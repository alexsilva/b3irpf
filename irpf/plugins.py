import django.forms as django_forms
from django.core.management import get_commands
from django.template.loader import render_to_string
from django.utils.functional import cached_property

from irpf.models import Negotiation, Earnings
from xadmin.plugins.utils import get_context_dict
from xadmin.views import BaseAdminPlugin


class ListActionModelPlugin(BaseAdminPlugin):

	def init_request(self, *args, **kwargs):
		return issubclass(self.model, (Negotiation, Earnings))

	@cached_property
	def model_app_label(self):
		return f"{self.opts.app_label}.{self.opts.model_name}"

	def get_import_action(self):
		url = self.get_admin_url("import_listmodel", self.model_app_label)
		return {
			'title': "Importar lista de dados",
			'url': url
		}

	def get_report_action(self):
		url = self.get_admin_url("reportirpf", self.model_app_label)
		return {
			'title': "Relatório do IRPF",
			'url': url
		}

	def block_top_toolbar(self, context, nodes):
		context = get_context_dict(context)
		list_actions_group = {}

		command_name = f"import_{self.opts.model_name.lower()}"
		if command_name in get_commands():
			list_actions_group['import_list'] = self.get_import_action()

		list_actions_group["report_irpf"] = self.get_report_action()

		context['list_actions_group'] = list_actions_group
		return render_to_string("irpf/adminx.block.listtoolbar_action.html",
		                        context=context)

	def get_media(self, media):
		media += django_forms.Media(js=[
			"irpf/js/import.list.model.js",
		])
		return media
