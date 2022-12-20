import django.forms as django_forms
from django.core.management import get_commands

from xadmin.plugins.utils import get_context_dict
from xadmin.views import BaseAdminPlugin


class ImportListModelPlugin(BaseAdminPlugin):

	def init_request(self, *args, **kwargs):
		self.command_name = f"import_{self.opts.model_name.lower()}"
		return self.command_name in get_commands()

	def block_top_toolbar(self, context, nodes):
		context = get_context_dict(context)
		model_name = f"{self.opts.app_label}.{self.opts.model_name}"
		url = self.get_admin_url("import_listmodel", model_name)
		return f"""
		<div class="btn-group layout-btns ml-2">
          <a href="{url}" class="btn-link btn-sm import-list">
            Importa lista de dados
          </a>
        </div>
		"""

	def get_media(self, media):
		media += django_forms.Media(js=[
			"irpf/js/import.list.model.js",
		])
		return media
