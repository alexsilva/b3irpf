import datetime

from irpf.report.cache import Cache


class BaseReport:
	"""Base report"""
	def __init__(self, model, user, **options):
		self.model = model
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
			return args

	@staticmethod
	def compile(date: datetime.date, reports):
		return reports[date.month]

	@staticmethod
	def results_sorted(item):
		"""Função usada para ordenar resultados do relatório"""
		sort_keys = []
		_instance = item['instance']
		if _instance and _instance.category:
			sort_keys.append(_instance.category_choices[_instance.category])
		sort_keys.append(item['code'])
		return sort_keys

	def generate(self, date_start: datetime.date, date_end: datetime.date, **options):
		raise NotImplementedError
