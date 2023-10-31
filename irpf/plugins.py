import calendar
import collections
import datetime
import io
import itertools
import re
from collections import OrderedDict
import django.forms as django_forms
from correpy.parsers.brokerage_notes.b3_parser.b3_parser import B3Parser
from django.conf import settings
from django.contrib.auth import get_permission_codename
from django.contrib.auth.models import Permission
from django.core.management import get_commands
from django.db.models import Count
from django.db.models.functions import ExtractMonth
from django.db.transaction import atomic
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from guardian.shortcuts import get_objects_for_user, assign_perm
from correpy.domain.entities.security import Security
from correpy.domain.entities.transaction import Transaction
from correpy.domain.enums import TransactionType
from irpf.fields import CharCodeField
from irpf.models import Negotiation, Earnings, Position, Asset, Statistic
from irpf.report import BaseReport
from irpf.report.base import BaseReportMonth
from irpf.report.utils import Assets, Stats, MoneyLC
from irpf.report.stats import StatsReport
from xadmin.plugins import auth
from xadmin.plugins.utils import get_context_dict
from xadmin.views import BaseAdminPlugin


class GuardianAdminPluginMixin(BaseAdminPlugin):

	def add_permission_for_object(self, obj, opts=None):
		model_perms = self.admin_view.get_model_perms()
		if opts is None:
			opts = self.opts
		for perm_name in model_perms:
			# atribuição das permissões de objeto
			if model_perms[perm_name]:
				permission_codename = get_permission_codename(perm_name, opts)
				assign_perm(permission_codename, self.user, obj)


class GuardianAdminPlugin(GuardianAdminPluginMixin):
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
	list_action_activate = False

	def init_request(self, *args, **kwargs):
		return self.list_action_activate

	def get_import_action(self):
		url = self.get_admin_url("import_listmodel", self.opts.label_lower)
		return {
			'title': "Importar lista de dados",
			'url': url
		}

	def get_report_action(self):
		url = self.get_admin_url("reportirpf", self.opts.label_lower)
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


class ReportBaseAdminPlugin(BaseAdminPlugin):
	report_for_model = Negotiation

	def init_request(self, *args, **kwargs):
		activate = False
		if model_app_label := kwargs.get('model_app_label'):
			activate = model_app_label == self.report_for_model._meta.label_lower
		return activate

	def setup(self, *args, **kwargs):
		self._caches = {}

	@staticmethod
	def _update_defaults(instance, defaults):
		"""Atualiza, se necessário a instância com valores padrão"""
		updated = False
		for key in defaults:
			value = defaults[key]
			if not updated and getattr(instance, key) != value:
				updated = True
			setattr(instance, key, value)
		if updated:
			instance.save(update_fields=list(defaults))
		return updated

	@cached_property
	def is_save_position(self):
		field = django_forms.BooleanField(initial=False)
		try:
			value = field.to_python(self.request.GET.get('position'))
		except django_forms.ValidationError:
			value = field.initial
		return value

	def report_generate(self, reports: BaseReportMonth, form):
		if self.is_save_position and reports:
			self.save(reports)
		return reports

	def save(self, reports: BaseReportMonth):
		...


class SaveReportPositionPlugin(ReportBaseAdminPlugin):
	"""Salva os dados de posição do relatório"""
	position_model = Position
	position_permission = list(auth.ACTION_NAME)

	def block_form_buttons(self, context, nodes):
		if self.admin_view.reports:
			return render_to_string("irpf/blocks/blocks.form.buttons.button_save_position.html")

	def save_position(self, report: BaseReport, asset: Assets):
		consolidation = report.get_opts('consolidation')
		end_date = report.get_opts('end_date')
		institution = asset.institution

		defaults = {
			'quantity': asset.buy.quantity,
			'avg_price': asset.buy.avg_price,
			'total': asset.buy.total,
			'tax': asset.buy.tax
		}
		instance, created = self.position_model.objects.get_or_create(
			defaults=defaults,
			date=end_date,
			user=self.user,
			asset=asset.instance,
			institution=institution,
			consolidation=consolidation
		)
		if not created:
			for field_name in defaults:
				setattr(instance, field_name, defaults[field_name])
			instance.save()
		# permissões de objeto
		for name in self.position_permission:
			if not self.has_model_perm(self.position_model, name, self.user):
				continue
			try:
				codename = self.get_model_perm(self.position_model, name)
				assign_perm(codename, self.user, instance)
			except Permission.DoesNotExist:
				continue

	def _remove_positions(self, report: BaseReport):
		"""Remove todos os dados de posição a partir da data 'end_date' relatório"""
		institution = report.get_opts('institution', None)
		consolidation = report.get_opts('consolidation')
		end_date = report.get_opts('end_date')
		# remove registro acima da data
		return self.position_model.objects.filter(
			user=self.user,
			date__gt=end_date,
			institution=institution,
			consolidation=consolidation
		).delete()

	@atomic
	def save(self, reports: BaseReportMonth):
		try:
			for month in reports:
				report = reports[month]
				self._remove_positions(report)
				for asset in report.get_results():
					# ativo não cadastrado
					if asset.instance is None:
						continue
					self.save_position(report, asset)
		except Exception as exc:
			self.message_user(f"Falha ao salvar posições: {exc}", level="error")
		else:
			self.message_user("Posições salvas com sucesso!", level="info")


class BrokerageNoteAdminPlugin(GuardianAdminPluginMixin):
	"""Plugin que faz o registro da nota de corretagem
	Distribui os valores proporcionais de taxas e registra negociações
	"""
	brokerage_note_parsers = None
	brokerage_note_field_update = ()
	brokerage_note_negotiation = Negotiation
	brokerage_note_asset_model = Asset

	def init_request(self, *args, **kwargs):
		return bool(self.brokerage_note_negotiation and
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

	def get_asset(self, ticker: str):
		"""O ativo"""
		try:
			asset = self.brokerage_note_asset_model.objects.get(code__iexact=ticker)
		except self.brokerage_note_asset_model.DoesNotExist:
			asset = None
		return asset

	def _save_trasaction(self, transaction: Transaction, instance, **options) -> Negotiation:
		"""Cria uma nova 'transaction' com os dados da nota"""
		ticker = options['code']
		options.update(
			date=instance.reference_date,
			quantity=transaction.amount,
			price=transaction.unit_price,
			brokerage_note=instance,
			irrf=transaction.source_withheld_taxes,
			institution=instance.institution.name,
			asset=self.get_asset(ticker),
			user=self.user
		)
		defaults = options.setdefault('defaults', {})
		defaults['total'] = transaction.amount * transaction.unit_price
		model = self.brokerage_note_negotiation
		opts = model._meta
		obj, created = model.objects.get_or_create(**options)
		self.add_permission_for_object(obj, opts=opts)
		return obj

	def _get_transaction_type(self, transaction: Transaction) -> str:
		# filtro para a categoria de transação
		kind = None
		if transaction.transaction_type == TransactionType.BUY:
			kind = self.brokerage_note_negotiation.KIND_BUY
		elif transaction.transaction_type == TransactionType.SELL:
			kind = self.brokerage_note_negotiation.KIND_SELL
		return kind

	def _get_clean_ticker(self, asset):
		"""Retornao ticker (code) simplificado"""
		return CharCodeField().to_python(asset.security.ticker)

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
		queryset = self.brokerage_note_negotiation.objects.all()
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
			transaction = transactions[ticker]
			qs = queryset.filter(
				date=instance.reference_date,
				institution=instance.institution.name,
				user=self.user)
			kind = self._get_transaction_type(transaction)
			if kind is None:
				continue
			# rateio de taxas proporcional ao valor pago
			avg_tax = tax * ((transaction.amount * transaction.unit_price) / paid)
			qs = qs.filter(code__iexact=ticker,
			               kind__iexact=kind,
			               quantity=transaction.amount)
			if self.is_save_transactions and not qs.exists():
				self._save_trasaction(
					transaction, instance,
					code=ticker,
					kind=kind,
					defaults={'tax': avg_tax}
				)
			else:
				for negotiation in qs:
					negotiation.tax = avg_tax
					negotiation.brokerage_note = instance
					negotiation.save()

	def save_models(self):
		instance = getattr(self.admin_view, "new_obj", None)
		if instance and instance.pk:
			if parts := re.findall('([0-9]+)', instance.institution.cnpj):
				cnpj = ''.join(parts)
				try:
					parser = self.brokerage_note_parsers[cnpj]
				except KeyError:
					parser = B3Parser
				self._parser_file(parser, instance)


class StatsReportAdminPlugin(ReportBaseAdminPlugin):
	"""Gera dados estatísticos (compra, venda, etc)"""
	stats_report_class = StatsReport
	statistic_model = Statistic
	position_model = Position
	asset_model = Asset

	def setup(self, *args, **kwargs):
		super().setup(*args, **kwargs)
		# guarda a referência na view
		self.admin_view.stats = None

	def _remove_stats(self, report: BaseReport):
		"""Remove todos os dados de Stats a partir da data 'end_date' relatório"""
		institution = report.get_opts('institution', None)
		consolidation = report.get_opts('consolidation')
		end_date = report.get_opts('end_date')
		# remove registro acima da data
		return self.statistic_model.objects.filter(
			user=self.user,
			date__gt=end_date,
			institution=institution,
			consolidation=consolidation,
		).delete()

	def save_stats(self, report: BaseReport, stats: StatsReport):
		"""Salva dados de estatística"""
		institution = report.get_opts('institution', None)
		date = report.get_opts('end_date')

		stats_results = stats.get_results()
		for category_name in stats_results:
			stats_category: Stats = stats_results[category_name]
			category = self.asset_model.get_category_by_name(category_name)

			# perdas do ano anterior com o mês
			cumulative_losses = stats_category.cumulative_losses
			cumulative_losses += stats_category.compensated_losses
			defaults = {'cumulative_losses': cumulative_losses}

			instance, created = self.statistic_model.objects.get_or_create(
				category=category,
				consolidation=self.statistic_model.CONSOLIDATION_MONTHLY,
				institution=institution,
				date=date,
				user=self.user,
				defaults=defaults
			)

			if not created:
				self._update_defaults(instance, defaults)

	def report_generate(self, reports, form):
		if self.is_save_position:
			for month in reports:
				# remove os dados salvos para o meses antes do recalculo.
				self._remove_stats(reports[month])
		self.admin_view.stats = self.get_stats(reports)
		return super().report_generate(reports, form)

	@atomic
	def save(self, reports: BaseReportMonth):
		for month in reports:
			report = reports[month]
			stats = self.admin_view.stats[month]
			self.save_stats(report, stats)

	def get_stats(self, reports: BaseReportMonth):
		"""Gera dados estatísticos"""
		stats_months = collections.OrderedDict()
		for month in reports:
			report = reports[month]
			date = report.get_opts('start_date')
			stats = self.stats_report_class(self.user)
			last_month = month - 1
			stats.cache.set(f'stats_month[{last_month}]', stats_months.get(last_month))
			stats.generate(date=date, results=report.get_results())
			stats_months[month] = stats
		return stats_months

	def update_residual_taxes_month(self, start_date, end_date,
	                                stats_all: Stats,
	                                stats_report: StatsReport):
		"""stats: é o compilado de todos os meses"""
		stats_compile = stats_report.compile_results()
		taxes_qs = self.stats_report_class.taxes_model.objects.filter(user=self.user, total__gt=0)
		darf_min_value = settings.TAX_RATES['darf']['min_value']
		# mantém o histórico de impostos pagos no período
		taxes_paid_qs = taxes_qs.filter(
			paid=True,
			pay_date__gte=start_date,
			pay_date__lte=end_date
		)
		taxes_unpaid = MoneyLC(0)
		# impostos não pagos aparecem no mês para pagamento(repeita o mínimo de R$ 10)
		taxes_unpaid_qs = taxes_qs.filter(
			pay_date__lte=end_date,
			paid=False
		)
		# incluindo valore pagos (readonly)
		for taxes in taxes_paid_qs:
			stats_all.taxes += taxes.taxes_to_pay
			stats_compile.taxes += taxes.taxes_to_pay

		# incluindo os valore não pagos
		for taxes in taxes_unpaid_qs:
			taxes_unpaid += taxes.taxes_to_pay

		if taxes_unpaid and (stats_compile.taxes + taxes_unpaid) >= MoneyLC(darf_min_value):
			stats_all.taxes += taxes_unpaid
			# os impostos residuais ficam congelados nessa data
			taxes_unpaid_qs.update(
				pay_date=end_date,
				paid=True
			)

	def update_residual_taxes(self, stats_all: Stats):
		"""Tem que ser feito quando os impostos já foram calculados
		# por se tratar de imposto residual, deve ser pago quando o total dos impostos
		# for maior ou igual a R$ 10,00
		"""
		for month in self.admin_view.stats:
			stats_month = self.admin_view.stats[month]
			report = self.admin_view.reports[month]
			start_date = report.get_opts('start_date')
			end_date = report.get_opts('end_date')
			self.update_residual_taxes_month(start_date, end_date, stats_all, stats_month)

	def get_context_data(self, context, **kwargs):
		if self.admin_view.reports:
			stats_months = self.stats_report_class.compile_months(
				self.admin_view.stats
			)
			stats_category = collections.OrderedDict([
				('TODOS', stats_all := self.stats_report_class.compile(stats_months))
			])
			# impostos residuais
			self.update_residual_taxes(stats_all)
			category_choices = self.asset_model.category_choices
			category_stocks_name = category_choices[self.asset_model.CATEGORY_STOCK]
			category_fiis_name = category_choices[self.asset_model.CATEGORY_FII]
			# ordenação dos ativos mais importantes manualmente
			if stocks := stats_months.pop(category_stocks_name, None):
				stats_category[category_stocks_name] = stocks
			if fiis := stats_months.pop(category_fiis_name, None):
				stats_category[category_fiis_name] = fiis
			stats_category.update(stats_months)

			context['report']['stats_category'] = stats_category
			context['report']['stock_exempt_profit'] = MoneyLC(settings.TAX_RATES['stocks']['exempt_profit'])
		return context

	def block_bonus_stats(self, context, nodes):
		context = get_context_dict(context)
		return render_to_string('irpf/blocks/blocks.adminx_report_irpf_bonus_stats.html',
		                        context=context)

	def block_report(self, context, nodes):
		context = get_context_dict(context)
		return render_to_string('irpf/adminx_report_irpf_stats.html',
		                        context=context)


class BreadcrumbMonths(BaseAdminPlugin):
	"""Plugin gera um breadcrumb com meses de posição de total de ativos"""
	report_for_model = Negotiation
	position_model = Position

	def init_request(self, *args, **kwargs):
		activate = False
		if model_app_label := kwargs.get('model_app_label'):
			activate = model_app_label == self.report_for_model._meta.label_lower
		return activate

	def setup(self, *args, **kwargs):
		self.report_url = self.get_admin_url("reportirpf", self.report_for_model._meta.label_lower)

	def _get_report_url(self, date):
		query_string = self._get_query_string(date)
		return self.report_url + query_string

	def _get_query_string(self, date: datetime.date):
		"""Querystring gerada para cada item o breadcrumb (mês apurado)"""
		query_string = self.get_query_string(new_params={
			'consolidation': self.position_model.CONSOLIDATION_MONTHLY,
			'dates_0': date.month,
			'dates_1': date.year,
		}, remove=['ts', '_dates', 'position'])
		return query_string

	def _get_position_months(self, reports: BaseReportMonth):
		"""https://stackoverflow.com/questions/37851053/django-query-group-by-month"""
		report = reports.get_last()
		end_date = report.get_opts('end_date')
		if end_date.month == 1:  # janeiro
			return ()
		start_date = datetime.date(end_date.year, 1, 1)
		queryset = self.position_model.objects.filter(
			quantity__gt=0,
			date__gte=start_date,
			date__lte=end_date,
			user=self.user
		).annotate(
			month=ExtractMonth('date')
		).values('month').annotate(
			count=Count("asset_id")
		).order_by('month')
		months = []
		for obj in queryset:
			month, count = obj['month'], obj['count']
			date = datetime.date(end_date.year, month=month, day=1)
			months.append({
				'name': calendar.month_name[month].upper(),
				'url': self._get_report_url(date),
				'active': end_date.month == month,
				'count': count
			})
		return months

	def block_report(self, context, nodes):
		context = get_context_dict(context)
		if self.admin_view.reports:
			if months := self._get_position_months(self.admin_view.reports):
				context['breadcrumb_months'] = months
				nodes.append(render_to_string('irpf/blocks/blocks.adminx_report_irpf_breadcrumb_months.html',
				                              context=context))
	block_report.priority = 1000
