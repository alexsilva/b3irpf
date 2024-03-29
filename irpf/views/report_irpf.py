from datetime import date
from datetime import datetime

import django.forms as django_forms
import time
from django.apps import apps
from django.http import Http404
from django.utils.datastructures import MultiValueDict
from django.utils.formats import date_format
from django.utils.safestring import mark_safe
from xadmin.views import filter_hook
from xadmin.widgets import AdminSelectWidget, AdminSelectMultiple

from irpf.models import Institution, Asset, Position
from irpf.report.base import BaseReportMonth
from irpf.utils import MonthYearDates
from irpf.views.base import AdminFormView
from irpf.widgets import MonthYearWidgetNavigator, MonthYearNavigatorField
from xadmin.util import vendor

_now = datetime.now()


class ReportIRPFForm(django_forms.Form):
	consolidation = django_forms.IntegerField(
		label="Apuração",
		widget=django_forms.Select(choices=Position.CONSOLIDATION_CHOICES),
		initial=Position.CONSOLIDATION_MONTHLY
	)

	dates = MonthYearNavigatorField(label="Período", widget=MonthYearWidgetNavigator(attrs={
		'class': 'form-control my-1',
	}), initial=(_now.month, _now.year))

	asset = django_forms.ModelChoiceField(Asset.objects.all(),
	                                      label=Asset._meta.verbose_name,
	                                      widget=AdminSelectWidget,
	                                      required=False)
	categories = django_forms.TypedMultipleChoiceField(choices=Asset.CATEGORY_CHOICES,
	                                                   widget=AdminSelectMultiple,
	                                                   label="Categorias",
	                                                   coerce=int,
	                                                   required=False)
	institution = django_forms.ModelChoiceField(Institution.objects.all(),
	                                            label=Institution._meta.verbose_name,
	                                            widget=AdminSelectWidget,
	                                            required=False)
	# para debug
	ts = django_forms.BooleanField(widget=django_forms.HiddenInput,
	                               initial=False,
	                               required=False)


class ReportIRPFFAdminView(AdminFormView):
	"""View that produces the report with data consolidation (average cost, sum of earnings, etc)."""
	template_name = "irpf/adminx_report_irpf_view.html"
	form_class = ReportIRPFForm
	title = "Relatório IRPF"
	models_report_class = {}

	def init_request(self, *args, **kwargs):
		super().init_request(*args, **kwargs)
		self.model_app_label = self.kwargs['model_app_label']
		self.reports: BaseReportMonth = None
		self.ts = None
		self.model = apps.get_model(*self.model_app_label.split('.', 1))
		if not self.admin_site.get_registry(self.model, None):
			raise Http404
		try:
			self.report_class = self.models_report_class[self.model]
		except KeyError:
			raise Http404

	def get_media(self):
		media = super().get_media()
		media += vendor("xadmin.bs.modal.js")
		media += django_forms.Media(js=(
			"irpf/js/irpf.plugin.clipboard.js",
			"irpf/js/irpf.report.js",
			"irpf/js/irpf.modal.expand.js",
		), css={
			'screen': ('irpf/css/irpf.report.css',)
		})
		return media

	def get_site_title(self):
		title = super().get_site_title()
		if self.reports:
			start = date_format(self.reports.start_date, "j b.")
			end = date_format(self.reports.end_date, "j b. Y")
			title = f"{title} - {start} até {end}"
			if self.ts:
				title += f" - TS({self.ts})"
			title = mark_safe(title)
		return title

	def report_object(self, **options):
		"""report to specified model"""
		report = self.report_class(self.user, self.model, **options)
		return report

	@filter_hook
	def report_generate(self, form):
		now = datetime.now().date()

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
				dates = MonthYearDates(dates.month, dates.year)
				if dates.month < 12:
					dates.month += 1
				else:
					dates.month = 1
					dates.year += 1
		elif _dates == "prev":
			if consolidation == Position.CONSOLIDATION_YEARLY:
				dates = MonthYearDates(dates.month, dates.year - 1)
			elif consolidation == Position.CONSOLIDATION_MONTHLY:
				dates = MonthYearDates(dates.month, dates.year)
				if dates.month > 1:
					dates.month -= 1
				else:
					dates.month = 12
					dates.year -= 1
		if consolidation == Position.CONSOLIDATION_YEARLY:
			months = dates.get_year_month_range(now)
		elif consolidation == Position.CONSOLIDATION_MONTHLY:
			months = [dates.get_month_range(now)]
		else:
			months = []

		reports = self.report_object()
		reports.generate(
			months,
			consolidation=consolidation,
			institution=institution,
			categories=categories,
			asset=asset
		)
		return reports

	@filter_hook
	def form_valid(self, form):
		ts = time.time()
		self.reports = self.report_generate(form)
		if form.cleaned_data['ts']:  # tempo da operação
			self.ts = time.time() - ts
		form.data = self.get_form_data(form, self.reports.start_date, self.reports.end_date)
		return self.render_to_response(self.get_context_data(form=form))

	@filter_hook
	def get_form_data(self, form, start_date: date, end_date: date) -> MultiValueDict:
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
			results = self.reports.compile()
			context['report'] = {
				'reports': self.reports,
				'start_date': self.reports.start_date,
				'end_date': self.reports.end_date,
				'results': results,
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
