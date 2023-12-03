import calendar
import datetime
from collections import OrderedDict
from decimal import Decimal

from django.conf import settings
from django.utils.functional import cached_property

from irpf.models import Asset, Statistic, Taxes
from irpf.report.base import Base, BaseReportMonth, BaseReport
from irpf.report.utils import Stats, MoneyLC


class StatsReport(Base):
	"""Estatísticas pode categoria de ativo"""
	asset_model = Asset
	statistic_model = Statistic
	taxes_model = Taxes

	def __init__(self, user, **options):
		super().__init__(user, **options)
		self.results = OrderedDict()

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
			stats = Stats(instance=statistics)
			# prejuízos acumulados no ano continuam contando em datas futuras
			if statistics:
				stats.cumulative_losses = statistics.cumulative_losses
			# quando os dados de prejuízo ainda não estão salvos usamos o último mês processado
			elif stats_last_month := self.cache.get(f'stats_month[{date.month - 1}]', None):
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
	def compile_months(cls, stats_months: OrderedDict[int], **options) -> OrderedDict:
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

	def compile_results(self) -> Stats:
		"""Compilado de todas as categorias do relatório (mês)"""
		stats = Stats()
		for category_name in self.results:
			stats_category: Stats = self.results[category_name]
			stats.update(stats_category)
			stats.cumulative_losses += stats_category.cumulative_losses
			stats.patrimony += stats_category.patrimony
		return stats

	@cached_property
	def stats_results(self):
		"""Cache armazenado de 'stats' dos resultados"""
		return self.compile_results()

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
							stats.taxes += profits * Decimal(stocks_rates['swing_trade'])
				else:
					# lucro isento no swing trade
					stats.exempt_profit += stats.profits
					stats.profits = MoneyLC(0)
			elif category == self.asset_model.CATEGORY_BDR:
				# compensação de prejuízos da categoria
				if profits := self.calc_profits(stats.profits, stats):
					# compensação de prejuízos de ações
					if profits := self.calc_profits(profits, self.results[category_stock_name]):
						# paga 15% sobre o lucro no swing trade
						stats.taxes += profits * Decimal(bdrs_rates['swing_trade'])
			elif category == self.asset_model.CATEGORY_FII:
				if profits := self.calc_profits(stats.profits, stats):
					# paga 20% sobre o lucro no swing trade / day trade
					stats.taxes += profits * Decimal(fiis_rates['swing_trade'])

	def generate(self, report: BaseReport, **options) -> dict:
		consolidation = report.get_opts("consolidation", None)
		start_date = report.get_opts('start_date')
		options.setdefault('consolidation', consolidation)
		self.options.update(options)

		self.results.clear()

		# cache de todas as categorias (permite a compensação de posições finalizadas)
		for category_name in self.asset_model.category_by_name_choices:
			self.results[category_name] = self._get_stats(category_name, date=start_date, **self.options)

		report_results = report.get_results()
		for asset in report_results:
			# não cadastrado
			instance: Asset = asset.instance
			if instance is None:
				continue

			stats = self._get_stats(instance.category_name, date=start_date, **self.options)

			asset_period = asset.period
			stats.buy += asset_period.buy.total
			stats.sell += asset.sell.total + asset.sell.fraction.total
			stats.tax += asset_period.buy.tax + asset.sell.tax
			stats.profits += asset.sell.profits
			stats.losses += asset.sell.losses

			# prejuízos acumulados
			stats.cumulative_losses += asset.sell.losses

			# total de bônus recebido dos ativos
			stats.bonus.update(asset.bonus)

			# total de todos os períodos
			stats.patrimony += asset.buy.total
		# taxas de período
		self.generate_taxes()
		self.cache.clear()
		return self.results


class StatsReports(Base):
	"""Um conjunto de relatório dentro de vários meses"""
	report_class = StatsReport

	def __init__(self, user, **options):
		super().__init__(user, **options)
		self.start_date: datetime.date = None
		self.end_date: datetime.date = None
		self.results = OrderedDict()

	def generate(self, reports: BaseReportMonth, **options) -> OrderedDict[int]:
		"""Gera dados de estatística para cada mês de relatório"""
		self.start_date = reports.start_date
		self.end_date = reports.end_date

		for month in reports:
			report = reports[month]
			stats = self.report_class(self.user, **options)

			last_month = month - 1
			stats.cache.set(f'stats_month[{last_month}]', self.results.get(last_month))
			stats.generate(report)

			self.results[month] = stats
		return self.results

	def compile(self) -> list:
		"""Tem a função de juntar os dados de todos os meses calculados"""
		raise NotImplementedError

	def get_first(self) -> StatsReport:
		"""Retorna o relatório do primeiro mês"""
		return self.results[self.start_date.month]

	def get_last(self) -> StatsReport:
		"""Retorna o relatório do último mês"""
		return self.results[self.end_date.month]
