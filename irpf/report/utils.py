import copy
import datetime


class Earning:
	def __init__(self, title: str, quantity: float = 0.0, value: float = 0.0):
		self.title = title
		self.quantity = quantity
		self.value = value
		self.items = []

	def __str__(self):
		return self.title


class Buy:
	"""Compas"""

	def __init__(self, quantity: float = 0,
	             avg_price: float = 0.0,
	             total: float = 0.0,
	             tax: float = 0.0,
	             date: datetime.date = None):
		self.quantity = quantity
		self.avg_price = avg_price
		self.total = total
		self.tax = tax
		self.date = date


class Sell:
	"""Vendas"""

	def __init__(self, quantity: float = 0,
	             avg_price: float = 0.0,
	             total: float = 0.0,
	             capital: float = 0.0,
	             tax: float = 0.0,
	             date: datetime.date = None):
		self.quantity = quantity
		self.avg_price = avg_price
		self.capital = capital
		self.total = total
		self.tax = tax
		self.date = date

	def __bool__(self):
		return bool(self.quantity)


class Asset:
	"""Ativos"""

	def __init__(self, buy: Buy = None, sell: Sell = None, position=None,
	             earnings: dict = None):
		self.items = []
		self.buy = buy
		self.sell = sell
		self.position = position
		self.earnings = earnings

		if buy is None:
			self.buy = Buy()
		if sell is None:
			self.sell = Sell()
		if earnings is None:
			self.earnings = {}

	def __deepcopy__(self, memo):
		memo[id(self)] = cpy = type(self)(
			buy=copy.deepcopy(self.buy, memo),
			sell=copy.deepcopy(self.sell, memo),
			earnings=copy.deepcopy(self.earnings, memo),
			position=self.position
		)
		return cpy

	def __iter__(self):
		return iter(self.items)


class AssetPosition(Asset):
	"""Posição de ativos"""

	def __init__(self, position, **kwargs):
		super().__init__(buy=Buy(
			quantity=position.quantity,
			avg_price=position.avg_price,
			total=position.total,
			tax=position.tax,
			date=position.date
		), position=position, **kwargs)

	def __deepcopy__(self, memo):
		cpy = type(self)(self.position,
		                 earnings=copy.deepcopy(self.earnings, memo))
		memo[id(self)] = cpy
		return cpy
