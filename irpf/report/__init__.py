import decimal

import copy
import datetime
from decimal import Decimal
from django.utils.text import slugify

from irpf.models import Enterprise, Earnings, Bonus, Position, AssetEvent
from irpf.report.utils import Event, Asset, Buy
from irpf.utils import range_dates


class EaningsReport:
	earnings_models = Earnings

	def __init__(self, flow, user, **options):
		self.flow = flow
		self.user = user
		self.options = options

	def get_queryset(self, **options):
		return self.earnings_models.objects.filter(**options)

	def report(self, code, start, end=None, **options):
		qs_options = dict(
			flow__iexact=self.flow,
			user=self.user,
			date__gte=start,
			code__iexact=code
		)
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution.name
		if end is not None:
			qs_options['date__lte'] = end
		earnings = {}
		try:
			qs = self.get_queryset(**qs_options)
			for instance in qs:
				kind = slugify(instance.kind).replace('-', "_")
				try:
					earning = earnings[kind]
				except KeyError:
					earning = earnings[kind] = Event(instance.kind)

				earning.items.append(instance)
				earning.quantity += instance.quantity
				earning.value += instance.total
		except self.earnings_models.DoesNotExist:
			pass
		return earnings


class NegotiationReport:
	earnings_model = Earnings
	enterprise_model = Enterprise
	position_model = Position
	event_model = AssetEvent
	bonus_model = Bonus

	YEARLY, MONTHLY = 1, 2

	def __init__(self, model, user, **options):
		self.model = model
		self.user = user
		self.options = options
		self._caches = {}

	def get_enterprise(self, code):
		"""A empresa"""
		try:
			enterprise = self.enterprise_model.objects.get(code__iexact=code)
		except self.enterprise_model.DoesNotExist:
			enterprise = None
		return enterprise

	def get_queryset(self, *args, **kwargs):
		return self.model.objects.filter(*args, **kwargs)

	def add_bonus(self, date, history, assets, **options):
		"""Adiciona ações bonificadas na data com base no histórico"""
		qs_options = {}
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['enterprise'] = enterprise
		categories = options['categories']
		if categories:
			qs_options['enterprise__category__in'] = categories
		queryset = self.bonus_model.objects.filter(date=date, user=self.user,
		                                           **qs_options)
		for bonus in queryset:
			try:
				asset = assets[bonus.enterprise.code]
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
			history_asset = history_data_com[bonus.enterprise.code]

			# valor quantidade e valores recebidos de bonificação
			bonus_quantity = history_asset.buy.quantity * (bonus.proportion / 100)
			bonus_value = int(bonus_quantity) * bonus.base_value
			bonus_event.append({
				'spec': bonus,
				'asset': asset,
				'history_asset': history_asset,
				'event': Event("Valor da bonificação",
			              quantity=bonus_quantity,
			              value=bonus_value)
			})
			# rebalanceando a carteira
			asset.buy.quantity += bonus_quantity
			asset.buy.total += bonus_value

	def apply_events(self, date, assets, **options):
		"""Eventos de desdobramento/grupamento"""
		qs_options = {}
		related_fields = []
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['enterprise'] = enterprise
			related_fields.append('enterprise')
		categories = options['categories']
		if categories:
			qs_options['enterprise__category__in'] = categories
		event_model = self.event_model
		queryset = event_model.objects.filter(date_com=date, user=self.user, **qs_options)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		for instance in queryset:
			try:
				asset = assets[instance.enterprise.code]
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
				asset.buy.quantity = quantity * instance.factor_to

			elif instance.event == event_model.INPLIT:  # Grupamento
				quantity = asset_period.quantity / instance.factor_from  # correção
				asset.buy.quantity = quantity * instance.factor_to

	def consolidate(self, instance, asset: Asset):
		if instance.is_buy:
			# valores de compras
			asset.buy.tax += instance.tax
			asset.buy.quantity += instance.quantity
			asset.buy.total += ((instance.quantity * instance.price) + instance.tax)
		elif instance.is_sell:
			# valores de venda
			sell_total = ((instance.quantity * instance.price) - instance.tax)

			asset.sell.tax += instance.tax
			asset.sell.quantity += instance.quantity
			asset.sell.total += sell_total

			# preço médio de compras
			sell_avg_price = sell_total / instance.quantity

			# preço médio de compras
			buy_avg_price = asset.buy.avg_price

			# ganho de capital de todas a vendas
			asset.sell.capital += (instance.quantity * (sell_avg_price - buy_avg_price))

			# ajustando compras
			asset.buy.tax -= instance.tax
			asset.buy.quantity -= instance.quantity
			asset.buy.total = int(asset.buy.quantity) * buy_avg_price
		return asset

	def get_earnings_queryset(self, date, **options):
		qs_options = dict(
			user=self.user,
			date=date
		)
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution.name
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['code'] = enterprise.code
		categories = options['categories']
		if categories:
			qs_options['asset__category__in'] = categories
		queryset = self.earnings_model.objects.filter(**qs_options)
		return queryset

	def calc_earnings(self, instance: Earnings, asset: Asset):
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
				asset.sell.quantity += instance.quantity
				asset.buy.quantity -= instance.quantity

	def apply_earnings(self, date, assets, **options):
		queryset = self.get_earnings_queryset(date, **options)
		for instance in queryset:
			try:
				self.calc_earnings(instance, assets[instance.code])
			except KeyError:
				continue

	def get_position_queryset(self, date: datetime.date, **options):
		"""Mota e retorna a queryset de posição"""
		qs_options = {}
		related_fields = []
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution
			related_fields.append('institution')
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['enterprise'] = enterprise
			related_fields.append('enterprise')
		categories = options['categories']
		if categories:
			qs_options['enterprise__category__in'] = categories
		consolidation = options['consolidation']
		if consolidation == self.YEARLY:
			startdate = datetime.date.min.replace(year=date.year - 1)
			enddate = datetime.date.max.replace(year=date.year - 1)
		elif consolidation == self.MONTHLY:
			if date.month - 1 > 0:
				startdate = datetime.date(year=date.year, month=date.month - 1, day=1)
				enddate = date - datetime.timedelta(days=1)
			else:
				enddate = datetime.date.max.replace(year=date.year - 1)
				startdate = datetime.date(year=enddate.year, month=enddate.month, day=1)
		else:
			startdate = enddate = date
		qs_options.setdefault(options.get('startdate_lookup', 'date__gte'), startdate)
		qs_options.setdefault(options.get('enddate_lookup', 'date__lte'), enddate)
		queryset = self.position_model.objects.filter(
			user=self.user,
			**qs_options
		)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		return queryset.order_by('date')

	def get_assets_position(self, date=None, queryset=None, **options):
		"""Retorna dados de posição para caculo do período"""
		assets = {}
		if queryset is None:
			queryset = self.get_position_queryset(date, **options)
		for position in queryset:
			ticker = position.enterprise.code
			asset = Asset(ticker=ticker,
			              institution=position.institution,
			              enterprise=position.enterprise,
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
		enterprise = options.get('enterprise')
		if enterprise:  # Permite filtrar por empresa (ativo)
			qs_options['code'] = enterprise.code
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
					asset = Asset(ticker=instance.code,
					              institution=institution,
					              enterprise=enterprise)
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
			asset.enterprise = asset.enterprise or self.get_enterprise(code)
			results.append({
				'code': code,
				'institution': institution,
				'enterprise': asset.enterprise,
				'asset': asset
			})

		def results_sort_category(item):
			_enterprise = item['enterprise']
			return (_enterprise.category_choices[_enterprise.category]
			        if _enterprise and _enterprise.category else item['code'])

		def results_sort_code(item):
			return item['code']

		results = sorted(results, key=results_sort_code)
		results = sorted(results, key=results_sort_category)
		return results
