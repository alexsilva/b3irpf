import calendar
import datetime
from collections import OrderedDict
from decimal import Decimal

from django.conf import settings

from irpf.models import Asset, Statistic
from irpf.report.cache import Cache
from irpf.report.utils import Stats, MoneyLC


class StatsReport:
	"""Estatísticas pode categoria de ativo"""
	asset_model = Asset
	statistic_model = Statistic

	def __init__(self, user):
		self.user = user
		self.results = OrderedDict()
		self.cache = Cache()

	def _get_statistics(self, date: datetime.date, category: int, **options):
		query = dict(
			consolidation=Statistic.CONSOLIDATION_MONTHLY,
			category=category,
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
		if (stats := self.results.get(category_name)) is None:
			# busca dados no histórico
			statistics: Statistic = self._get_statistics(
				date, self.asset_model.get_category_by_name(category_name),
				**options)
			self.results[category_name] = stats = Stats(instance=statistics)
			# prejuízos acumulados no ano continuam contando em datas futuras
			if statistics:
				stats.cumulative_losses = statistics.cumulative_losses
			# quando os dados de prejuízo ainda não estão salvos usamos o último mês processado
			elif stats_last_month := self.cache.get('stats_last_month', None):
				stats_results = stats_last_month.get_results()
				if category_name in stats_results:
					st = stats_results[category_name]
					cumulative_losses = st.cumulative_losses
					cumulative_losses += st.compensated_losses
					stats.cumulative_losses = cumulative_losses
		return stats

	@staticmethod
	def compile(stats_categories: OrderedDict[int]) -> Stats:
		stats = Stats()
		for stats_category in stats_categories.values():
			stats.update(stats_category)
			stats.cumulative_losses += stats_category.cumulative_losses
			stats.patrimony += stats_category.patrimony
		return stats

	@classmethod
	def compile_months(cls, stats_months: OrderedDict[int], **options) -> Stats:
		stats_category = OrderedDict()
		for month in stats_months:
			stats_month = stats_months[month]
			stats_results = stats_month.get_results()
			for category_name in stats_results:
				value: Stats = stats_results[category_name]
				if (stats := stats_category.get(category_name)) is None:
					stats_category[category_name] = stats = Stats()
				stats.update(value)
				stats.cumulative_losses = value.cumulative_losses
				stats.patrimony = value.patrimony
		return stats_category

	def get_results(self):
		return self.results

	def calc_profits(self, profits, stats: Stats):
		"""Lucro com compensação de prejuízo"""
		if profits and (cumulative_losses := abs(stats.cumulative_losses)):
			# compensação de prejuízos acumulados
			if cumulative_losses >= profits:
				stats.compensated_losses += profits
				profits = Decimal(0)
			else:
				profits -= cumulative_losses
				stats.compensated_losses += cumulative_losses
		return profits

	def generate_taxes(self):
		"""Calcula os impostos a se serem pagos (quando aplicável)"""
		stocks_rates = settings.TAX_RATES['stocks']
		bdrs_rates = settings.TAX_RATES['bdrs']
		fiis_rates = settings.TAX_RATES['fiis']

		category_bdr_name = self.asset_model.category_choices[self.asset_model.CATEGORY_BDR]
		category_stock_name = self.asset_model.category_choices[self.asset_model.CATEGORY_STOCK]

		for category_name in self.results:
			stats: Stats = self.results[category_name]
			category = self.asset_model.get_category_by_name(category_name)
			if category == self.asset_model.CATEGORY_STOCK:
				# vendeu mais que R$ 20.000,00 e teve lucro?
				if stats.sell > MoneyLC(stocks_rates['exempt_profit']):
					if profits := self.calc_profits(stats.profits, stats):
						# compensação de prejuízos de bdrs
						if profits := self.calc_profits(profits, self.results[category_bdr_name]):
							# paga 15% sobre o lucro no swing trade
							stats.taxes = profits * Decimal(stocks_rates['swing_trade'])
			elif category == self.asset_model.CATEGORY_BDR:
				# compensação de prejuízos da categoria
				if profits := self.calc_profits(stats.profits, stats):
					# compensação de prejuízos de ações
					if profits := self.calc_profits(profits, self.results[category_stock_name]):
						# paga 15% sobre o lucro no swing trade
						stats.taxes = profits * Decimal(bdrs_rates['swing_trade'])
			elif category == self.asset_model.CATEGORY_FII:
				if profits := self.calc_profits(stats.profits, stats):
					# paga 20% sobre o lucro no swing trade / day trade
					stats.taxes = profits * Decimal(fiis_rates['swing_trade'])

	def generate(self, date: datetime.date, results: list, **options) -> dict:
		options.setdefault('consolidation', self.statistic_model.CONSOLIDATION_MONTHLY)
		self.results.clear()
		for item in results:
			asset = item['asset']
			# não cadastrado
			instance: Asset = asset.instance
			if instance is None:
				continue

			stats = self._get_stats(instance.category_name, date=date, **options)

			stats.buy += asset.period.buy.total
			stats.sell += asset.sell.total + asset.sell.fraction.total
			stats.tax += asset.period.buy.tax + asset.sell.tax
			stats.profits += asset.sell.profits
			stats.losses += asset.sell.losses

			# prejuízos acumulados
			stats.cumulative_losses += asset.sell.losses

			# total de bônus recebido dos ativos
			stats.bonus += asset.bonus

			# total de todos os períodos
			stats.patrimony += asset.buy.total
		# taxas de período
		self.generate_taxes()
		return self.results
