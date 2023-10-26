import datetime
from collections import OrderedDict

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
	def compile(date: datetime.date, reports: OrderedDict[int]):
		raise NotImplementedError

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
