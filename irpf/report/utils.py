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
	if not value:
		value = Decimal(0)
	elif value % 1 == 0:
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

	def __add__(self, event):
		"""Acrescenta os dados de outro objeto event"""
		self.quantity += event.quantity
		self.value += event.value
		return self

	def __bool__(self):
		return bool(self.quantity)

	def __str__(self):
		return self.title


class Stats:
	def __init__(self, buy: MoneyLC = MoneyLC(0),
	             sell: MoneyLC = MoneyLC(0),
	             profits: MoneyLC = MoneyLC(0),
	             losses: MoneyLC = MoneyLC(0),
	             cumulative_losses: MoneyLC = MoneyLC(0),
	             patrimony: MoneyLC = MoneyLC(0),
	             tax: MoneyLC = MoneyLC(0),
	             bonus: Event = None):
		self.buy = buy
		self.sell = sell
		self.profits = profits  # lucros
		self.losses = losses  # prejuízos
		self.cumulative_losses = cumulative_losses  # prejuízos acumulados
		self.patrimony = patrimony
		self.tax = tax
		self.bonus = Event("Bonificação") if bonus is None else bonus
		self.taxes = MoneyLC(0)

		# prejuízos compensados
		self.compensated_losses = MoneyLC(0)

	def update(self, stats):
		"""Acrescenta os dados de outro objeto stats"""
		self.buy += stats.buy
		self.sell += stats.sell
		self.profits += stats.profits
		self.losses += stats.losses
		self.tax += stats.tax
		self.bonus += stats.bonus
		self.taxes += stats.taxes
		self.compensated_losses += stats.compensated_losses
		return self

	def __bool__(self):
		return bool(self.buy or self.sell)


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
	             tax: MoneyLC = MoneyLC(0)):
		self.quantity = quantity
		self.total = total
		self.tax = tax

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

	def __bool__(self):
		return bool(self.quantity)


class SellFrac:
	"""Frações vendidas"""
	def __init__(self, quantity: Decimal = Decimal(0),
	             total: MoneyLC = MoneyLC(0)):
		self.quantity = quantity
		self.total = total

	def update(self, sellfrac):
		self.quantity += sellfrac.quantity
		self.total += sellfrac.total


class Sell:
	"""Vendas"""

	def __init__(self, quantity: Decimal = Decimal(0),
	             total: MoneyLC = MoneyLC(0),
	             profits: MoneyLC = MoneyLC(0),
	             losses: MoneyLC = MoneyLC(0),
	             tax: MoneyLC = MoneyLC(0)):
		self.quantity = quantity
		self.profits = profits  # lucros
		self.losses = losses  # prejuízos
		self.total = total  # total vendas
		self.tax = tax  # taxas
		self.fraction = SellFrac()

	def update(self, sell):
		self.quantity += sell.quantity
		self.total += sell.total
		self.profits += sell.profits
		self.losses += sell.losses
		self.tax += sell.tax
		self.fraction.update(sell.fraction)

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

	def __init__(self, ticker: str,
	             buy: Buy = None,
	             sell: Sell = None,
	             position=None,
	             credit: Credit = None,
	             debit: Debit = None,
	             events: Events = None,
	             bonus: Event = None,
	             institution=None,
	             instance=None):
		self.items = []
		self.ticker = ticker
		self.buy = Buy() if buy is None else buy
		self.sell = Sell() if sell is None else sell
		self.credit = Credit() if credit is None else credit
		self.debit = Debit() if debit is None else debit
		self.events = Events() if events is None else events
		self.bonus = Event("Total recebido") if bonus is None else bonus
		self.position = position
		self.institution = institution
		self.instance = instance

	def is_position_interval(self, date: datetime.date):
		"""Se a data presenta uma posição já calculada"""
		return bool(date and self.position and date <= self.position.date)

	def update(self, asset):
		"""Atualiza os dados desse asset com outro"""
		self.sell.update(asset.sell)
		self.bonus += asset.bonus
		self.events.update(asset.events)
		self.credit.update(asset.credit)
		self.debit.update(asset.debit)
		return self

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
