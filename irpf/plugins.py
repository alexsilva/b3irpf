import calendar
import collections
import datetime
import hashlib
import io
import itertools
import re

import django.forms as django_forms
from correpy.domain.entities.security import Security
from correpy.domain.entities.transaction import Transaction
from correpy.domain.enums import TransactionType
from correpy.parsers.brokerage_notes.b3_parser.b3_parser import B3Parser
from django.conf import settings
from django.contrib.auth import get_permission_codename
from django.core.exceptions import PermissionDenied
from django.core.management import get_commands
from django.db.models import Count
from django.db.models.functions import ExtractMonth
from django.db.transaction import atomic
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from guardian.shortcuts import get_objects_for_user, assign_perm
from irpf.fields import CharCodeField
from irpf.models import Negotiation, Position, Asset, Statistic, Taxes
from irpf.report import BaseReport
from irpf.report.base import BaseReportMonth
from irpf.report.stats import StatsReport, StatsReports
from irpf.report.utils import Assets, Stats, MoneyLC
from xadmin.plugins.utils import get_context_dict
from xadmin.views import BaseAdminPlugin


class GuardianAdminPluginMixin(BaseAdminPlugin):
	guardian_permissions_models = {}

	def set_guardian_object_perms(self, obj, user=None):
		"""Configura permissões de objeto para o usuário da seção"""
		model = type(obj)
		if user is None:
			user = self.user
		for perm_name in self.guardian_permissions_models[model]:
			permission_codename = self.get_model_perm(model, perm_name)
			# tem que ter permissão de modelo para ter permissão de objeto
			if user.has_perm(permission_codename):
				assign_perm(permission_codename, user, obj)
			else:
				raise PermissionDenied(permission_codename)


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
			self.set_guardian_object_perms(new_obj)


class AssignUserAdminPlugin(GuardianAdminPluginMixin):
	"""Salva o usuário da sessão junto a instância do modelo recém-criada"""
	assign_current_user = False

	def init_request(self, *args, **kwargs):
		return self.assign_current_user

	def save_forms(self):
		new_obj = getattr(self.admin_view, "new_obj", None)
		if new_obj and new_obj.user_id is None:
			new_obj.user = self.user

	def save_related(self, __):
		if (new_obj := getattr(self.admin_view, "new_obj", None)) is None:
			return
		for formset in getattr(self.admin_view, "formsets", ()):
			formset.instance = new_obj
			for instance in formset.save(commit=False):
				if instance and hasattr(instance, 'user_id') and instance.user_id is None:
					instance.user = self.user
				instance.save()
				self.set_guardian_object_perms(instance)
			formset.save_m2m()


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


class ReportBaseAdminPlugin(GuardianAdminPluginMixin):
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
			opts = getattr(self.request, 'POST' if self.admin_view.request_method == 'post' else 'GET')
			value = field.to_python(opts.get('position'))
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
			'tax': asset.buy.tax,
			'is_valid': True
		}
		instance, created = self.position_model.objects.get_or_create(
			defaults=defaults,
			date=end_date,
			user=self.user,
			asset=asset.instance,
			institution=institution,
			consolidation=consolidation
		)
		if created:
			self.set_guardian_object_perms(instance)
		else:
			self._update_defaults(instance, defaults)

	def _invalidate_positions(self, report: BaseReport):
		"""Remove todos os dados de posição a partir da data 'end_date' relatório"""
		institution = report.get_opts('institution', None)
		consolidation = report.get_opts('consolidation')
		end_date = report.get_opts('end_date')
		qs_options = dict(
			user=self.user,
			# invalida registros maiores que a data
			date__gt=end_date,
			institution=institution,
			consolidation=consolidation
		)
		if asset := report.get_opts('asset', None):
			qs_options['asset'] = asset
		if categories := report.get_opts('categories', None):
			qs_options['asset__category__in'] = categories
		self.position_model.objects.filter(**qs_options).update(is_valid=False)

	@atomic
	def save(self, reports: BaseReportMonth):
		try:
			if reports:
				self._invalidate_positions(reports.get_first())
			for month in reports:
				report: BaseReport = reports[month]
				# só salva para relatório fechado (mês completo)
				if not report.is_closed:
					continue
				for asset in report.get_results():
					# ignora ativo não cadastrado ou com posição zerada
					if asset.buy.quantity <= 0 or asset.instance is None:
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
			institution_name=instance.institution.name,
			asset=self.get_asset(ticker),
			user=self.user
		)
		defaults = options.setdefault('defaults', {})
		defaults['total'] = transaction.amount * transaction.unit_price
		obj, created = self.brokerage_note_negotiation.objects.get_or_create(**options)
		if created:
			self.set_guardian_object_perms(obj)
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
				institution_name=instance.institution.name,
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
	stats_reports_class = StatsReports
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
		).update(valid=False)

	@atomic
	def save_stats(self, report: BaseReport, stats: StatsReport):
		"""Salva dados de estatística"""
		institution = report.get_opts('institution', None)
		end_date = report.get_opts('end_date')

		stats_results = stats.get_results()
		for category_name in stats_results:
			stats_category: Stats = stats_results[category_name]
			category = self.asset_model.get_category_by_name(category_name)

			# perdas do ano anterior com o mês
			cumulative_losses = stats_category.cumulative_losses
			cumulative_losses += stats_category.compensated_losses
			defaults = {
				'residual_taxes': stats_category.taxes.residual,
				'cumulative_losses': cumulative_losses,
				'valid': True
			}
			instance, created = self.statistic_model.objects.get_or_create(
				category=category,
				consolidation=self.statistic_model.CONSOLIDATION_MONTHLY,
				institution=institution,
				date=end_date,
				user=self.user,
				defaults=defaults
			)
			if created:
				self.set_guardian_object_perms(instance)
			elif self._update_defaults(instance, defaults):
				...
			if stats_category.taxes.paid:
				# configura a data do pagamento do valor de imposto cadastrado pelo usuário
				for taxes in stats_category.taxes.items:
					taxes.pay_date = end_date
					taxes.paid = True
					taxes.save()
				stats_category.taxes.items.clear()
			elif stats_category.taxes.items:
				# imposto cadastrado pelo usuário
				instance.taxes_set.add(*stats_category.taxes.items)

	def report_generate(self, reports: BaseReportMonth, form):
		if self.is_save_position and reports:
			# remove os dados salvos para o meses antes do recalculo.
			self._remove_stats(reports.get_first())
		self.admin_view.stats = self.get_stats(reports)
		return super().report_generate(reports, form)

	def save(self, reports: BaseReportMonth):
		for month in reports:
			report: BaseReport = reports[month]
			# só salva para relatório fechado (mês completo)
			if not report.is_closed:
				continue
			stats = self.admin_view.stats[month]
			self.save_stats(report, stats)

	def get_stats(self, reports: BaseReportMonth):
		"""Gera dados estatísticos"""
		stats = self.stats_reports_class(self.user, reports)
		# gera dados de estatística para cada relatório mensal
		stats.generate()
		return stats

	def get_context_data(self, context, **kwargs):
		if self.admin_view.stats:
			# compila os meses de estatística em um conjunto de categorias
			stats_categories = self.admin_view.stats.compile()
			# compilas as categorias de estatística em um objeto 'Stats'
			stats_all = self.admin_view.stats.compile_all(stats_categories)

			stats_category = collections.OrderedDict([('TODOS', stats_all)])

			category_choices = self.asset_model.category_choices
			category_stocks_name = category_choices[self.asset_model.CATEGORY_STOCK]
			category_fiis_name = category_choices[self.asset_model.CATEGORY_FII]
			# ordenação dos ativos mais importantes manualmente
			if stocks := stats_categories.pop(category_stocks_name, None):
				stats_category[category_stocks_name] = stocks
			if fiis := stats_categories.pop(category_fiis_name, None):
				stats_category[category_fiis_name] = fiis
			stats_category.update(stats_categories)

			context['report']['stats_category'] = stats_category
			context['report']['stock_exempt_profit'] = self.admin_view.stats.tax_rate.darf
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

	def get_media(self, media):
		return media + django_forms.Media(js=(
			"irpf/js/jquery-asBreadcrumbs.min.js",
			"irpf/js/breadcrumbs.start.js",
		), css={
			'screen': ('irpf/css/asBreadcrumbs.min.css',)
		})

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
		qs_options = dict(
			is_valid=True,
			quantity__gt=0,
			consolidation=self.position_model.CONSOLIDATION_MONTHLY,
			date__range=[start_date, end_date],
			user=self.user
		)
		if asset := report.get_opts('asset', None):
			qs_options['asset'] = asset
		if institution := report.get_opts('institution', None):
			qs_options['institution'] = institution
		if categories := report.get_opts('categories', None):
			qs_options['asset__category__in'] = categories
		queryset = self.position_model.objects.filter(
			**qs_options
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
