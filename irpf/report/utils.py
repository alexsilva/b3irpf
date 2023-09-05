import copy
import datetime
import decimal
from collections import OrderedDict
from decimal import Decimal
import moneyfield.fields


class MoneyLC(moneyfield.fields.MoneyLC):
	"""Default BRL Currency"""
	def __init__(self, amount, currency=None):
		if currency is None:
			currency = 'BRL'
		super().__init__(amount=amount, currency=currency)


def as_int_desc(value) -> Decimal:
	try:
		value = Decimal(int(value))
	except decimal.InvalidOperation:
		...
	return value


def smart_desc(value) -> Decimal:
	"""Converte 'value' para decimal quanto a parte fracionária for zero"""
	# 5.0 % 5 == 0, 5.5 % 5 = 0.5
	if value % 1 == 0:
		# converte para inteiro porque o valor não tem fração relevante
		value = as_int_desc(value)
	return value


class Event:
	def __init__(self, title: str,
	             quantity: Decimal = Decimal(0),
	             value: MoneyLC = MoneyLC(0)):
		self.title = title
		self.quantity = quantity
		self.value = value
		self.items = []

	def __str__(self):
		return self.title


class Stats:
	def __init__(self, buy: Decimal = Decimal(0),
	             sell: MoneyLC = MoneyLC(0),
	             capital: MoneyLC = MoneyLC(0),
	             patrimony: MoneyLC = MoneyLC(0),
	             tax: MoneyLC = MoneyLC(0),
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
	             total: MoneyLC = MoneyLC(0),
	             tax: MoneyLC = MoneyLC(0),
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
			avg_price = MoneyLC(0)
		return avg_price

	@property
	def avg_tax(self):
		"""Taxa média por ativo"""
		quantity = int(self.quantity)
		if quantity > 0:
			avg_tax = self.tax / quantity
		else:
			avg_tax = MoneyLC(0)
		return avg_tax


class SellFrac:
	"""Frações vendidas"""
	def __init__(self, quantity: Decimal = Decimal(0),
	             total: MoneyLC = MoneyLC(0)):
		self.quantity = quantity
		self.total = total


class Sell:
	"""Vendas"""

	def __init__(self, quantity: Decimal = Decimal(0),
	             total: MoneyLC = MoneyLC(0),
	             capital: MoneyLC = MoneyLC(0),
	             tax: MoneyLC = MoneyLC(0),
	             date: datetime.date = None):
		self.quantity = quantity
		self.capital = capital
		self.total = total
		self.tax = tax
		self.date = date
		self.fraction = SellFrac()

	@property
	def avg_price(self):
		"""Preço médio de venda"""
		quantity = int(self.quantity)
		if quantity > 0:
			avg_price = (self.total - self.tax) / quantity
		else:
			avg_price = MoneyLC(0)
		return avg_price

	def __bool__(self):
		return bool(self.quantity)


class Period:
	"""Compras e vendas do intervalo (sem posição)"""

	def __init__(self, buy: Buy = None, sell: Sell = None):
		self.buy = Buy() if buy is None else buy
		self.sell = Sell() if sell is None else sell


class Assets:
	"""Ativos"""

	def __init__(self, ticker,
	             buy: Buy = None,
	             sell: Sell = None,
	             position=None,
	             credit: Credit = None,
	             debit: Debit = None,
	             events: Events = None,
	             institution=None,
	             instance=None):
		self.items = []
		self.ticker = ticker
		self.buy = buy
		self.sell = sell
		self.position = position
		self.credit = credit
		self.debit = debit
		self.events = events
		self.institution = institution
		self.instance = instance

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
	def period(self) -> Period:
		"""Compras e vendas do intervalo (sem posição)"""
		period = Period(sell=self.sell)
		for instance in self.items:
			if not instance.is_buy:
				continue
			period.buy.quantity += instance.quantity
			period.buy.total += instance.total
			period.buy.tax += instance.tax
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
			instance=self.instance,
			position=self.position
		)
		return cpy

	def __iter__(self):
		return iter(self.items)
