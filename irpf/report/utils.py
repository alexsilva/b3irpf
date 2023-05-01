import decimal

import copy
import datetime
from decimal import Decimal
from collections import OrderedDict
import math


def smart_desc(value) -> Decimal:
	"""Converte 'value' para decimal quanto a parte fracionária for zero"""
	try:
		# 5.0 % 5 == 0, 5.5 % 5 = 0.5
		parts = math.modf(value)
		if parts[0] == 0:
			# converte para inteiro porque o valor não tem fração relevante
			value = Decimal(parts[1])
	except decimal.InvalidOperation:
		...
	return value


class Event:
	def __init__(self, title: str,
	             quantity: Decimal = Decimal(0),
	             value: Decimal = Decimal(0)):
		self.title = title
		self.quantity = quantity
		self.value = value
		self.items = []

	def __str__(self):
		return self.title


class Stats:
	def __init__(self, buy: Decimal = Decimal(0),
	             sell: Decimal = Decimal(0),
	             capital: Decimal = Decimal(0),
	             patrimony: Decimal = Decimal(0),
	             tax: Decimal = Decimal(0),
	             bonus: Event = None):
		self.buy = buy
		self.capital = capital
		self.patrimony = patrimony
		self.tax = tax
		self.sell = sell
		self.bonus = bonus


class Credit(OrderedDict):
	"""credito"""


class Debit(OrderedDict):
	"""Débito"""


class Events(OrderedDict):
	"""Eventos"""


class Buy:
	"""Compas"""

	def __init__(self, quantity: Decimal = Decimal(0),
	             total: Decimal = Decimal(0),
	             tax: Decimal = Decimal(0),
	             date: datetime.date = None):
		self.quantity = quantity
		self.total = total
		self.tax = tax
		self.date = date

	@property
	def avg_price(self):
		"""Preço médio de compra"""
		quantity = int(self.quantity)
		if quantity > 0:
			avg_price = self.total / quantity
		else:
			avg_price = Decimal(0)
		return avg_price

	@property
	def avg_tax(self):
		"""Taxa média por ativo"""
		quantity = int(self.quantity)
		if quantity > 0:
			avg_tax = self.tax / quantity
		else:
			avg_tax = Decimal(0)
		return avg_tax


class Sell:
	"""Vendas"""

	def __init__(self, quantity: Decimal = Decimal(0),
	             total: Decimal = Decimal(0),
	             capital: Decimal = Decimal(0),
	             tax: Decimal = Decimal(0),
	             date: datetime.date = None):
		self.quantity = quantity
		self.capital = capital
		self.total = total
		self.tax = tax
		self.date = date

	@property
	def avg_price(self):
		"""Preço médio de venda"""
		quantity = int(self.quantity)
		if quantity > 0:
			avg_price = self.total / quantity
		else:
			avg_price = Decimal(0)
		return avg_price

	def __bool__(self):
		return bool(self.quantity)


class Period:
	"""Compas menos vendas no intervalo de tempo"""

	def __init__(self, quantity: Decimal = Decimal(0),
	             total: Decimal = Decimal(0),
	             tax: Decimal = Decimal(0),
	             position=None):
		self.quantity = quantity
		self.position = position
		self.total = total
		self.tax = tax

	@property
	def avg_price(self):
		quantity = int(self.quantity)
		if quantity > 0:
			avg_price = self.total / quantity
		else:
			avg_price = Decimal(0)
		return avg_price


class Asset:
	"""Ativos"""

	def __init__(self, ticker,
	             buy: Buy = None,
	             sell: Sell = None,
	             position=None,
	             credit: Credit = None,
	             debit: Debit = None,
	             events: Events = None,
	             institution=None,
	             enterprise=None):
		self.items = []
		self.ticker = ticker
		self.buy = buy
		self.sell = sell
		self.position = position
		self.credit = credit
		self.debit = debit
		self.events = events
		self.institution = institution
		self.enterprise = enterprise

		if buy is None:
			self.buy = Buy()
		if sell is None:
			self.sell = Sell()
		if credit is None:
			self.credit = Credit()
		if debit is None:
			self.debit = Debit()
		if events is None:
			self.events = Events()

	def is_position_interval(self, date: datetime.date):
		"""Se a data presenta uma posição já calculada"""
		return bool(self.position and date <= self.position.date)

	@property
	def period_buy(self) -> Buy:
		"""Compras do perído (sem posição)"""
		buy = Buy()
		for instance in self.items:
			if not instance.is_buy:
				continue
			buy.quantity += instance.quantity
			buy.total += instance.total
			buy.tax += instance.tax
		return buy

	@property
	def period(self) -> Period:
		"""Compras menos vendas no intervalo de tempo"""
		period = Period(quantity=self.buy.quantity,
		                total=self.buy.total,
		                tax=self.buy.tax,
		                position=self.position)
		return period

	def __deepcopy__(self, memo):
		memo[id(self)] = cpy = type(self)(
			ticker=self.ticker,
			buy=copy.deepcopy(self.buy, memo),
			sell=copy.deepcopy(self.sell, memo),
			credit=copy.deepcopy(self.credit, memo),
			debit=copy.deepcopy(self.debit, memo),
			events=copy.deepcopy(self.events, memo),
			institution=self.institution,
			enterprise=self.enterprise,
			position=self.position
		)
		return cpy

	def __iter__(self):
		return iter(self.items)
