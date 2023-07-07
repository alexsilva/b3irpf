import django.forms as django_forms
from django.apps import apps
from django.http import Http404
from django.utils import timezone
from django.utils.module_loading import import_string
from xadmin.views import filter_hook
from xadmin.widgets import AdminDateWidget, AdminSelectWidget, AdminSelectMultiple

from irpf.models import Institution, Asset, Position
from irpf.utils import YearMonthDates
from irpf.views.base import AdminFormView
from irpf.widgets import YearMonthWidget, YearMonthField

_now = timezone.now()
startdt, enddt = YearMonthDates(_now.year, _now.month).year_interval


class ReportIRPFForm(django_forms.Form):
	prefix = 'rp'
	# start = django_forms.DateField(
	# 	label="Começa",
	# 	initial=startdt,
	# 	help_text="Data inicial para consolidação dos dados da declaração.",
	# 	required=True,
	# 	widget=AdminDateWidget
	# )
	# end = django_forms.DateField(
	# 	label="Termina",
	# 	initial=enddt,
	# 	help_text="Data final para consolidação dos dados da declaração.",
	# 	required=True,
	# 	widget=AdminDateWidget
	# )

	consolidation = django_forms.IntegerField(
		label="Apuração",
		widget=django_forms.Select(choices=Position.CONSOLIDATION_CHOICES),
		initial=Position.CONSOLIDATION_MONTHLY
	)

	dates = YearMonthField(label="Período", widget=YearMonthWidget(attrs={
		'class': 'form-control my-1',
	}), initial=(_now.year, _now.month))

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


class AdminReportIrpfModelView(AdminFormView):
	"""View that produces the report with data consolidation (average cost, sum of earnings, etc)."""
	template_name = "irpf/adminx_report_irpf_view.html"
	form_class = ReportIRPFForm

	title = "Relatório IRPF"

	def init_request(self, *args, **kwargs):
		super().init_request(*args, **kwargs)
		self.model_app_label = self.kwargs['model_app_label']
		self.report, self.results = None, None

	def get_media(self):
		media = super().get_media()
		media += django_forms.Media(js=(
			"irpf/js/irpf.report.js",
		), css={
			'screen': ('irpf/css/irpf.report.css',)
		})
		return media

	def report_object(self, report_class, model, user, **options):
		"""report to specified model"""
		report = report_class(model, user, **options)
		return report

	@filter_hook
	def form_valid(self, form):
		model = apps.get_model(*self.model_app_label.split('.', 1))
		report_class = getattr(model, "report_class", None)

		if not (self.admin_site.get_registry(model, None) and report_class):
			raise Http404

		report_class = import_string(model.report_class)

		self.report = self.report_object(report_class, model, self.user)

		form_data = form.cleaned_data
		dates: YearMonthDates = form_data['dates']
		institution = form_data['institution']
		consolidation = form_data['consolidation']
		categories = form_data['categories']
		asset = form_data['asset']

		if consolidation == Position.CONSOLIDATION_YEARLY:
			start, end = dates.year_interval
		elif consolidation == Position.CONSOLIDATION_MONTHLY:
			start, end = dates.month_interval
		else:
			start, end = None, None

		if (btn_dates := self.request.GET.get('btn_dates')) == "_dates_next":
			if consolidation == Position.CONSOLIDATION_YEARLY:
				dates = YearMonthDates(dates.year + 1, dates.month)
				start, end = dates.year_interval
			elif consolidation == Position.CONSOLIDATION_MONTHLY:
				dates = YearMonthDates(dates.year, dates.month + 1 if dates.month < 12 else 12)
				start, end = dates.month_interval
		elif btn_dates == "_dates_previous":
			if consolidation == Position.CONSOLIDATION_YEARLY:
				dates = YearMonthDates(dates.year - 1, dates.month)
				start, end = dates.year_interval
			elif consolidation == Position.CONSOLIDATION_MONTHLY:
				dates = YearMonthDates(dates.year, dates.month - 1 if dates.month > 1 else 1)
				start, end = dates.month_interval

		self.results = self.report.report(start, end,
		                                  institution=institution,
		                                  asset=asset,
		                                  consolidation=consolidation,
		                                  categories=categories)
		self.start_date, self.end_date = start, end
		form.data = self._get_form_data(form, dates)
		return self.render_to_response(self.get_context_data(form=form))

	@staticmethod
	def _get_form_data(form, dates):
		data = form.data.copy()
		dates_widget = form.fields['dates'].widget
		prefix = f"{form.prefix}-" if form.prefix else ""
		data[f'{prefix}dates{dates_widget.widgets_names[0]}'] = dates.year
		data[f'{prefix}dates{dates_widget.widgets_names[1]}'] = dates.month
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
		if self.report and self.results:
			context['report'] = {
				'report': self.report,
				'results': self.results
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
