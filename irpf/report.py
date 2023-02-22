import collections
import copy
import datetime

from django.utils.text import slugify

from irpf.models import Enterprise, Earnings, Bonus, Position
from irpf.utils import range_dates


class Earning:
	def __init__(self, title: str, quantity: float = 0.0, value: float = 0.0):
		self.title = title
		self.quantity = quantity
		self.value = value
		self.items = []

	def __str__(self):
		return self.title


class EaningsReport:
	earnings_models = Earnings

	def __init__(self, flow, user, **options):
		self.flow = flow
		self.user = user
		self.options = options

	def get_queryset(self, **options):
		return self.earnings_models.objects.filter(**options)

	def report(self, code, institution, start, end=None, **options):
		qs_options = dict(
			flow__iexact=self.flow,
			user=self.user,
			institution=institution.name,
			date__gte=start,
			code__iexact=code
		)
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['code'] = enterprise.code
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
					earnings[kind] = earning = Earning(instance.kind)

				earning.items.append(instance)
				earning.quantity += instance.quantity
				earning.value += instance.total
		except self.earnings_models.DoesNotExist:
			pass
		return earnings


class Buy:
	"""Compas"""

	def __init__(self, quantity: float = 0,
	             avg_price: float = 0.0,
	             total: float = 0.0,
	             date: datetime.date = None):
		self.quantity = quantity
		self.avg_price = avg_price
		self.total = total
		self.date = date


class Sell:
	"""Vendas"""

	def __init__(self, quantity: float = 0,
	             avg_price: float = 0.0,
	             total: float = 0.0,
	             capital: float = 0.0,
	             date: datetime.date = None):
		self.quantity = quantity
		self.avg_price = avg_price
		self.capital = capital
		self.total = total
		self.date = date

	def __bool__(self):
		return bool(self.quantity)


class Asset:
	"""Ativos"""
	def __init__(self, buy: Buy = None, sell: Sell = None, position=None):
		self.items = []
		self.buy = buy
		self.sell = sell
		self.position = position

		if buy is None:
			self.buy = Buy()
		if sell is None:
			self.sell = Sell()

	def __deepcopy__(self, memo):
		memo[id(self)] = cpy = type(self)(
			buy=copy.deepcopy(self.buy, memo),
			sell=copy.deepcopy(self.sell, memo),
			position=self.position
		)
		return cpy

	def __iter__(self):
		return iter(self.items)


class AssetPosition(Asset):
	"""Posição de ativos"""
	def __init__(self, position):
		super().__init__(buy=Buy(
			quantity=position.quantity,
			avg_price=position.avg_price,
			total=position.total,
			date=position.date
		), position=position)

	def __deepcopy__(self, memo):
		cpy = type(self)(self.position)
		memo[id(self)] = cpy
		return cpy


class NegotiationReport:
	enterprise_model = Enterprise
	position_model = Position
	bonus_model = Bonus

	buy, sell = "compra", "venda"

	def __init__(self, model, user, **options):
		self.model = model
		self.user = user
		self.options = options
		self.earnings_report = EaningsReport("Credito", user=self.user)

	def get_enterprise(self, code):
		"""A empresa"""
		try:
			enterprise = self.enterprise_model.objects.get(code__iexact=code)
		except self.enterprise_model.DoesNotExist:
			enterprise = None
		return enterprise

	def get_queryset(self, **options):
		return self.model.objects.filter(**options)

	def add_bonus(self, date, history, assets, **options):
		"""Adiciona ações bonificadas na data com base no histórico"""
		qs_options = {}
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['enterprise'] = enterprise
		queryset = self.bonus_model.objects.filter(date=date, user=self.user,
		                                           **qs_options)
		for bonus in queryset:
			asset = assets[bonus.enterprise.code]
			# ignora os registros que já foram contabilizados na posição
			if asset.position and bonus.date < asset.position.date:
				continue

			# total de ativos na data ex
			history_date_ex = history[bonus.date_ex]
			history_asset = history_date_ex[bonus.enterprise.code]

			# valor quantidade e valores recebidos de bonificação
			bonus_quantity = int(history_asset.buy.quantity * (bonus.proportion / 100.0))
			bonus_value = bonus_quantity * bonus.base_value

			# adição dos novos ativos
			asset.buy.quantity += bonus_quantity
			asset.buy.total += bonus_value

			# novo preço médio já com a bonifição
			asset.buy.avg_price = asset.buy.total / float(asset.buy.quantity)

	def consolidate(self, instance, asset: Asset):
		kind = instance.kind.lower()

		if kind == self.buy:
			# valores de compras
			asset.buy.quantity += instance.quantity
			asset.buy.total += ((instance.quantity * instance.price) + instance.tx)
			asset.buy.avg_price = asset.buy.total / float(asset.buy.quantity)
		elif kind == self.sell:
			# valores de venda
			asset.sell.quantity += instance.quantity
			asset.sell.total += (instance.quantity * instance.price)
			asset.sell.avg_price = (asset.sell.total / float(asset.sell.quantity))

			# ganho de capital de todas a vendas
			asset.sell.capital += ((instance.quantity * (instance.price - asset.buy.avg_price)) - instance.tx)

			# novos valores para compra
			asset.buy.quantity -= instance.quantity
			asset.buy.total = asset.buy.quantity * asset.buy.avg_price
		return asset

	def get_position(self, institution, **options):
		"""Retorna dados de posição para caculo do período"""
		assets, qs_options = {}, {}
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['enterprise'] = enterprise
		queryset = self.position_model.objects.filter(
			institution=institution,
			user=self.user,
			**qs_options
		)
		for position in queryset:
			asset = AssetPosition(position=position)
			assets[position.enterprise.code] = asset
		return assets

	def report(self, institution, dtstart, dtend, **options):
		assets = self.get_position(institution, **options)
		history = {}
		qs_options = {}
		enterprise = options.get('enterprise')
		if enterprise:  # Permite filtrar por empresa (ativo)
			qs_options['code'] = enterprise.code
		for dt in range_dates(dtstart, dtend):  # calcula um dia por vez
			queryset = self.get_queryset(date=dt,
			                             institution=institution.name,
			                             position__isnull=True,
			                             user=self.user,
			                             **qs_options)
			for instance in queryset:
				# instance: compra / venda
				try:
					asset = assets[instance.code]
				except KeyError:
					assets[instance.code] = asset = Asset()
				asset.items.append(instance)
				# ignora os registros que já foram contabilizados na posição
				if asset.position and instance.date < asset.position.date:
					continue
				self.consolidate(instance, asset)

			# histórico das posições no dia
			if assets:
				history[dt] = copy.deepcopy(assets)

			# aplica a bonificiação na data do histórico
			self.add_bonus(dt, history, assets, **options)
		results = []
		for code in assets:
			enterprise = self.get_enterprise(code)
			earnings = self.earnings_report.report(code, institution,
			                                       dtstart, dtend,
			                                       **options)
			results.append({
				'code': code,
				'institution': institution,
				'enterprise': enterprise,
				'earnings': earnings,
				'results': assets[code]
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
