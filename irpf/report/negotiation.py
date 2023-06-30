import calendar
import copy
import datetime

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

	YEARLY, MONTHLY = 1, 2

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

	def add_bonus(self, date, history, assets, **options):
		"""Adiciona ações bonificadas na data com base no histórico"""
		qs_options = {}
		asset_instance = options.get('asset')
		if asset_instance:
			qs_options['asset'] = asset_instance
		categories = options['categories']
		if categories:
			qs_options['asset__category__in'] = categories
		queryset = self.bonus_model.objects.filter(date=date, user=self.user,
		                                           **qs_options)
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
		qs_options = dict(
			date_com=date,
			user=self.user
		)
		related_fields = []
		asset_instance = options.get('asset')
		if asset_instance:
			qs_options['asset'] = asset_instance
			related_fields.append('asset')
		categories = options['categories']
		if categories:
			qs_options['asset__category__in'] = categories
		event_model = self.event_model
		queryset = event_model.objects.filter(**qs_options)
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
				avg_price = asset_period.avg_price

				quantity = asset_period.quantity / instance.factor_from  # correção
				fractional, quantity = quantity % 1, int(quantity)

				# reduz do total a fração que será vendida
				asset.buy.total -= fractional * avg_price
				asset.buy.quantity = quantity * instance.factor_to

			elif instance.event == event_model.INPLIT:  # Grupamento
				avg_price = asset_period.avg_price

				quantity = asset_period.quantity / instance.factor_from
				fractional = quantity % 1, int(quantity)

				# reduz do total a fração que será vendida
				asset.buy.total -= fractional * avg_price
				asset.buy.quantity = quantity * instance.factor_to  # correção

	def consolidate(self, instance, asset: Assets):
		if instance.is_buy:
			# valores de compras
			asset.buy.tax += instance.tax
			asset.buy.quantity += instance.quantity
			asset.buy.total += ((instance.quantity * instance.price) + instance.tax)
		elif instance.is_sell:
			# valores de venda
			sell_total = instance.quantity * instance.price

			asset.sell.tax += instance.tax
			asset.sell.quantity += instance.quantity
			asset.sell.total += sell_total

			# preço médio de compras
			sell_avg_price = sell_total - instance.tax
			sell_avg_price = sell_avg_price / instance.quantity

			# preço médio de compras
			buy_avg_price = asset.buy.avg_price

			# ganho de capital de todas a vendas
			asset.sell.capital += (instance.quantity * (sell_avg_price - buy_avg_price))

			# ajustando compras
			asset.buy.quantity -= instance.quantity
			asset_buy_quantity = int(asset.buy.quantity)
			asset.buy.tax = asset_buy_quantity * asset.buy.avg_tax
			asset.buy.total = asset_buy_quantity * buy_avg_price
		return asset

	def get_earnings_queryset(self, date, **options):
		qs_options = dict(
			user=self.user,
			date=date
		)
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution.name
		asset_instance = options.get('asset')
		if asset_instance:
			qs_options['code'] = asset_instance.code
		categories = options['categories']
		if categories:
			qs_options['asset__category__in'] = categories
		queryset = self.earnings_model.objects.filter(**qs_options)
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
				asset.sell.total += instance.total
				# ganho de capital de todas a vendas
				asset.sell.capital += instance.total
			elif kind_slug == instance.BONIFICAO_EM_ATIVOS:
				# calculada por registro manual
				# asset.buy.quantity += instance.quantity
				# asset.buy.total += instance.total
				...
		elif instance.is_debit:
			if kind_slug == instance.FRACAO_EM_ATIVOS:
				# debito do frações
				# asset.sell.quantity += instance.quantity
				# asset.buy.quantity -= instance.quantity
				...

	def apply_earnings(self, date, assets, **options):
		queryset = self.get_earnings_queryset(date, **options)
		for instance in queryset:
			try:
				self.calc_earnings(instance, assets[instance.code])
			except KeyError:
				continue

	def get_position_queryset(self, date: datetime.date, **options):
		"""Mota e retorna a queryset de posição"""
		qs_options = {
			'user': self.user
		}
		related_fields = []
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution
			related_fields.append('institution')
		asset_instance = options.get('asset')
		if asset_instance:
			qs_options['asset'] = asset_instance
			related_fields.append('asset')
		categories = options['categories']
		if categories:
			qs_options['asset__category__in'] = categories
		consolidation = options['consolidation']
		# a data de posição é sempre o último dia do mês ou ano.
		if consolidation == self.YEARLY:
			qs_options['date'] = datetime.date.max.replace(year=date.year - 1)
		elif consolidation == self.MONTHLY:
			if date.month - 1 > 0:
				max_day = calendar.monthrange(date.year, date.month - 1)[1]
				qs_options['date'] = datetime.date(date.year, date.month - 1, max_day)
			else:
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

	def report(self, dtstart, dtend, **options):
		options.setdefault('consolidation', self.YEARLY)
		categories = options.setdefault('categories', ())
		qs_options = {'user': self.user}
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution.name
		asset_instance = options.get('asset')
		if asset_instance:  # Permite filtrar por empresa (ativo)
			qs_options['code'] = asset_instance.code
		if categories:
			qs_options['asset__category__in'] = categories
		# cache
		assets = self.get_assets_position(date=dtstart, **options)
		assets_queryset = self.get_queryset(**qs_options)
		history = {}

		for date in range_dates(dtstart, dtend):  # calcula um dia por vez
			queryset = assets_queryset.filter(date=date)
			for instance in queryset:
				# calculo de compra, venda, boficiação, etc
				try:
					asset = assets[instance.code]
				except KeyError:
					asset = Assets(ticker=instance.code,
					               institution=institution,
					               instance=(instance.asset or
					                         asset_instance or
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

			# aplica a bonificiação na data do histórico
			self.apply_earnings(date, assets, **options)
			self.apply_events(date, assets, **options)
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
