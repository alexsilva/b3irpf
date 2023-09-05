import calendar
import copy
import datetime
from decimal import Decimal
from irpf.models import Asset, Earnings, Bonus, Position, AssetEvent, Subscription
from irpf.report.base import BaseReport
from irpf.report.utils import Event, Assets, Buy
from irpf.utils import range_dates


class NegotiationReport(BaseReport):
	asset_model = Asset
	earnings_model = Earnings
	position_model = Position
	event_model = AssetEvent
	subscription_model = Subscription
	bonus_model = Bonus

	def __init__(self, model, user, **options):
		super().__init__(model, user, **options)
		self.date_start = self.date_end = None
		self._caches = {}

	def get_asset(self, code):
		"""A empresa"""
		try:
			asset = self.asset_model.objects.get(code__iexact=code)
		except self.asset_model.DoesNotExist:
			asset = None
		return asset

	def get_queryset(self, *args, **kwargs):
		return self.model.objects.filter(*args, **kwargs)

	def get_common_qs_options(self, **options) -> dict:
		qs_options = {'user': self.user}
		if asset := options.get('asset'):
			qs_options['asset'] = asset
		if categories := options['categories']:
			qs_options['asset__category__in'] = categories
		return qs_options

	def get_bonus_group_by_date(self, **options) -> dict:
		"""Agrupamento de todos os registros de bônus no intervalo pela data"""
		try:
			return self._caches['bonus_by_date']
		except KeyError:
			by_date = {}
		qs_options = self.get_common_qs_options(**options)
		qs_options['date__gte'] = self.date_start
		qs_options['date__lte'] = self.date_end
		for instance in self.bonus_model.objects.filter(**qs_options):
			by_date.setdefault(instance.date, []).append(instance)
		self._caches['bonus_by_date'] = by_date
		return by_date

	def add_bonus(self, date, history, assets, **options):
		"""Adiciona ações bonificadas na data considerando o histórico"""
		bonus_by_date = self.get_bonus_group_by_date(**options)
		for bonus in bonus_by_date.get(date, ()):
			ticker = bonus.asset.code
			try:
				asset = assets[ticker]
			except KeyError:
				continue
			# ignora os registros que já foram contabilizados na posição
			if asset.is_position_interval(bonus.date):
				continue
			try:
				bonus_event = asset.events['bonus']
			except KeyError:
				bonus_event = asset.events['bonus'] = []

			# total de ativos na data com
			history_assets = history[bonus.date_com]
			history_asset = history_assets[ticker]

			# valor quantidade e valores recebidos de bonificação
			bonus_quantity = history_asset.buy.quantity * (bonus.proportion / 100)
			bonus_base_quantity = int(bonus_quantity)
			bonus_value = bonus_base_quantity * bonus.base_value
			bonus_event.append({
				'instance': bonus,
				'history_asset': history_asset,
				'event': Event("Valor da bonificação",
				               quantity=bonus_quantity,
				               value=bonus_value)
			})
			# rebalanceando a carteira
			asset.buy.quantity += bonus_base_quantity
			asset.buy.total += bonus_value

	def get_subscription_group_by_date(self, **options) -> dict:
		"""Agrupamento de todos os registros de subscrição no intervalo pela data"""
		try:
			return self._caches['subscription_by_date']
		except KeyError:
			by_date = {}
		qs_options = self.get_common_qs_options(**options)
		qs_options['date__gte'] = self.date_start
		qs_options['date__lte'] = self.date_end
		for instance in self.subscription_model.objects.filter(**qs_options):
			by_date.setdefault(instance.date, []).append(instance)
		self._caches['subscription_by_date'] = by_date
		return by_date

	def add_subscription(self, date, assets, history, **options):
		"""Adiciona subscrições ativas para compor a nova quantidade e preço"""
		subscription_group_by_date = self.get_subscription_group_by_date(**options)
		for subscription in subscription_group_by_date.get(date, ()):
			ticker = subscription.asset.code
			try:
				asset = assets[ticker]
			except KeyError:
				continue
			# ignora os registros que já foram contabilizados na posição
			if asset.is_position_interval(subscription.date):
				continue

			# valor quantidade e valores recebidos de bonificação
			subscription_quantity = asset.buy.quantity * (subscription.proportion / 100)
			if (subscription_base_quantity := int(subscription_quantity)) > 0:
				try:
					subscription_event = asset.events['subscription']
				except KeyError:
					subscription_event = asset.events['subscription'] = []

				subscription_value = subscription_base_quantity * subscription.price
				subscription_event.append({
					'history_asset': history[date][ticker],
					'instance': subscription,
					'event': Event("Valor da subscrição",
					               quantity=subscription_base_quantity,
					               value=subscription_value)
				})
				# rebalanceando a carteira
				if subscription.active:
					asset.buy.quantity += subscription_base_quantity
					asset.buy.total += subscription_value

	def get_events_group_by_date(self, **options) -> dict:
		"""Agrupamento de todos os registros de eventos no intervalo pela data"""
		try:
			return self._caches['events_by_date']
		except KeyError:
			by_date = {}
		qs_options = self.get_common_qs_options(**options)
		qs_options['date_com__gte'] = self.date_start
		qs_options['date_com__lte'] = self.date_end
		related_fields = []
		if (field_name := 'asset') in qs_options:
			related_fields.append(field_name)
		queryset = self.event_model.objects.filter(**qs_options)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		for instance in queryset:
			by_date.setdefault(instance.date, []).append(instance)
		self._caches['events_by_date'] = by_date
		return by_date

	def apply_events(self, date, assets, **options):
		"""Eventos de desdobramento/grupamento"""
		events_group_by_date = self.get_events_group_by_date(**options)
		for instance in events_group_by_date.get(date, ()):
			try:
				asset = assets[instance.asset.code]
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
			asset.sell.capital += (instance.quantity * (sell_avg_price - buy_avg_price))

			# ajustando compras
			asset.buy.quantity -= int(instance.quantity)
			asset.buy.tax = asset.buy.quantity * buy_tax_avg_price
			asset.buy.total = asset.buy.quantity * buy_avg_price
		return asset

	def get_earnings_group_by_date(self, **options):
		try:
			return self._caches['earnings_by_date']
		except KeyError:
			by_date = {}
		qs_options = self.get_common_qs_options(**options)
		qs_options['date__gte'] = self.date_start
		qs_options['date__lte'] = self.date_end
		if institution := options.get('institution'):
			qs_options['institution'] = institution.name
		if asset_obj := qs_options.pop('asset', None):
			qs_options['code__iexact'] = asset_obj.code
		queryset = self.earnings_model.objects.filter(**qs_options)
		for instance in queryset:
			by_date.setdefault(instance.date, []).append(instance)
		self._caches['earnings_by_date'] = by_date
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

	def apply_earnings(self, date, assets, **options):
		earnings_group_by_date = self.get_earnings_group_by_date(**options)
		for instance in earnings_group_by_date.get(date, ()):
			try:
				self.calc_earnings(instance, assets[instance.code])
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
		# a data de posição é sempre o último dia do mês ou ano.
		if consolidation == self.position_model.CONSOLIDATION_YEARLY:
			qs_options['date'] = datetime.date.max.replace(year=date.year - 1)
		elif consolidation == self.position_model.CONSOLIDATION_MONTHLY:
			if date.month - 1 > 0:
				max_day = calendar.monthrange(date.year, date.month - 1)[1]
				qs_options['date'] = datetime.date(date.year, date.month - 1, max_day)
			else:
				# começo de ano sempre pega o compilado anual
				qs_options['consolidation'] = self.position_model.CONSOLIDATION_YEARLY
				qs_options['date'] = datetime.date.max.replace(year=date.year - 1)
		else:
			qs_options['date'] = date
		queryset = self.position_model.objects.filter(**qs_options)
		queryset = queryset.exclude(quantity=0)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		return queryset.order_by('date')

	def get_assets_position(self, date, **options) -> dict:
		"""Retorna dados de posição para caculo do período"""
		assets = {}
		queryset = self.get_position_queryset(date, **options)
		for position in queryset:
			ticker = position.asset.code
			asset = Assets(
				ticker=ticker,
				institution=position.institution,
				instance=position.asset,
				position=position,
				buy=Buy(
					quantity=position.quantity,
					total=position.total,
					tax=position.tax,
					date=position.date
				))
			assets[ticker] = asset
		return assets

	def report(self, date_start: datetime.date, date_end: datetime.date, **options):
		options.setdefault('consolidation', self.position_model.CONSOLIDATION_YEARLY)
		options.setdefault('categories', ())
		self.date_start, self.date_end = date_start, date_end
		qs_options = self.get_common_qs_options(**options)
		qs_options['date__gte'] = date_start
		qs_options['date__lte'] = date_end
		if asset_obj := qs_options.pop('asset', None):  # Permite filtrar por empresa (ativo)
			qs_options['code__iexact'] = asset_obj.code
		if institution := options.get('institution'):
			qs_options['institution'] = institution.name
		# cache
		assets = self.get_assets_position(date=date_start, **options)
		assets_queryset = self.get_queryset(**qs_options)
		history = {}

		for date in range_dates(date_start, date_end):  # calcula um dia por vez
			queryset = assets_queryset.filter(date=date)
			for instance in queryset:
				# cálculo de compra e venda
				try:
					asset = assets[instance.code]
				except KeyError:
					asset = Assets(ticker=instance.code,
					               institution=institution,
					               instance=(instance.asset or
					                         asset_obj or
					                         self.get_asset(instance.code)))
					assets[instance.code] = asset
				# ignora os registros que já foram contabilizados na posição
				if asset.is_position_interval(instance.date):
					continue
				asset.items.append(instance)
				self.consolidate(instance, asset)

			# histórico das posições no dia
			if assets:
				history[date] = copy.deepcopy(assets)

			self.apply_earnings(date, assets, **options)
			self.apply_events(date, assets, **options)
			# aplica a bonificação na data do histórico
			self.add_bonus(date, history, assets, **options)
			self.add_subscription(date, assets, history, **options)
		results = []
		for code in assets:
			asset = assets[code]
			results.append({
				'code': code,
				'institution': institution,
				'instance': asset.instance,
				'asset': asset
			})

		results = sorted(results, key=self.results_sorted)

		# reset cache
		self._caches = {}
		return results
