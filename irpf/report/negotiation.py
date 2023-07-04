import calendar
import copy
import datetime
from decimal import Decimal
from irpf.models import Asset, Earnings, Bonus, Position, AssetEvent
from irpf.report.base import BaseReport
from irpf.report.utils import Event, Assets, Buy
from irpf.utils import range_dates


class NegotiationReport(BaseReport):
	asset_model = Asset
	earnings_model = Earnings
	position_model = Position
	event_model = AssetEvent
	bonus_model = Bonus

	def __init__(self, model, user, **options):
		super().__init__(model, user, **options)
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

	def add_bonus(self, date, history, assets, **options):
		"""Adiciona ações bonificadas na data considerando o histórico"""
		qs_options = self.get_common_qs_options(**options)
		queryset = self.bonus_model.objects.filter(date=date, **qs_options)
		for bonus in queryset:
			try:
				asset = assets[bonus.asset.code]
			except KeyError:
				continue
			# ignora os registros que já foram contabilizados na posição
			if asset.is_position_interval(bonus.date):
				continue
			try:
				bonus_event = asset.events['bonus']
			except KeyError:
				bonus_event = asset.events['bonus'] = []

			# total de ativos na data ex
			history_data_com = history[bonus.data_com]
			history_asset = history_data_com[bonus.asset.code]

			# valor quantidade e valores recebidos de bonificação
			bonus_quantity = history_asset.buy.quantity * (bonus.proportion / 100)
			bonus_base_quantity = int(bonus_quantity)
			bonus_value = bonus_base_quantity * bonus.base_value
			bonus_event.append({
				'spec': bonus,
				'asset': asset,
				'history_asset': history_asset,
				'event': Event("Valor da bonificação",
				               quantity=bonus_quantity,
				               value=bonus_value)
			})
			# rebalanceando a carteira
			asset.buy.quantity += bonus_base_quantity
			asset.buy.total += bonus_value

	def apply_events(self, date, assets, **options):
		"""Eventos de desdobramento/grupamento"""
		qs_options = self.get_common_qs_options(**options)
		related_fields = []
		if (field_name := 'asset') in qs_options:
			related_fields.append(field_name)
		event_model = self.event_model
		queryset = event_model.objects.filter(date_com=date, **qs_options)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		for instance in queryset:
			try:
				asset = assets[instance.asset.code]
			except KeyError:
				continue
			# posição na data
			asset_period = asset.period
			if asset_period.quantity == 0:
				continue
			# ignora os registros que já foram contabilizados na posição
			elif asset.is_position_interval(instance.date_com):
				continue
			elif instance.event == event_model.SPLIT:  # Desdobramento
				quantity = asset_period.quantity / instance.factor_from  # correção
				fraction, quantity = quantity % 1, Decimal(int(quantity))
				# nova quantidade altera o preço médio
				asset.buy.quantity = quantity * instance.factor_to
				# reduz a fração valor da fração com o novo preço médio
				asset.buy.total -= fraction * asset.buy.avg_price

			elif instance.event == event_model.INPLIT:  # Grupamento
				quantity = asset_period.quantity / instance.factor_from
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

			# preço médio de compras
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

	def get_earnings_queryset(self, date, **options):
		qs_options = self.get_common_qs_options(**options)
		if institution := options.get('institution'):
			qs_options['institution'] = institution.name
		if asset_obj := qs_options.pop('asset', None):
			qs_options['code__iexact'] = asset_obj.code
		queryset = self.earnings_model.objects.filter(date=date, **qs_options)
		return queryset

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
		queryset = self.get_earnings_queryset(date, **options)
		for instance in queryset:
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

	def get_assets_position(self, date=None, queryset=None, **options):
		"""Retorna dados de posição para caculo do período"""
		assets = {}
		if queryset is None:
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
		qs_options = self.get_common_qs_options(**options)
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
				# calculo de compra, venda, boficiação, etc
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
		return results