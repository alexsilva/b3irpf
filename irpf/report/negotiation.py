import calendar
import datetime
from collections import OrderedDict
from decimal import Decimal
from irpf.models import Asset, Earnings, Bonus, Position, AssetEvent, Subscription, BonusInfo, \
	AssetConvert
from irpf.report.base import BaseReport, BaseReportMonth
from irpf.report.cache import EmptyCacheError
from irpf.report.utils import Event, Assets, Buy, MoneyLC
from irpf.utils import range_dates


class NegotiationReport(BaseReport):
	asset_model = Asset
	asset_convert_model = AssetConvert
	earnings_model = Earnings
	position_model = Position
	event_model = AssetEvent
	subscription_model = Subscription
	bonus_model = Bonus
	bonus_info_model = BonusInfo

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.assets = {}

	def get_asset(self, code: str) -> Asset:
		"""Retorna o registro do ativo (vindo do banco de dados)"""
		try:
			asset = self.asset_model.objects.get(code__iexact=code)
		except self.asset_model.DoesNotExist:
			asset = None
		return asset

	def get_assets(self, ticker: str, instance: Asset = None, institution=None, **options):
		"""Retorna o registro de asset (agrupamentos de todas as negociações)"""
		try:
			asset = self.assets[ticker]
		except KeyError:
			asset = Assets(ticker=ticker,
			               institution=institution,
			               instance=(instance or self.get_asset(ticker)),
			               **options)
			self.assets[ticker] = asset
		return asset

	def get_queryset(self, **options):
		qs_options = self.get_common_qs_options(**options)
		qs_options['date__range'] = [options['start_date'], options['end_date']]

		# Permite filtrar pelo ativo
		if asset_instance := qs_options.pop('asset', None):
			qs_options['code__iexact'] = asset_instance.code
		if institution := self.options.get('institution'):
			qs_options['institution_name'] = institution.name

		return self.model.objects.filter(**qs_options)

	def get_common_qs_options(self, **options) -> dict:
		qs_options = {'user': self.user}
		if asset_instance := options.get('asset'):
			qs_options['asset'] = asset_instance
		if categories := options['categories']:
			qs_options['asset__category__in'] = categories
		return qs_options

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

	def get_bonus_registry_by_date(self, **options) -> dict:
		"""Agrupamento de todos os registros de bônus no intervalo pela data"""
		try:
			return self.cache.get('bonus_registry_by_date')
		except EmptyCacheError:
			by_date = self.cache.set('bonus_registry_by_date', {})
		qs_options = self.get_common_qs_options(**options)
		qs_options['date_com__range'] = [options['start_date'],
		                                 options['end_date']]
		for instance in self.bonus_model.objects.filter(**qs_options):
			by_date.setdefault(instance.date_com, []).append(instance)
		return by_date

	def get_bonus_by_date(self, **options) -> dict:
		"""Cache dos bônus registrados para a data de incorporação"""
		try:
			return self.cache.get('bonus_by_date')
		except EmptyCacheError:
			by_date = self.cache.set('bonus_by_date', {})
		qs_options = self.get_common_qs_options(**options)
		qs_options['bonus__date__range'] = [options['start_date'],
		                                    options['end_date']]
		if assetft := qs_options.pop('asset', None):
			qs_options['bonus__asset'] = assetft
		if categories := qs_options.pop('asset__category__in', None):
			qs_options['bonus__asset__category__in'] = categories
		queryset = self.bonus_info_model.objects.filter(**qs_options)
		queryset = queryset.select_related("bonus")
		for instance in queryset:
			by_date.setdefault(instance.bonus.date, []).append(instance)
		return by_date

	def add_bonus(self, date, **options):
		"""Adiciona ações bonificadas na data considerando o histórico"""
		bonus_by_date = self.get_bonus_by_date(**options)
		for bonus_info in bonus_by_date.get(date, ()):
			bonus = bonus_info.bonus
			asset = self.get_assets(bonus.asset.code,
			                        instance=bonus.asset,
			                        institution=options.get('institution'))
			# ignora os registros que já foram contabilizados na posição
			if asset.is_position_interval(bonus.date):
				continue

			# rebalanceando a carteira
			if active := bonus_info.quantity > 0:
				asset.buy.quantity += bonus_info.quantity
				asset.buy.total += bonus_info.total
				# total recebido de bônus que precisa ser declarado
				asset.bonus.quantity += bonus_info.quantity
				asset.bonus.value += bonus_info.total

			try:
				events = asset.events['bonus']
			except KeyError:
				events = asset.events['bonus'] = []

			_events = []
			for event in events:
				if event['bonus_info'] == bonus_info:
					event['active'] = active
					_events.append(event)
					break

			# um evento proveniente do registro já existe
			if not _events:
				event = Event("Valor da bonificação",
				              quantity=bonus_info.quantity,
				              value=bonus_info.total)
				events.append({
					'instance': bonus,
					'active': active,
					'bonus_info': bonus_info,
					'event': event
				})

	def registry_bonus(self, date, **options):
		"""Adiciona ações bonificadas na data considerando o histórico"""
		bonus_by_date = self.get_bonus_registry_by_date(**options)
		for bonus in bonus_by_date.get(date, ()):
			asset = self.get_assets(bonus.asset.code,
			                        instance=bonus.asset,
			                        institution=options.get('institution'))
			# ignora os registros que já foram contabilizados na posição
			if asset.is_position_interval(bonus.date):
				continue
			try:
				events = asset.events['bonus']
			except KeyError:
				events = asset.events['bonus'] = []

			# valor e quantidade dos valores recebidos de bonificação
			quantity = asset.buy.quantity * (bonus.proportion / 100)
			bonus_quantity = int(quantity)
			bonus_value = bonus_quantity * bonus.base_value
			defaults = {
				'from_quantity': asset.buy.quantity,
				'from_total': asset.buy.total,
				'quantity': bonus_quantity,
				'total': bonus_value,
				'user': self.user
			}
			bonus_info, created = self.bonus_info_model.objects.get_or_create(
				bonus=bonus,
				defaults=defaults
			)
			if created:
				# sempre é necessário limpar o cache para garantir que esse novo registro vai ser calculado no futuro
				self.cache.remove('bonus_by_date')
			# atualiza os dados sempre que necessário
			elif self._update_defaults(bonus_info, defaults):
				# sempre é necessário limpar o cache para garantir que esse novo registro vai ser calculado no futuro
				self.cache.remove('bonus_by_date')

			event = Event("Valor da bonificação",
			              quantity=quantity,
			              value=bonus_value)
			events.append({
				'instance': bonus,
				'bonus_info': bonus_info,
				'active': False,
				'event': event
			})

	def get_subscription_by_date(self, **options) -> dict:
		"""Agrupamento de todos os registros de subscrição pela 'data com'"""
		try:
			return self.cache.get('subscription_registry_by_date')
		except EmptyCacheError:
			by_date = self.cache.set('subscription_registry_by_date', {})
		qs_options = self.get_common_qs_options(**options)
		qs_options['date__range'] = [options['start_date'], options['end_date']]
		for instance in self.subscription_model.objects.filter(**qs_options):
			by_date.setdefault(instance.date, []).append(instance)
		return by_date

	def add_subscription(self, date, **options):
		"""Adiciona ativos da subscrição na data da incorporação (composição do preço médio)"""
		subscription_by_date = self.get_subscription_by_date(**options)
		for subscription in subscription_by_date.get(date, ()):
			asset = self.get_assets(subscription.asset.code,
			                        instance=subscription.asset,
			                        institution=options.get('institution'))
			# ignora os registros que já foram contabilizados na posição
			if asset.is_position_interval(subscription.date):
				continue

			subscription_assets = OrderedDict()
			for instance in subscription.negotiation_set.all().order_by('date'):
				if (subscription_asset := subscription_assets.get(instance.code)) is None:
					subscription_asset = Assets(ticker=instance.code,
					                            institution=options.get('institution'),
					                            instance=(instance or self.get_asset(instance.code)))
					subscription_assets[instance.code] = subscription_asset

				subscription_asset.items.append(instance)
				self.consolidate(instance, subscription_asset)

			for subscription_asset in subscription_assets.values():
				if subscription_asset.buy.quantity > 0:
					# rebalanceando a carteira
					asset.buy.quantity += subscription_asset.buy.quantity
					asset.buy.total += subscription_asset.buy.total
					asset.items.extend(subscription_asset.items)
					# o ativo deixar se existir porque foi incorporado
					if _subscription_asset := self.assets.get(subscription_asset.ticker):
						# zera o histórico de compras
						_subscription_asset.empty()
					try:
						events = asset.events['subscription']
					except KeyError:
						events = asset.events['subscription'] = []

					event = Event("Subscrição",
					              quantity=subscription_asset.buy.quantity,
					              value=subscription_asset.buy.total)
					events.append({
						'subscription_asset': subscription_asset,
						'instance': subscription,
						'active': True,
						'event': event,
					})

	def get_events_group_by_date(self, **options) -> dict:
		"""Agrupamento de todos os registros de eventos no intervalo pela data"""
		try:
			return self.cache.get('events_by_date')
		except EmptyCacheError:
			by_date = self.cache.set('events_by_date', {})
		qs_options = self.get_common_qs_options(**options)
		qs_options['date_com__range'] = [options['start_date'],
		                                 options['end_date']]
		related_fields = []
		if (field_name := 'asset') in qs_options:
			related_fields.append(field_name)
		queryset = self.event_model.objects.filter(**qs_options)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		for instance in queryset:
			by_date.setdefault(instance.date, []).append(instance)
		return by_date

	def apply_events(self, date, **options):
		"""Eventos de desdobramento/grupamento"""
		events_group_by_date = self.get_events_group_by_date(**options)
		for instance in events_group_by_date.get(date, ()):
			try:
				asset = self.assets[instance.asset.code]
			except KeyError:
				continue
			# posição na data
			if asset.buy.quantity == 0:
				continue
			# ignora os registros que já foram contabilizados na posição
			elif asset.is_position_interval(instance.date_com):
				continue
			elif instance.event == self.event_model.SPLIT:  # Desdobramento
				quantity = asset.buy.quantity / instance.factor_from  # correção
				fraction, quantity = quantity % 1, Decimal(int(quantity))
				# nova quantidade altera o preço médio
				asset.buy.quantity = quantity * instance.factor_to
				# reduz a fração valor da fração com o novo preço médio
				asset.buy.total -= fraction * asset.buy.avg_price

			elif instance.event == self.event_model.INPLIT:  # Grupamento
				quantity = asset.buy.quantity / instance.factor_from
				fraction, quantity = quantity % 1, Decimal(int(quantity))
				# nova quantidade altera o preço médio
				asset.buy.quantity = quantity * instance.factor_to  # correção
				# reduz a fração valor da fração com o novo preço médio
				asset.buy.total -= fraction * asset.buy.avg_price

	def get_asset_convert_group_by_date(self, **options) -> dict:
		"""Agrupamento de todos os registros de eventos de conversão do intervalo pela data"""
		try:
			return self.cache.get('asset_convert_by_date')
		except EmptyCacheError:
			by_date = self.cache.set('asset_convert_by_date', {})
		related_fields = ['origin', 'target']
		qs_options = self.get_common_qs_options(**options)
		qs_options['date__range'] = [options['start_date'], options['end_date']]
		if asset_instance := qs_options.pop('asset', None):
			qs_options['target'] = asset_instance
		if categories := qs_options.pop('asset__category__in', None):
			qs_options['target__category__in'] = categories
		queryset = self.asset_convert_model.objects.filter(**qs_options)
		queryset = queryset.select_related(*related_fields)
		for instance in queryset:
			by_date.setdefault(instance.date, []).append(instance)
		return by_date

	def apply_asset_convert(self, date, **options):
		"""Aplica a conversão de ativo na data"""
		asset_convert_by_date = self.get_asset_convert_group_by_date(**options)
		for convert in asset_convert_by_date.get(date, ()):
			institution = options.get('institution')

			origin, target = convert.origin, convert.target

			asset_origin = self.get_assets(origin.code, instance=origin,
			                               institution=institution)
			asset_target = self.get_assets(target.code, instance=target,
			                               institution=institution)

			# ignora os registros que já foram contabilizados na posição
			if asset_target.is_position_interval(convert.date):
				continue

			origin_buy_avg_price = asset_origin.buy.avg_price
			origin_buy_tax_avg_price = asset_origin.buy.avg_tax

			origin_buy_quantity = asset_origin.buy.quantity
			origin_buy_total = asset_origin.buy.total
			origin_buy_tax = asset_origin.buy.tax

			# factores de conversão
			factor_from = convert.factor_from if convert.factor_from > 0 else 1
			factor_to = convert.factor_to if convert.factor_to > 0 else 1

			convert_limit = convert.limit if convert.limit and 0 < convert.limit < origin_buy_quantity else 0

			if convert_limit and convert_limit < origin_buy_quantity:
				asset_origin.buy.quantity -= convert_limit
				asset_origin.buy.total = asset_origin.buy.quantity * origin_buy_avg_price
				origin_buy_quantity = convert_limit
				origin_buy_total = origin_buy_quantity * origin_buy_avg_price
				origin_buy_tax = origin_buy_quantity * origin_buy_tax_avg_price

			asset_target.buy.quantity += int((origin_buy_quantity / factor_from) * factor_to)
			asset_target.buy.total += origin_buy_total
			asset_target.buy.tax += origin_buy_tax

			# o ativo deixa de existir a partir da data
			if not convert_limit and (asset := self.assets.pop(convert.origin.code)) not in asset_target.conv:
				asset_target.conv.insert(0, asset)

	def consolidate(self, instance, asset: Assets):
		if instance.is_buy:
			# valores de compras
			asset.buy.tax += instance.tax
			asset.buy.quantity += instance.quantity
			asset.buy.total += ((instance.quantity * instance.price) + instance.tax)
		elif instance.is_sell:
			# valores de vendas
			sell_total = instance.quantity * instance.price

			asset.sell.tax += instance.tax
			asset.sell.quantity += instance.quantity
			asset.sell.total += sell_total

			# preço médio de venda
			sell_avg_price = (sell_total - instance.tax) / instance.quantity

			# preço médio de compras
			buy_avg_price = asset.buy.avg_price
			# preço médio de taxas das compras
			buy_tax_avg_price = asset.buy.avg_tax

			# ganho de capital de todas a vendas
			capital = instance.quantity * (sell_avg_price - buy_avg_price)

			# registra lucros e prejuízos
			if capital > MoneyLC(0):
				asset.sell.profits += capital
			else:
				asset.sell.losses += capital

			# ajustando compras
			asset.buy.quantity -= int(instance.quantity)
			asset.buy.tax = asset.buy.quantity * buy_tax_avg_price
			asset.buy.total = asset.buy.quantity * buy_avg_price
		return asset

	def get_earnings_group_by_date(self, **options):
		try:
			return self.cache.get('earnings_by_date')
		except EmptyCacheError:
			by_date = self.cache.set('earnings_by_date', {})
		qs_options = self.get_common_qs_options(**options)
		qs_options['date__range'] = [options['start_date'],
		                             options['end_date']]
		if institution := options.get('institution'):
			qs_options['institution_name'] = institution.name
		if assetft := qs_options.pop('asset', None):
			qs_options['code__iexact'] = assetft.code
		queryset = self.earnings_model.objects.filter(**qs_options)
		for instance in queryset:
			by_date.setdefault(instance.date, []).append(instance)
		return by_date

	def calc_earnings(self, instance: Earnings, asset: Assets):
		kind_slug = instance.kind_slug
		obj = getattr(asset, "credit" if instance.is_credit else "debit")
		try:
			event = obj[kind_slug]
		except KeyError:
			obj[kind_slug] = event = Event(instance.kind)

		event.items.append(instance)
		event.quantity += instance.quantity
		event.value += instance.total

		# ignora os registros que já foram contabilizados na posição
		if asset.is_position_interval(instance.date):
			return
		elif instance.is_credit:
			if kind_slug == instance.LEILAO_DE_FRACAO:
				# as frações influenciam no valor de venda para cálculo do imposto (se for o caso 20mil+)
				asset.sell.fraction.total += instance.total
				asset.sell.fraction.quantity += instance.quantity
			elif kind_slug == instance.BONIFICAO_EM_ATIVOS:
				# calculada por registro manual
				# asset.buy.quantity += instance.quantity
				# asset.buy.total += instance.total
				...
		elif instance.is_debit:
			if kind_slug == instance.FRACAO_EM_ATIVOS:
				# debito do frações
				...

	def apply_earnings(self, date, **options):
		earnings_group_by_date = self.get_earnings_group_by_date(**options)
		for instance in earnings_group_by_date.get(date, ()):
			try:
				self.calc_earnings(instance, self.assets[instance.code])
			except KeyError:
				continue

	def get_position_queryset(self, date: datetime.date, **options):
		"""Monta e retorna a queryset de posição"""
		related_fields = []
		qs_options = self.get_common_qs_options(**options)
		if consolidation := options['consolidation']:
			qs_options['consolidation'] = consolidation
		if institution := options.get('institution'):
			qs_options['institution'] = institution
			related_fields.append('institution')
		if (field_name := 'asset') in qs_options:
			related_fields.append(field_name)

		if date.month - 1 > 0:
			max_day = calendar.monthrange(date.year, date.month - 1)[1]
			qs_options['date'] = datetime.date(date.year, date.month - 1, max_day)
		else:
			max_day = calendar.monthrange(date.year - 1, 12)[1]
			qs_options['date'] = datetime.date(date.year - 1, 12, max_day)

		queryset = self.position_model.objects.filter(is_valid=True, **qs_options)
		queryset = queryset.exclude(quantity=0)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		return queryset.order_by('date')

	def get_assets_position(self, date: datetime.date, **options) -> dict:
		"""Retorna dados de posição para caculo do período"""
		positions = {}
		# usa a posição do mês anterior em cache (sempre calculada para relatório anual).
		if assets_position := options.get('assets_position'):
			for asset in assets_position:
				assets = Assets(
					ticker=asset.ticker,
					institution=asset.institution,
					instance=asset.instance,
					position=asset.position,
					buy=Buy(
						quantity=asset.buy.quantity,
						total=asset.buy.total,
						tax=asset.buy.tax
					)
				)
				positions[assets.ticker] = assets
		else:
			# usa posições salvas para relatórios mensais
			queryset = self.get_position_queryset(date, **options)
			for position in queryset:
				assets = Assets(
					ticker=position.asset.code,
					institution=position.institution,
					instance=position.asset,
					position=position,
					buy=Buy(
						quantity=position.quantity,
						total=position.total,
						tax=position.tax
					))
				positions[assets.ticker] = assets
		return positions

	def generate(self, start_date: datetime.date, end_date: datetime.date, **options):
		self.options.setdefault('start_date', start_date)
		self.options.setdefault('end_date', end_date)
		self.options.setdefault('consolidation', self.position_model.CONSOLIDATION_MONTHLY)
		self.options.setdefault('assets_position', None)
		self.options.setdefault('categories', ())
		self.options.update(options)

		# cache
		self.assets = self.get_assets_position(date=start_date, **self.options)
		assets_queryset = self.get_queryset(**self.options)

		institution = self.options.get('institution')
		asset_instance = self.options.get('asset')

		for date in range_dates(start_date, end_date):  # calcula um dia por vez
			self.apply_asset_convert(date, **self.options)
			# inclusão de bônus considera a data da incorporação
			self.add_bonus(date, **self.options)
			# inclusão de subscrições na data de incorporação
			self.add_subscription(date, **self.options)

			queryset = assets_queryset.filter(date=date)
			for instance in queryset:
				asset = self.get_assets(instance.code,
				                        instance=instance.asset or asset_instance,
				                        institution=institution)
				# ignora os registros que já foram contabilizados na posição
				if asset.is_position_interval(instance.date):
					continue
				asset.items.append(instance)
				# cálculo de compra e venda
				self.consolidate(instance, asset)

			self.apply_earnings(date, **self.options)
			self.apply_events(date, **self.options)
			# cria um registro de bônus para os ativos do dia
			self.registry_bonus(date, **self.options)

		# limpeza de resultados anteriores
		self.results.clear()
		self.results.extend(self.assets.values())
		self.results.sort(key=self.results_sorted)
		# reset cache
		self.cache.clear()
		return self.results


class NegotiationReportMonth(BaseReportMonth):
	"""Relatório de todos os meses de um range"""
	report_class = NegotiationReport

	def generate(self, months_range: list, **options) -> OrderedDict:
		"""Gera um relatório para cada mês
		months: é uma lista com tuplas contendo meses
			[(start_date, end_date, ...)]
		"""
		self.options.update(**options)

		for start_date, end_date in months_range:
			report = self.report_class(self.user, self.model)
			opts = dict(self.options, consolidation=self.report_class.position_model.CONSOLIDATION_MONTHLY)

			# relatório do mês anterior (usado como posição para o mês atual)
			if report_month := self.results.get(start_date.month - 1):
				opts['assets_position'] = report_month.get_results()

			report.generate(start_date, end_date, **opts)

			self.results[start_date.month] = report
		# datas inicial e final do range
		self.set_dates_range(months_range)
		return self.results

	def compile(self) -> list:
		"""Junta os relatórios de todos os meses como se fossem um só"""
		if len(self.results) == 1:
			return self.get_last().get_results()
		assets = {}
		for month in self.results:
			for _asset in self.results[month]:
				if (asset := assets.get(_asset.ticker)) is None:
					asset = Assets(ticker=_asset.ticker,
					               position=_asset.position,
					               instance=_asset.instance)
					assets[_asset.ticker] = asset
				asset.update(_asset)
				asset.buy = _asset.buy
		return sorted(assets.values(), key=self.report_class.results_sorted)
