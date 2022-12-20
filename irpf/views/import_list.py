import django.forms as django_forms
from django.apps import apps
from django.core.management import get_commands, load_command_class
from django.http import Http404
from django.views.generic import FormView

from xadmin.views.base import CommAdminView


class ImportListForm(django_forms.Form):
	filestream = django_forms.FileField(label="Arquivo de dados")


class AdminImportListModelView(CommAdminView, FormView):
	"""View that imports data through the import command"""
	template_name = "irpf/adminx_import_listmodel_view.html"
	form_class = ImportListForm

	def init_request(self, *args, **kwargs):
		super().init_request(*args, **kwargs)
		model_app_label = self.kwargs['model_app_label']
		self.import_model = apps.get_model(*model_app_label.split('.', 1))
		if not self.admin_site.get_registry(self.import_model, None):
			raise Http404
		self.import_model_opts = self.import_model._meta

	def get_success_url(self):
		return self.get_model_url(self.import_model, "changelist")

	def form_valid(self, form):
		filestream = form.cleaned_data["filestream"]
		command_name = f"import_{self.import_model_opts.model_name.lower()}"
		command_app = get_commands()[command_name]
		try:
			command = load_command_class(command_app, command_name)
			command.handle(filepath=filestream.file)
			self.message_user(f"Dados importados com sucesso!",
			                  level='success')
		except Exception as exc:
			self.message_user(f"Falha na importação de dados: {exc}",
			                  level='error')
		return super().form_valid(form)

	def get_form_kwargs(self):
		kwargs = super().get_form_kwargs()
		return kwargs

	def get_context_data(self, **kwargs):
		context = self.get_context()
		context.update(super().get_context_data(**kwargs))
		context['media'] += context['form'].media
		return context
