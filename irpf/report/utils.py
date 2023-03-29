import copy
import datetime


def smart_int(value):
	"""Converte 'value' para int quanto a parte decimal for zero"""
	try:
		# 5.0 % 5 == 0, 5.5 % 5 = 0.5
		if value % value == 0:
			# converte para inteiro porque o valor não tem fração relevante
			value = int(value)
	except ZeroDivisionError:
		...
	return value


class Event:
	def __init__(self, title: str,
	             quantity: float = 0.0,
	             value: float = 0.0):
		self.title = title
		self.quantity = quantity
		self.value = value
		self.items = []

	def __str__(self):
		return self.title


class Credit(dict):
	"""credito"""


class Debit(dict):
	"""Débito"""


class Events(dict):
	"""Eventos"""


class Buy:
	"""Compas"""

	def __init__(self, quantity: float = 0,
	             total: float = 0.0,
	             tax: float = 0.0,
	             date: datetime.date = None):
		self.quantity = quantity
		self.total = total
		self.tax = tax
		self.date = date

	@property
	def avg_price(self):
		quantity = int(self.quantity)
		if quantity > 0:
			avg_price = self.total / quantity
		else:
			avg_price = 0.0
		return avg_price


class Sell:
	"""Vendas"""

	def __init__(self, quantity: float = 0,
	             total: float = 0.0,
	             capital: float = 0.0,
	             tax: float = 0.0,
	             date: datetime.date = None):
		self.quantity = quantity
		self.capital = capital
		self.total = total
		self.tax = tax
		self.date = date

	@property
	def avg_price(self):
		if self.quantity > 0:
			avg_price = self.total / self.quantity
		else:
			avg_price = 0.0
		return avg_price

	def __bool__(self):
		return bool(self.quantity)


class Period:
	"""Compas menos vendas no intervalo de tempo"""

	def __init__(self, quantity: float = 0,
	             total: float = 0.0,
	             tax: float = 0.0,
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
			avg_price = 0.0
		return avg_price


class Asset:
	"""Ativos"""

	def __init__(self, ticker,
	             buy: Buy = None, sell: Sell = None,
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

	@property
	def period_buy(self) -> Buy:
		"""Compras do perído (sem posição)"""
		if self.position:
			quantity = int(self.buy.quantity) - int(self.position.quantity)
			total = self.buy.total - self.position.total
			tax = self.buy.tax - self.position.tax
			buy = Buy(quantity=quantity,
			          total=total,
			          tax=tax,
			          date=self.position.date)
		else:
			buy = self.buy
		return buy

	@property
	def period(self) -> Period:
		"""Compras menos vendas no intervalo de tempo"""
		quantity = self.buy.quantity - self.sell.quantity
		total = int(quantity) * self.buy.avg_price
		period = Period(quantity=smart_int(quantity),
		                total=total,
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
