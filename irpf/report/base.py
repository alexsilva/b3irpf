import datetime


class BaseReport:
	"""Base report"""
	def __init__(self, model, user, **options):
		self.model = model
		self.user = user
		self.options = options

	def get_opts(self, name: str):
		"""Returns a filter option with the name"""
		return self.options[name]

	@staticmethod
	def results_sorted(item):
		"""Função usada para ordenar resultados do relatório"""
		sort_keys = []
		_instance = item['instance']
		if _instance and _instance.category:
			sort_keys.append(_instance.category_choices[_instance.category])
		sort_keys.append(item['code'])
		return sort_keys

	def report(self, date_start: datetime.date, date_end: datetime.date, **options):
		raise NotImplementedError
