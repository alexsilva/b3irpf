import calendar
import datetime
from collections import OrderedDict

from irpf.models import Asset, Statistic
from irpf.report.utils import Stats


class StatsReport:
	"""Estatísticas pode categoria de ativo"""
	asset_model = Asset
	statistic_model = Statistic

	def __init__(self, user, results: list):
		self.user = user
		self.results = results
		self.data = OrderedDict()

	def _get_statistics(self, date: datetime.date, category: int, **options):
		consolidation = Statistic.CONSOLIDATION_MONTHLY
		query = dict(
			category=category,
			consolidation=consolidation,
			user=self.user
		)
		if institution := options.get('institution'):
			query['institution'] = institution

		# a data de posição é sempre o último dia do mês ou ano.
		if date.month - 1 > 0:
			max_day = calendar.monthrange(date.year, date.month - 1)[1]
			query['date'] = datetime.date(date.year, date.month - 1, max_day)
		else:
			max_day = calendar.monthrange(date.year - 1, 12)[1]
			query['date'] = datetime.date(date.year - 1, 12, max_day)
		try:
			instance = self.statistic_model.objects.get(**query)
		except self.statistic_model.DoesNotExist:
			instance = None
		return instance

	def _get_stats(self, category_name: str, date: datetime.date, **options) -> Stats:
		if (stats := self.data.get(category_name)) is None:
			# busca dados no histórico
			statistics: Statistic = self._get_statistics(
				date, self.asset_model.get_category_by_name(category_name),
				**options)
			stats = Stats()
			if statistics:
				# prejuízos acumulados no ano continuam contando em datas futuras
				stats.cumulative_losses += statistics.cumulative_losses
				# prejuízos no mês acumulam para o mês/ano seguinte
				stats.losses += statistics.losses
			self.data[category_name] = stats
		return stats

	@staticmethod
	def compile(data: dict) -> Stats:
		_stats = Stats()
		for stats in data.values():
			_stats += stats
		return _stats

	def report(self, date: datetime.date, **options) -> dict:
		consolidation = options.setdefault('consolidation', self.statistic_model.CONSOLIDATION_YEARLY)
		for item in self.results:
			asset = item['asset']
			# não cadastrado
			instance: Asset = asset.instance
			if instance is None:
				continue

			stats = self._get_stats(instance.category_name, date=date, **options)

			stats.buy += asset.period.buy.total
			stats.sell += asset.sell.total + asset.sell.fraction.total

			# taxas do período sendo trabalhado
			if consolidation == self.statistic_model.CONSOLIDATION_YEARLY:
				stats.tax += asset.buy.tax + asset.sell.tax
			else:
				stats.tax += asset.period.buy.tax + asset.sell.tax

			stats.profits += asset.sell.profits
			stats.losses += asset.sell.losses

			# total de bônus recebido dos ativos
			stats.bonus += asset.bonus

			# total de todos os períodos
			stats.patrimony += asset.buy.total
		return self.data
