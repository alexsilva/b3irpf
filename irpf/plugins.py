import django.forms as django_forms
from django.contrib.auth import get_permission_codename
from django.core.management import get_commands
from django.db.transaction import atomic
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from guardian.shortcuts import get_objects_for_user, assign_perm

from irpf.models import Negotiation, Earnings, Provision, Position
from xadmin.plugins import auth
from xadmin.plugins.utils import get_context_dict
from xadmin.views import BaseAdminPlugin


class GuardianAdminPlugin(BaseAdminPlugin):
	"""Protege a view permitindo acesso somente a objetos para os quais o usuário tem permissão"""
	guardian_protected = False

	def init_request(self, *args, **kwargs):
		return self.guardian_protected

	def queryset(self, __):
		model_perms = self.admin_view.get_model_perms()
		model_perms = [get_permission_codename(name, self.opts)
		               for name in model_perms if model_perms[name]]
		queryset = get_objects_for_user(
			self.user,
			model_perms,
			klass=self.model,
			any_perm=True,
			with_superuser=False,
			accept_global_perms=False)
		return queryset

	def save_models(self):
		new_obj = getattr(self.admin_view, "new_obj", None)
		if new_obj and new_obj.pk:
			model_perms = self.admin_view.get_model_perms()
			for perm_name in model_perms:
				# atribuição das permissões de objeto
				if model_perms[perm_name]:
					permission_codename = get_permission_codename(perm_name, self.opts)
					assign_perm(permission_codename, self.user, new_obj)


class AssignUserAdminPlugin(BaseAdminPlugin):
	"""Salva o usuário da sessão junto a instância do modelo recém criada"""
	assign_current_user = False

	def init_request(self, *args, **kwargs):
		return self.assign_current_user

	def save_forms(self):
		if self.admin_view.new_obj and self.admin_view.new_obj.user is None:
			self.admin_view.new_obj.user = self.user


class ListActionModelPlugin(BaseAdminPlugin):

	def init_request(self, *args, **kwargs):
		return issubclass(self.model, (Negotiation, Earnings, Provision))

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


class SaveReportPositionPlugin(BaseAdminPlugin):
	"""Salva os dados de posição do relatório"""
	position_model = Position
	position_permission = list(auth.ACTION_NAME)

	def form_valid(self, response, form):
		if self.is_save_position and self.admin_view.report and self.admin_view.results:
			self.save_position(form.cleaned_data['end'], self.admin_view.results)
		return response

	def block_form_buttons(self, context, nodes):
		if self.admin_view.report:
			return render_to_string("irpf/blocks/blocks.form.buttons.button_save_position.html")

	@atomic
	def save_position(self, date, results):
		for item in results:
			enterprise = item['enterprise']
			institution = item['institution']

			item_result = item['results']
			compra = item_result['compra']

			defaults = {
				'quantity': compra['quantity'],
				'avg_price': compra['avg_price'],
				'total': compra['total'],
				'date': date
			}
			instance, created = self.position_model.objects.get_or_create(
				defaults=defaults,
				enterprise=enterprise,
				institution=institution,
				user=self.user
			)
			if not created:
				for field_name in defaults:
					setattr(instance, field_name, defaults[field_name])
				instance.save()

			# permissões de objeto
			for name in self.position_permission:
				if not self.has_model_perm(self.position_model, name, self.user):
					continue
				codename = self.get_model_perm(self.position_model, name)
				assign_perm(codename, self.user, instance)

	@cached_property
	def is_save_position(self):
		field = django_forms.BooleanField(initial=False)
		try:
			value = field.to_python(self.request.GET.get('position'))
		except django_forms.ValidationError:
			value = field.initial
		return value
