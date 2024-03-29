import django.forms as django_forms
from django.apps import apps
from django.core.management import get_commands, load_command_class
from django.http import Http404

from irpf.views.base import AdminFormView
from xadmin.widgets import AdminFileWidget


class ImportListForm(django_forms.Form):
	filestream = django_forms.FileField(label="Arquivo",
	                                    help_text="formato excel (xlsx)",
	                                    widget=AdminFileWidget)


class AdminImportListModelView(AdminFormView):
	"""View that imports data through the import command"""
	template_name = "irpf/adminx_import_listmodel_view.html"
	form_class = ImportListForm
	title = "Importação de dados"
	form_method_post = True

	def init_request(self, *args, **kwargs):
		super().init_request(*args, **kwargs)
		model_app_label = self.kwargs['model_app_label']
		self.import_model = apps.get_model(*model_app_label.split('.', 1))
		if not self.admin_site.get_registry(self.import_model, None):
			raise Http404
		self.import_model_opts = self.import_model._meta

	def get_success_url(self):
		return self.get_model_url(self.import_model, "changelist")

	def get_media(self):
		media = super().get_media()
		media += django_forms.Media(css={
			'screen': ("irpf/css/irpf.import.css",)
		})
		return media

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context['verbose_name'] = getattr(self.import_model_opts, "verbose_name_plural", None)
		return context

	def form_valid(self, form):
		filestream = form.cleaned_data["filestream"]
		command_name = f"import_{self.import_model_opts.model_name.lower()}"
		command_app = get_commands()[command_name]
		try:
			command = load_command_class(command_app, command_name)
			command.handle(filepath=filestream.file,
			               user=self.user)
			self.message_user(f"Dados importados com sucesso!",
			                  level='success')
		except Exception as exc:
			self.message_user(f"Falha na importação de dados: {exc}",
			                  level='error')
		return super().form_valid(form)
