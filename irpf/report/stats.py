from collections import OrderedDict

from irpf.models import Asset, Position
from irpf.report.utils import Stats


class StatsReport:
	"""Estatísticas pode categoria de ativo"""
	def __init__(self, results: list):
		self.results = results

	@staticmethod
	def _get_stats(key: str, data: dict) -> Stats:
		if (stats := data.get(key)) is None:
			data[key] = stats = Stats()
		return stats

	@staticmethod
	def compile(data: dict) -> Stats:
		_stats = Stats()
		for stats in data.values():
			_stats += stats
		return _stats

	def report(self, consolidation=None) -> dict:
		data = OrderedDict()

		if consolidation is None:
			consolidation = Position.CONSOLIDATION_YEARLY

		for item in self.results:
			asset = item['asset']
			# não cadastrado
			instance: Asset = asset.instance
			if instance is None:
				continue

			stats = self._get_stats(instance.category_name, data)

			stats.buy += asset.period.buy.total
			stats.sell += asset.sell.total + asset.sell.fraction.total

			# taxas do período sendo trabalhado
			if consolidation == Position.CONSOLIDATION_YEARLY:
				stats.tax += asset.buy.tax + asset.sell.tax
			else:
				stats.tax += asset.period.buy.tax + asset.sell.tax

			stats.profits += asset.sell.profits
			stats.losses += asset.sell.losses

			# total de todos os períodos
			stats.patrimony += asset.buy.total
		return data
