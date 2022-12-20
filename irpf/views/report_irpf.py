import django.forms as django_forms
from django.apps import apps
from django.http import Http404
from django.utils import timezone
from django.views.generic import FormView
from xadmin.widgets import AdminDateWidget
from xadmin.views.base import CommAdminView

_now = timezone.now()


class ReportIRPFForm(django_forms.Form):
	startdt = django_forms.DateField(
		label="Começando na data",
		initial=_now.replace(day=1, month=1).date(),
		help_text="Data inicial  do ano para consolidação dos dados da declaração.",
		required=True,
		widget=AdminDateWidget
	)


class AdminReportIrpfModelView(CommAdminView, FormView):
	"""View that produces the report with data consolidation (average cost, sum of earnings, etc)."""
	template_name = "irpf/adminx_report_irpf_view.html"
	form_class = ReportIRPFForm

	def init_request(self, *args, **kwargs):
		super().init_request(*args, **kwargs)
		model_app_label = self.kwargs['model_app_label']
		if model_app_label == "all":
			self.report_all()
		else:
			model = apps.get_model(*model_app_label.split('.', 1))
			if not self.admin_site.get_registry(model, None):
				raise Http404
			self.report_model(model)

	def report_all(self):
		"""report from all models"""

	def report_model(self, model):
		"""report to specified model"""

	def get_success_url(self):
		return self.request.path

	def form_valid(self, form):
		return super().form_valid(form)

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		return kwargs

	def get_context_data(self, **kwargs):
		context = self.get_context()
		context.update(super().get_context_data(**kwargs))
		context['media'] += context['form'].media
		return context
