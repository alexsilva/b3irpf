import collections
import io
import itertools
import re

import django.forms as django_forms
from django.contrib.auth import get_permission_codename
from django.contrib.auth.models import Permission
from django.core.management import get_commands
from django.db.transaction import atomic
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from guardian.shortcuts import get_objects_for_user, assign_perm

from correpy.domain.entities.security import Security
from correpy.domain.entities.transaction import Transaction
from correpy.domain.enums import TransactionType
from irpf.models import Negotiation, Earnings, Provision, Position
from xadmin.plugins import auth
from xadmin.plugins.utils import get_context_dict
from xadmin.views import BaseAdminPlugin


class GuadianAdminPluginMixin(BaseAdminPlugin):

	def add_permission_for_object(self, obj, opts=None):
		model_perms = self.admin_view.get_model_perms()
		if opts is None:
			opts = self.opts
		for perm_name in model_perms:
			# atribuição das permissões de objeto
			if model_perms[perm_name]:
				permission_codename = get_permission_codename(perm_name, opts)
				assign_perm(permission_codename, self.user, obj)


class GuardianAdminPlugin(GuadianAdminPluginMixin):
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
			self.add_permission_for_object(new_obj)


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
			asset = item['results']

			defaults = {
				'quantity': asset.buy.quantity,
				'avg_price': asset.buy.avg_price,
				'total': asset.buy.total,
				'tax': asset.buy.tax,
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
			elif asset.items:
				# relaciona a intância (Negotiation) com a posição
				for obj in asset.items:
					if obj.position == instance:
						continue
					obj.position = instance
					obj.save()

			# permissões de objeto
			for name in self.position_permission:
				if not self.has_model_perm(self.position_model, name, self.user):
					continue
				try:
					codename = self.get_model_perm(self.position_model, name)
					assign_perm(codename, self.user, instance)
				except Permission.DoesNotExist:
					continue

	@cached_property
	def is_save_position(self):
		field = django_forms.BooleanField(initial=False)
		try:
			value = field.to_python(self.request.GET.get('position'))
		except django_forms.ValidationError:
			value = field.initial
		return value


class BrokerageNoteAdminPlugin(GuadianAdminPluginMixin):
	"""Plugin que faz o registro da nota de corretagem
	Distribui os valores proporcionais de taxas e registra negociações
	"""
	brokerage_note_parsers = None
	brokerage_note_field_update = ()
	brokerage_note_negociation = Negotiation

	def init_request(self, *args, **kwargs):
		return bool(self.brokerage_note_negociation and
		            self.brokerage_note_parsers)

	def setup(self, *args, **kwargs):
		...

	def block_submit_more_btns(self, context, nodes):
		return render_to_string("irpf/blocks/blocks.form.save_transactions.html")

	@cached_property
	def is_save_transactions(self):
		field = django_forms.BooleanField(initial=False)
		try:
			value = field.to_python(self.request.POST.get('_continue') == "save_transactions")
		except django_forms.ValidationError:
			value = field.initial
		return value

	@atomic
	def _parser_file(self, parser, instance):
		with instance.note.file as fp:
			parser = parser(brokerage_note=io.BytesIO(fp.read()))
			for note in parser.parse_brokerage_note():
				for field_name in self.brokerage_note_field_update:
					setattr(instance, field_name, getattr(note, field_name))

				instance.save()
				self._add_transations(note, instance)

	def _save_trasaction(self, asset, instance, **options) -> Negotiation:
		"""Cria uma nova 'transaction' com os dados da nota"""
		options.update(
			date=instance.reference_date,
			quantity=asset.amount,
			price=asset.unit_price,
			brokerage_note=instance,
			irrf=asset.source_withheld_taxes,
			institution=instance.institution.name,
			user=self.user
		)
		defaults = options.setdefault('defaults', {})
		defaults['total'] = asset.amount * asset.unit_price
		model = self.brokerage_note_negociation
		opts = model._meta
		obj, created = model.objects.get_or_create(**options)
		self.add_permission_for_object(obj, opts=opts)
		return obj

	def _get_transaction_type(self, asset) -> str:
		# filtro para a categoria de transação
		kind = None
		if asset.transaction_type == TransactionType.BUY:
			kind = self.brokerage_note_negociation.KIND_BUY
		elif asset.transaction_type == TransactionType.SELL:
			kind = self.brokerage_note_negociation.KIND_SELL
		return kind

	@staticmethod
	def _get_clean_ticker(asset):
		return asset.security.ticker.rstrip("Ff")

	def _get_transations_group(self, note_transactions) -> collections.OrderedDict:
		"""Agrupa transações que perceçam ao mesmo ativo"""
		transactions = collections.OrderedDict()

		def key_group(ts):
			return self._get_clean_ticker(ts), ts.transaction_type

		for key, group in itertools.groupby(note_transactions, key=key_group):
			ticker, transaction_type = key
			for transaction in group:
				try:
					asset = transactions[ticker]
					asset_total = asset.amount * asset.unit_price
					transaction_total = transaction.amount * transaction.unit_price
					# atualização do preço médio e quantidade
					asset.amount += transaction.amount
					asset.unit_price = (asset_total + transaction_total) / asset.amount
				except KeyError:
					transactions[ticker] = Transaction(
						transaction_type=transaction.transaction_type,
						amount=transaction.amount,
						unit_price=transaction.unit_price,
						security=Security(ticker)
					)
		return transactions

	def _add_transations(self, note, instance):
		queryset = self.brokerage_note_negociation.objects.all()
		tax = sum([note.settlement_fee,
		           note.term_fee,
		           note.ana_fee,
		           note.registration_fee,
		           note.taxes,
		           note.emoluments,
		           note.others])

		transactions = self._get_transations_group(note.transactions)
		paid = sum([(transactions[ticker].amount * transactions[ticker].unit_price)
		            for ticker in transactions])
		for ticker in transactions:
			asset = transactions[ticker]
			qs = queryset.filter(
				date=instance.reference_date,
				institution=instance.institution.name,
				user=self.user)
			kind = self._get_transaction_type(asset)
			if kind is None:
				continue
			# rateio de taxas proporcional ao valor pago
			tx = tax * ((asset.amount * asset.unit_price) / paid)
			qs = qs.filter(code__iexact=ticker,
			               kind__iexact=kind,
			               quantity=asset.amount,
			               price=asset.unit_price)
			if self.is_save_transactions and not qs.exists():
				self._save_trasaction(
					asset, instance,
					code=ticker,
					kind=kind,
					defaults={'tx': tx}
				)
			else:
				for negociation in qs:
					negociation.tx = tx
					negociation.brokerage_note = instance
					negociation.save()

	def save_models(self):
		instance = getattr(self.admin_view, "new_obj", None)
		if instance and instance.pk:
			if parts := re.findall('([0-9]+)', instance.institution.cnpj):
				cnpj = ''.join(parts)
				parser = self.brokerage_note_parsers[cnpj]
				self._parser_file(parser, instance)


class ReportStatsAdminPlugin(BaseAdminPlugin):
	"""Gera dados estatísticos (compra, venda, etc)"""

	def init_request(self, *args, **kwargs):
		return True

	def get_stats(self):
		stats = {}
		results = self.admin_view.results
		buy, sell, capital, tax = 'buy', 'sell', 'capital', 'tax'
		stats[capital] = stats[buy] = stats[sell] = stats[tax] = 0.0
		for item in results:
			asset = item['results']
			stats[buy] += asset.buy.total
			stats[sell] += asset.sell.total
			stats[capital] += asset.sell.capital
			stats[tax] += (asset.buy.tax + asset.sell.tax)
		return stats

	def get_context_data(self, context, **kwargs):
		if self.admin_view.report and self.admin_view.results:
			context['report']['stats'] = self.get_stats()
		return context

	def block_report(self, context, nodes):
		context = get_context_dict(context)
		return render_to_string('irpf/blocks/blocks.adminx_report_irpf_stats.html',
		                        context=context)
