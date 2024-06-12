import calendar
import collections
import datetime
import functools
import io
import itertools
import operator
import urllib
import urllib.parse
import django.forms as django_forms
from django.contrib.auth import get_permission_codename
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import get_commands
from django.db.models import Count, Value, Q
from django.db.models.functions import ExtractMonth
from django.db.transaction import atomic
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.safestring import mark_safe
from guardian.shortcuts import get_objects_for_user, assign_perm

from correpy.domain.entities.brokerage_note import BrokerageNote
from correpy.domain.entities.security import Security
from correpy.domain.entities.transaction import Transaction
from correpy.domain.enums import TransactionType
from correpy.parsers.brokerage_notes.base_parser import BaseBrokerageNoteParser
from correpy.parsers.brokerage_notes.parser_factory import ParserFactory
from irpf.fields import CharCodeField
from irpf.funcs import RegexReplace
from irpf.models import Negotiation, Position, Asset, Statistic, BrokerageNote as IrpfBrokerageNote, Institution
from irpf.report import BaseReport
from irpf.report.base import BaseReportMonth
from irpf.report.cache import Cache
from irpf.report.stats import StatsReport, StatsReports
from irpf.report.utils import Assets, Stats, OrderedDictResults, TransactionGroup, MoneyLC
from irpf.utils import update_defaults, get_numbers
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
	guardian_protected = False

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
				if self.guardian_protected:
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
		return update_defaults(instance, defaults)

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


class ReportSavePositionAdminPlugin(ReportBaseAdminPlugin):
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
	brokerage_note_parser_factory = ParserFactory
	brokerage_note_negotiation = Negotiation
	brokerage_note_asset_model = Asset
	brokerage_note_field_update = ()

	def init_request(self, *args, **kwargs):
		return bool(len(self.brokerage_note_field_update))

	def setup(self, *args, **kwargs):
		self._cache = Cache()

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

	@cached_property
	def parser_map(self):
		return dict([(v, k) for k, v in self.brokerage_note_parser_factory.CNPJ_PARSER_MAP.items()])

	def _get_cnpj_from_parser(self, parser_cls: BaseBrokerageNoteParser) -> BaseBrokerageNoteParser:
		return self.parser_map[parser_cls]

	def _get_institution(self, parser: BaseBrokerageNoteParser) -> Institution:
		"""Obtém e retorna a instituição (corretora) com base no 'parser' usado"""
		cnpj = get_numbers(self._get_cnpj_from_parser(type(parser)))
		# remove formatação do texto
		institution = Institution.objects.annotate(
			cnpj_nums=RegexReplace('cnpj',
			                       Value(r'[^\d]'),
			                       Value('')
			                       ),
		).get(
			cnpj_nums=cnpj,
		)
		return institution

	@atomic
	def _parser_and_update(self, instance: IrpfBrokerageNote) -> list[BrokerageNote]:
		"""Atualiza a instância com os dados da nota"""
		notes = []
		try:
			factory = self._get_parser_factory(io.BytesIO(instance.note.read()))
		finally:
			instance.note.seek(0)

		parser = factory.get_parser()
		if instance.institution_id is None:
			instance.institution = self._get_institution(parser)

		for note in parser.parse_brokerage_note():
			for field_name in self.brokerage_note_field_update:
				setattr(instance, field_name, getattr(note, field_name))
			notes.append(note)
		return notes

	def get_asset(self, ticker: str):
		"""O ativo"""
		try:
			asset = self.brokerage_note_asset_model.objects.get(code__iexact=ticker)
		except self.brokerage_note_asset_model.DoesNotExist:
			asset = None
		return asset

	def get_asset_by_name(self, name: str):
		"""Obtém o ativo pela descrição"""
		if (asset := self._cache.get(name, None)) is None:
			try:
				query = functools.reduce(operator.and_, (Q(description__icontains=word.strip())
				                                         for word in name.split() if word.strip()))
				asset = self.brokerage_note_asset_model.objects.get(query)
			except self.brokerage_note_asset_model.DoesNotExist:
				asset = None
			self._cache.set(name, asset)
		return asset

	def _save_transaction(self, transaction: Transaction, instance, **options) -> Negotiation:
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
		if transaction.transaction_type == TransactionType.BUY:
			kind = self.brokerage_note_negotiation.KIND_BUY
		elif transaction.transaction_type == TransactionType.SELL:
			kind = self.brokerage_note_negotiation.KIND_SELL
		else:
			kind = None
		return kind

	def _get_clean_ticker(self, transaction: Transaction):
		"""Retorna o ticker (code) simplificado"""
		if transaction.security.ticker:
			return CharCodeField().to_python(transaction.security.ticker)
		elif asset := self.get_asset_by_name(transaction.security.name):
			return asset.code
		else:
			raise ValueError(f"Não foi possível extrair o 'ticker' do ativo '{transaction.security.name}'")

	def _get_transactions_group(self, note_transactions: list[Transaction]) -> collections.OrderedDict:
		"""Agrupa transações que pertençam ao mesmo ativo (com compra e venda separado)"""
		results = collections.OrderedDict()

		def transaction_group_by(tns: Transaction):
			return self._get_clean_ticker(tns), tns.transaction_type

		for (ticker, transaction_type), items in itertools.groupby(note_transactions, key=transaction_group_by):
			ts = TransactionGroup()
			# soma as quantidade e totais para cada categoria (compra, venda)
			# calcula o preço médio final com base no total de todas as negociações do ativo
			for transaction in items:
				ts.quantity += transaction.amount
				ts.total += transaction.amount * transaction.unit_price

			results[ticker] = Transaction(
				transaction_type=transaction_type,
				amount=ts.quantity,
				unit_price=ts.avg_price,
				security=Security(ticker)
			)
		return results

	def _add_transactions(self, note: BrokerageNote, instance):
		queryset = self.brokerage_note_negotiation.objects.all()
		tax = sum([note.settlement_fee,
		           note.term_fee,
		           note.ana_fee,
		           note.registration_fee,
		           note.taxes,
		           note.emoluments,
		           note.others])

		transactions = self._get_transactions_group(note.transactions)
		paid = sum([(transactions[ticker].amount * transactions[ticker].unit_price)
		            for ticker in transactions])
		for ticker in transactions:
			transaction = transactions[ticker]
			if (kind := self._get_transaction_type(transaction)) is None:
				continue
			# rateio de taxas proporcional ao valor pago
			avg_tax = MoneyLC(tax * ((transaction.amount * transaction.unit_price) / paid))
			qs = queryset.filter(
				date=instance.reference_date,
				code__iexact=ticker,
				kind__iexact=kind,
				quantity=transaction.amount,
				institution_name=instance.institution.name,
				user=self.user
			)
			if self.is_save_transactions and not qs.exists():
				self._save_transaction(
					transaction, instance,
					code=ticker,
					kind=kind,
					defaults={'tax': avg_tax}
				)
			else:
				for negotiation in qs:
					update_defaults(negotiation, {
						'brokerage_note': instance,
						'tax': avg_tax,
					})

	def _get_parser_factory(self, brokerage_note: io.BytesIO) -> ParserFactory:
		"""Retorna o 'factory' de notas"""
		factory = self.brokerage_note_parser_factory(brokerage_note=brokerage_note)
		return factory

	def valid_forms(self, is_valid: bool):
		if is_valid:
			# valida se a nota é única
			self.admin_view.save_forms()
			new_obj = self.admin_view.new_obj
			cleaned_data = self.admin_view.form_obj.cleaned_data
			note_file = cleaned_data['note']
			try:
				factory = self._get_parser_factory(brokerage_note=io.BytesIO(note_file.read()))
			finally:
				note_file.seek(0)

			parser = factory.get_parser()
			if new_obj.institution_id is None:
				try:
					new_obj.institution = self._get_institution(parser)
				except KeyError:
					self.message_user(f"{self.opts.verbose_name} ainda não suportada!", level='error')
					return False
				except Institution.DoesNotExist:
					cnpj = get_numbers(self._get_cnpj_from_parser(type(parser)))
					url = self.get_model_url(Institution, "add")
					params = urllib.parse.urlencode({'cnpj': cnpj})
					url = f"<a href='{url}?{params}'>{cnpj}</a>"
					self.message_user(mark_safe(f"{escape(Institution._meta.verbose_name)} cnpj '{url}' ainda cadastrada!"),
					                  level='error')
					return False
			for note in parser.parse_brokerage_note():
				new_obj.reference_date = note.reference_date
				new_obj.reference_id = note.reference_id
				new_obj.user = self.user

				if new_obj.reference_id and new_obj.reference_date and new_obj.user:
					try:
						new_obj.validate_unique()
					except ValidationError as exc:
						self.message_user('//'.join(exc.message_dict['__all__']), level='error')
						is_valid = False
					break
			else:
				if not (new_obj.reference_id and new_obj.reference_date and new_obj.user):
					self.message_user(f"{self.opts.verbose_name} invalida!", level='error')
					is_valid = False
		return is_valid

	def save_models(self, __):
		if instance := getattr(self.admin_view, "new_obj", None):
			try:
				brokerage_notes = self._parser_and_update(instance)
			except Exception as exc:
				raise exc from None
			else:
				# salva a instância
				retval = __()
				for note in brokerage_notes:
					self._add_transactions(note, instance)
				return retval
		else:
			return __()


class ReportStatsAdminPlugin(ReportBaseAdminPlugin):
	"""Gera dados estatísticos (compra, venda, etc)"""
	stats_reports_class = StatsReports
	statistic_model = Statistic
	position_model = Position
	asset_model = Asset

	def setup(self, *args, **kwargs):
		super().setup(*args, **kwargs)
		# guarda a referência na view
		self.admin_view.stats = None

	def report_generate(self, reports: BaseReportMonth, form):
		if reports:
			if self.is_save_position:
				# remove os dados salvos para o meses antes do recalculo.
				self._invalidate_stats(reports.get_first())
			self.admin_view.stats = self.get_stats(reports)
		return super().report_generate(reports, form)

	def _invalidate_stats(self, report: BaseReport):
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

	def save_stats(self, report: BaseReport, stats: StatsReport):
		"""Salva dados de estatística"""
		institution = report.get_opts('institution', None)
		consolidation = report.get_opts('consolidation')
		end_date = report.get_opts('end_date')

		stats_results = stats.get_results()
		for category_name in stats_results:
			stats_category: Stats = stats_results[category_name]
			category = self.asset_model.get_category_by_name(category_name)
			defaults = {
				'residual_taxes': stats_category.taxes.residual,
				'cumulative_losses': stats_category.cumulative_losses,
				'valid': True
			}
			instance, created = self.statistic_model.objects.get_or_create(
				category=category,
				consolidation=consolidation,
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

	@atomic
	def save(self, reports: BaseReportMonth):
		if not self.admin_view.stats:
			return
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

	def render_to_response(self, response, context, **kwargs):
		if self.admin_view.reports is not None and not (self.admin_view.stats or self.admin_view.reports):
			self.message_user('Nenhum resultado com encontrado para o relatório.',
			                  level='warning')
		return response

	def get_context_data(self, context, **kwargs):
		if self.admin_view.stats:
			# compila os meses de estatística em um conjunto de categorias
			stats_categories = self.admin_view.stats.compile()
			# compilas as categorias de estatística em um objeto 'Stats'
			stats_all = self.admin_view.stats.compile_all(stats_categories)
			stats_results = self.admin_view.stats.compile_results(stats_categories)
			stats_category = OrderedDictResults([('TODOS', stats_all)])

			category_choices = self.asset_model.category_choices
			category_stocks_name = category_choices[self.asset_model.CATEGORY_STOCK]
			category_fiis_name = category_choices[self.asset_model.CATEGORY_FII]
			# ordenação dos ativos mais importantes manualmente
			if stocks := stats_categories.pop(category_stocks_name, None):
				stats_category[category_stocks_name] = stocks
			if fiis := stats_categories.pop(category_fiis_name, None):
				stats_category[category_fiis_name] = fiis
			stats_category.update(stats_categories)
			stats_category_results = collections.OrderedDict([
				('OPERAÇÕES COMUNS', stats_results[0]),
				('FII OU FIAGRO', stats_results[1])
			])
			stats_category.update(stats_category_results)
			context['report']['stats_category'] = stats_category
			context['report']['stock_exempt_profit'] = self.admin_view.stats.tax_rate.stock_exempt_profit
		return context

	def block_bonus_stats(self, context, nodes):
		context = get_context_dict(context)
		return render_to_string('irpf/blocks/blocks.adminx_report_irpf_bonus_stats.html',
		                        context=context)

	def block_report(self, context, nodes):
		context = get_context_dict(context)
		return render_to_string('irpf/adminx_report_irpf_stats.html',
		                        context=context)


class BreadcrumbMonthsAdminPlugin(BaseAdminPlugin):
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
