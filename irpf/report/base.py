import datetime
from collections import OrderedDict

from irpf.report.cache import Cache


class Base:
	def __init__(self, user, **options):
		self.user = user
		self.options = options
		self.cache = Cache()
		self.results = []

	def get_results(self):
		return self.results

	def get_opts(self, name: str, *args):
		"""Returns a filter option with the name"""
		try:
			return self.options[name]
		except KeyError:
			if not args:
				raise
			return args[0]

	def __bool__(self):
		return bool(self.results)

	def __iter__(self):
		return iter(self.results)

	def __getitem__(self, item):
		return self.results[item]


class BaseReport(Base):
	"""Base report"""
	def __init__(self, user, model, **option):
		super().__init__(user, **option)
		self.model = model

	@staticmethod
	def results_sorted(asset):
		"""Função usada para ordenar resultados do relatório"""
		sort_keys = []
		if asset.instance and asset.instance.category:
			sort_keys.append(asset.instance.category_choices[asset.instance.category])
		sort_keys.append(asset.ticker)
		return sort_keys

	def generate(self, start_date: datetime.date, end_date: datetime.date, **options):
		raise NotImplementedError


class BaseReportMonth(Base):
	"""Um conjunto de relatório dentro de vários meses"""
	report_class: BaseReport = None

	def __init__(self, user, model, **options):
		super().__init__(user, **options)
		self.model = model
		self.start_date: datetime.date = None
		self.end_date: datetime.date = None
		self.results = OrderedDict()

	def set_dates_range(self, months: list):
		"""Configura as datas start e end"""
		if len(months) > 1:
			self.start_date, self.end_date = months[0][0], months[-1][1]
		else:
			self.start_date, self.end_date = months[0]
		return self.start_date, self.end_date

	def generate(self, months_range: list) -> OrderedDict:
		raise NotImplementedError

	def compile(self) -> list:
		"""Tem a função de juntar os dados de todos os meses calculados"""
		raise NotImplementedError

	def get_first(self) -> BaseReport:
		"""Retorna o relatório do primeiro mês"""
		return self.results[self.start_date.month]

	def get_last(self) -> BaseReport:
		"""Retorna o relatório do último mês"""
		return self.results[self.end_date.month]
