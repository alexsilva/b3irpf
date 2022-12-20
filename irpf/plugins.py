import django.forms as django_forms
from django.core.management import get_commands
from django.template.loader import render_to_string

from xadmin.plugins.utils import get_context_dict
from xadmin.views import BaseAdminPlugin


class ListActionModelPlugin(BaseAdminPlugin):

	def init_request(self, *args, **kwargs):
		self.command_name = f"import_{self.opts.model_name.lower()}"
		return self.command_name in get_commands()

	def get_import_action(self):
		model_name = f"{self.opts.app_label}.{self.opts.model_name}"
		url = self.get_admin_url("import_listmodel", model_name)
		return {
			'title': "Importa lista de dados",
			'url': url
		}

	def get_report_action(self):
		return {
			'title': "Relário do IRPF",
			'url': ''
		}

	def block_top_toolbar(self, context, nodes):
		context = get_context_dict(context)
		list_actions_group = {
			"import_list": self.get_import_action(),
			"report_irpf": self.get_report_action()
		}
		context['list_actions_group'] = list_actions_group
		return render_to_string("irpf/adminx.block.listtoolbar_action.html",
		                        context=context)

	def get_media(self, media):
		media += django_forms.Media(js=[
			"irpf/js/import.list.model.js",
		])
		return media
