from collections import OrderedDict
import time
from datetime import date

import django.forms as django_forms
from django.apps import apps
from django.http import Http404
from django.utils.formats import date_format
from django.utils.module_loading import import_string
from django.utils.safestring import mark_safe
from xadmin.views import filter_hook
from xadmin.widgets import AdminSelectWidget, AdminSelectMultiple
from datetime import datetime


from irpf.models import Institution, Asset, Position
from irpf.utils import MonthYearDates
from irpf.views.base import AdminFormView
from irpf.widgets import MonthYearWidget, MonthYearField

_now = datetime.now()
startdt, enddt = MonthYearDates(_now.year, _now.month).get_year_interval(_now)


class ReportIRPFForm(django_forms.Form):
	consolidation = django_forms.IntegerField(
		label="Apuração",
		widget=django_forms.Select(choices=Position.CONSOLIDATION_CHOICES),
		initial=Position.CONSOLIDATION_MONTHLY
	)

	dates = MonthYearField(label="Período", widget=MonthYearWidget(attrs={
		'class': 'form-control my-1',
	}), initial=(_now.month, _now.year))

	asset = django_forms.ModelChoiceField(Asset.objects.all(),
	                                      label=Asset._meta.verbose_name,
	                                      widget=AdminSelectWidget,
	                                      required=False)
	categories = django_forms.MultipleChoiceField(choices=Asset.CATEGORY_CHOICES,
	                                              widget=AdminSelectMultiple,
	                                              label="Categorias",
	                                              required=False)
	institution = django_forms.ModelChoiceField(Institution.objects.all(),
	                                            label=Institution._meta.verbose_name,
	                                            widget=AdminSelectWidget,
	                                            required=False)
	# para debug
	ts = django_forms.BooleanField(widget=django_forms.HiddenInput,
	                               initial=False,
	                               required=False)


class AdminReportIrpfModelView(AdminFormView):
	"""View that produces the report with data consolidation (average cost, sum of earnings, etc)."""
	template_name = "irpf/adminx_report_irpf_view.html"
	form_class = ReportIRPFForm
	title = "Relatório IRPF"
	models_report_class = {}

	def init_request(self, *args, **kwargs):
		super().init_request(*args, **kwargs)
		self.model_app_label = self.kwargs['model_app_label']
		self.start_date = self.ts = self.end_date = None
		self.reports: OrderedDict[int] = None

		self.model = apps.get_model(*self.model_app_label.split('.', 1))
		if not self.admin_site.get_registry(self.model, None):
			raise Http404
		try:
			self.report_class = self.models_report_class[self.model]
		except KeyError:
			raise Http404

	def get_media(self):
		media = super().get_media()
		media += django_forms.Media(js=(
			"irpf/js/irpf.report.js",
		), css={
			'screen': ('irpf/css/irpf.report.css',)
		})
		return media

	def get_site_title(self):
		title = super().get_site_title()
		if self.start_date and self.end_date:
			start = date_format(self.start_date)
			end = date_format(self.end_date)
			title = f"{title} - {start} Até {end}"
			if self.ts:
				title += f" - TS({self.ts})"
			title = mark_safe(title)
		return title

	def report_object(self, user, **options):
		"""report to specified model"""
		report = self.report_class(self.model, user, **options)
		return report

	@filter_hook
	def report_generate(self, form):
		now = datetime.now()

		form_data = form.cleaned_data
		dates: MonthYearDates = form_data['dates']
		institution = form_data['institution']
		consolidation = form_data['consolidation']
		categories = form_data['categories']
		asset = form_data['asset']

		if (_dates := self.request.GET.get('_dates')) == "next":
			if consolidation == Position.CONSOLIDATION_YEARLY:
				dates = MonthYearDates(dates.month, dates.year + 1)
			elif consolidation == Position.CONSOLIDATION_MONTHLY:
				dates = MonthYearDates(dates.month + 1 if dates.month < 12 else 12, dates.year)
		elif _dates == "prev":
			if consolidation == Position.CONSOLIDATION_YEARLY:
				dates = MonthYearDates(dates.month, dates.year - 1)
			elif consolidation == Position.CONSOLIDATION_MONTHLY:
				dates = MonthYearDates(dates.month - 1 if dates.month > 1 else 1, dates.year)

		if consolidation == Position.CONSOLIDATION_YEARLY:
			months = dates.get_year_months(now)
		elif consolidation == Position.CONSOLIDATION_MONTHLY:
			months = [dates.get_month_interval(now)]
		else:
			months = []

		reports_months = OrderedDict()
		for start, end in months:
			report = self.report_object(self.user)
			# após o processamento do relatório esse dado vai ser removido
			report.cache.set('report_history', reports_months.get(start.month - 1))
			# gera os dados de results
			report.generate(
				start, end,
				institution=institution,
				categories=categories,
				asset=asset
			)
			reports_months[start.month] = report

		if len(months) == 1:
			self.start_date, self.end_date = months[0]
		else:
			self.start_date, self.end_date = months[0][0], months[-1][1]
		return reports_months

	@filter_hook
	def form_valid(self, form):
		ts = time.time()
		self.reports = self.report_generate(form)
		if form.cleaned_data['ts']:  # tempo da operação
			self.ts = time.time() - ts
		form.data = self._get_form_data(form, self.start_date, self.end_date)
		return self.render_to_response(self.get_context_data(form=form))

	@staticmethod
	def _get_form_data(form, start_date: date, end_date: date):
		data = form.data.copy()
		dates_widget = form.fields['dates'].widget
		prefix = f"{form.prefix}-" if form.prefix else ""
		data[f'{prefix}dates{dates_widget.widgets_names[0]}'] = end_date.month
		data[f'{prefix}dates{dates_widget.widgets_names[1]}'] = end_date.year
		return data

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		if self.request.GET or self.request.FILES:
			kwargs.update({
				'data': self.request.GET,
				'files': self.request.FILES,
			})
		return kwargs

	@filter_hook
	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		if self.reports:
			results = self.report_class.compile(self.end_date, self.reports)
			context['report'] = {
				'reports': self.reports,
				'results': results,
				'start_date': self.start_date,
				'end_date': self.end_date,
				'ts': self.ts,
			}
		return context

	def get(self, request, *args, **kwargs):
		"""
		Handle POST requests: instantiate a form instance with the passed
		POST variables and then check if it's valid.
		"""
		if self.request.GET:
			response = self.post(request, *args, **kwargs)
		else:
			response = super().get(request, *args, **kwargs)
		return response
