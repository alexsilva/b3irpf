import datetime

import django.forms as django_forms
from django.apps import apps
from django.http import Http404
from django.utils import timezone

from irpf.models import Institution, Asset
from irpf.report import NegotiationReport
from irpf.views.base import AdminFormView
from xadmin.views import filter_hook
from xadmin.widgets import AdminDateWidget, AdminSelectWidget, AdminSelectMultiple

_now = timezone.now()
startdt, enddt = datetime.date.min.replace(year=_now.year), _now


class ReportIRPFForm(django_forms.Form):
	start = django_forms.DateField(
		label="Começando na data",
		initial=startdt,
		help_text="Data inicial  do ano para consolidação dos dados da declaração.",
		required=True,
		widget=AdminDateWidget
	)
	end = django_forms.DateField(
		label="Terminando na data",
		initial=enddt,
		help_text="Data final  do ano para consolidação dos dados da declaração.",
		required=True,
		widget=AdminDateWidget
	)

	consolidation = django_forms.IntegerField(
		label="Consolidação",
		widget=django_forms.Select(choices=[
				(1, "Anual"),
				(2, "Mensal")
			]),
		initial=1
	)
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

	def report_all(self, **options):
		"""report from all models"""
		return None

	def get_media(self):
		media = super().get_media()
		media += django_forms.Media(js=(
			"irpf/js/irpf.report.js",
		))
		return media

	def report_model(self, model, **options):
		"""report to specified model"""
		report = NegotiationReport(model, **options)
		return report

	@filter_hook
	def form_valid(self, form):
		if self.model_app_label == "all":
			self.report = self.report_all()
		else:
			model = apps.get_model(*self.model_app_label.split('.', 1))
			if not self.admin_site.get_registry(model, None):
				raise Http404

			self.report = self.report_model(model, user=self.user)

			form_data = form.cleaned_data
			institution = form_data['institution']
			asset = form_data['asset']
			consolidation = form_data['consolidation']
			categories = form_data['categories']
			start = form_data['start']
			end = form_data['end']

			self.results = self.report.report(start, end,
			                                  institution=institution,
			                                  asset=asset,
			                                  consolidation=consolidation,
			                                  categories=categories)
		return self.render_to_response(self.get_context_data(form=form))

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
