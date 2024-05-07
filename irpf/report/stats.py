import calendar
import datetime
from collections import OrderedDict

from django.utils.functional import cached_property

from irpf.models import Asset, Statistic, Taxes, TaxRate
from irpf.report.base import Base, BaseReportMonth, BaseReport
from irpf.report.utils import Stats, MoneyLC, OrderedDictResults


class StatsReport(Base):
	"""Estatísticas pode categoria de ativo"""
	asset_model = Asset
	statistic_model = Statistic
	taxes_model = Taxes

	def __init__(self, user, report: BaseReport, tax_rate: TaxRate, **options):
		super().__init__(user, **options)
		self.report = report
		self.results = OrderedDictResults()
		self.start_date = self.report.get_opts('start_date')
		self.end_date = self.report.get_opts('end_date')
		self.tax_rate = tax_rate

	def _get_statistics(self, date: datetime.date, category: int, **options):
		options.setdefault('consolidation', self.report.get_opts('consolidation'))
		query = dict(
			consolidation=options['consolidation'],
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

	def generate_residual_taxes(self, **options):
		"""Atualiza impostos residuais (aqueles abaixo de R$ 10,00 que devem ser pagos posteriormente)
		"""
		# impostos não pagos aparecem no mês para pagamento(repeita o mínimo de R$ 10)
		taxes_qs = self.taxes_model.objects.filter(
			created_date__range=[self.start_date, self.end_date],
			user=self.user,
			total__gt=0
		)
		for category_name in self.results:
			category = self.asset_model.get_category_by_name(category_name)
			stats_category: Stats = self.results[category_name]

			# impostos cadastrados pelo usuário
			for taxes in taxes_qs.filter(category=category):
				# nesse caso o imposto é só uma anotação para o usuário
				if taxes.paid and not taxes.stats.exists():
					continue
				taxes_to_pay = taxes.taxes_to_pay

				self.stats_results.taxes.value += taxes_to_pay
				stats_category.taxes.value += taxes_to_pay

				self.stats_results.taxes.items.add(taxes)
				stats_category.taxes.items.add(taxes)

		# Se o imposto do mês é maior ou igual ao limite para pagamento (R$ 10)
		if self.stats_results.taxes.total >= self.tax_rate.darf:
			# no fechamento do mês, o imposto residual passa para imposto a pagar (taxes.value) e tem seu valor zerado
			if not self.report.is_closed:
				return
			for category_name in self.results:
				stats_category: Stats = self.results[category_name]
				stats_category.taxes.value += stats_category.taxes.residual
				stats_category.taxes.residual = MoneyLC(0)
				stats_category.taxes.paid = True
		else:
			for category_name in self.results:
				stats_category: Stats = self.results[category_name]
				stats_category.taxes.residual += stats_category.taxes.value
				stats_category.taxes.value = MoneyLC(0)

	def _get_stats(self, category_name: str, date: datetime.date, **options) -> Stats:
		if (stats := self.results.get(category_name)) is None:
			stats = Stats()
			# quando os dados de prejuízo ainda não estão salvos usamos o último mês processado
			if stats_position := options.get('stats_position'):
				if stats_category := stats_position.get(category_name):
					stats.cumulative_losses = stats_category.cumulative_losses
					stats.taxes.residual = stats_category.taxes.residual
					if not stats_category.taxes.paid:
						stats.taxes.items.update(stats_category.taxes.items)
			else:
				# busca dados no histórico
				statistics: Statistic = self._get_statistics(
					date, self.asset_model.get_category_by_name(category_name),
					**options)
				# prejuízos acumulados no ano continuam contando em datas futuras
				if statistics:
					stats.instance = statistics
					stats.cumulative_losses = statistics.cumulative_losses
					stats.taxes.residual = statistics.residual_taxes
					stats.taxes.items.update(list(statistics.taxes_set.all()))
		return stats

	def compile(self) -> Stats:
		"""Compilado de todas as categorias do relatório (mês)"""
		stats = Stats()
		for category_name in self.results:
			stats_category: Stats = self.results[category_name]
			stats.update(stats_category)
			stats.taxes.residual += stats_category.taxes.residual
			stats.cumulative_losses += stats_category.cumulative_losses
			stats.patrimony += stats_category.patrimony
		return stats

	@cached_property
	def stats_results(self):
		"""Cache armazenado de 'stats' dos resultados"""
		return self.compile()

	def calc_profits(self, profits, stats: Stats):
		"""Lucro com compensação de prejuízo"""
		if profits and (cumulative_losses := abs(stats.cumulative_losses)):
			# compensação de prejuízos acumulados
			if cumulative_losses >= profits:
				stats.compensated_losses += profits
				stats.cumulative_losses += profits
				profits = MoneyLC(0)
			else:
				profits -= cumulative_losses
				stats.compensated_losses += cumulative_losses
				stats.cumulative_losses = MoneyLC(0)
		return profits

	def generate_taxes(self):
		"""Calcula os impostos a se serem pagos (quando aplicável)
		Obs:
		Solução de Consulta Cosit nº 166, de 27 de setembro de 2021
		"""
		category_choices = self.asset_model.category_choices
		category_bdr_name = category_choices[self.asset_model.CATEGORY_BDR]
		category_stock_name = category_choices[self.asset_model.CATEGORY_STOCK]

		for category_name in self.results:
			stats: Stats = self.results[category_name]
			category = self.asset_model.get_category_by_name(category_name)
			if category == self.asset_model.CATEGORY_STOCK:
				# vendeu mais que R$ 20.000,00 e teve lucro?
				if stats.sell > self.tax_rate.stock_exempt_profit:
					# compensação de prejuízos da categoria
					if ((profits := self.calc_profits(stats.profits, stats)) and
						# compensação de prejuízos de bdrs
						(profits := self.calc_profits(profits, self.results[category_bdr_name]))):
						# paga 15% sobre o lucro no swing trade
						stats.taxes.value += profits * self.tax_rate.swingtrade.stock_percent
						# desconto do irrf (imposto retido na fonte - 0,005% swing trade)
						stats.taxes.value -= stats.irrf
				else:
					# lucro isento no swing trade
					stats.exempt_profit += stats.profits
					stats.profits = MoneyLC(0)
			elif category == self.asset_model.CATEGORY_BDR:
				# compensação de prejuízos da categoria
				if ((profits := self.calc_profits(stats.profits, stats)) and
					# compensação de prejuízos de ações
					(profits := self.calc_profits(profits, self.results[category_stock_name]))):
					# paga 15% sobre o lucro no swing trade
					stats.taxes.value += profits * self.tax_rate.swingtrade.bdr_percent
			elif category == self.asset_model.CATEGORY_FII:
				if profits := self.calc_profits(stats.profits, stats):
					# paga 20% sobre o lucro no swing trade / day trade
					stats.taxes.value += profits * self.tax_rate.swingtrade.fii_percent
			# cálculo das taxas de subscrição
			elif category == self.asset_model.CATEGORY_STOCK_SUBSCRIPTION_RIGHTS:
				if ((profits := self.calc_profits(stats.profits, stats)) and
					# compensação de prejuízos de ações
					(profits := self.calc_profits(profits, self.results[category_stock_name])) and
					# compensação de prejuízos de bdrs
					(profits := self.calc_profits(profits, self.results[category_bdr_name]))):
					# paga 15% sobre o lucro no swing trade
					stats.taxes.value += profits * self.tax_rate.swingtrade.stock_subscription_percent
					# desconto do irrf (imposto retido na fonte - 0,005% swing trade)
					stats.taxes.value -= stats.irrf
			elif category == self.asset_model.CATEGORY_FII_SUBSCRIPTION_RIGHTS:
				if ((profits := self.calc_profits(stats.profits, stats)) and
					# compensação de prejuízos de ações
					(profits := self.calc_profits(profits, self.results[category_stock_name])) and
					# compensação de prejuízos de bdrs
					(profits := self.calc_profits(profits, self.results[category_bdr_name]))):
					# paga 15% sobre o lucro no swing trade
					stats.taxes.value += profits * self.tax_rate.swingtrade.fii_subscription_percent
					# desconto do irrf (imposto retido na fonte - 0,005% swing trade)
					stats.taxes.value -= stats.irrf

	def generate(self, **options) -> dict:
		consolidation = self.report.get_opts("consolidation", None)
		categories: tuple[int] = self.report.get_opts('categories', ())
		options.setdefault('consolidation', consolidation)
		options.setdefault('stats_position', None)
		self.options.update(options)
		self.results.clear()

		# cache de todas as categorias (permite a compensação de posições finalizadas)
		category_name_choices = self.asset_model.category_by_name_choices
		for category_name in category_name_choices:
			# quando o filtro por categorias está ativado, considera somente as categoria do filtro.
			if categories and category_name_choices[category_name] not in categories:
				continue
			self.results[category_name] = self._get_stats(category_name, date=self.start_date, **self.options)

		report_results = self.report.get_results()
		for asset in report_results:
			# não cadastrado
			instance: Asset = asset.instance
			if instance is None:
				continue

			stats = self._get_stats(instance.category_name, date=self.start_date, **self.options)

			# negociações do mês
			asset_period = asset.period

			# compras e vendas
			stats.buy += asset_period.buy.total
			stats.sell += asset.sell.total + asset.sell.fraction.total

			# taxas e impostos
			stats.tax += asset_period.buy.tax + asset.sell.tax
			stats.irrf += asset.sell.irrf

			# lucro e prejuízos
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
		self.generate_residual_taxes(**self.options)
		self.cache.clear()
		return self.results


class StatsReports(Base):
	"""Um conjunto de relatório dentro de vários meses"""
	report_class = StatsReport
	tax_rate_model = TaxRate

	def __init__(self, user, reports: BaseReportMonth, **options):
		super().__init__(user, **options)
		self.tax_rate_model.cache_clear(user)
		self.start_date: datetime.date = reports.start_date
		self.end_date: datetime.date = reports.end_date
		self.tax_rate: TaxRate = self.tax_rate_model.get_from_date(user, reports.start_date, reports.end_date)
		self.reports: BaseReportMonth = reports
		self.results = OrderedDictResults()

	def generate(self, **options) -> OrderedDict[int]:
		"""Gera dados de estatística para cada mês de relatório"""

		for month in self.reports:
			report = self.reports[month]
			stats = self.report_class(self.user, report, self.tax_rate)

			opts = dict(options)
			if stats_month := self.results.get(month - 1):
				opts['stats_position'] = stats_month.get_results()

			stats.generate(**opts)

			self.results[month] = stats
		return self.results

	def compile(self) -> OrderedDict[str]:
		"""Une os resultados de cada mês para cada categoria em um único objeto 'Stats' por categoria"""
		stats_categories = OrderedDict()
		for month in self.results:
			# cada resultado representa uma categoria de ativo (stock, fii, bdr, etc)
			stats_results = self.results[month].get_results()
			for category_name in stats_results:
				stats_category: Stats = stats_results[category_name]
				if (stats := stats_categories.get(category_name)) is None:
					stats_categories[category_name] = stats = Stats()
				stats.update(stats_category)
				stats.taxes.residual = stats_category.taxes.residual
				stats.cumulative_losses = stats_category.cumulative_losses
				stats.patrimony = stats_category.patrimony
		return stats_categories

	@staticmethod
	def compile_all(stats_categories: OrderedDict[str]) -> Stats:
		"""Une todas as categorias em um único objeto 'Stats'"""
		stats_all = Stats()
		for stats in stats_categories.values():
			stats_all.update(stats)
			stats_all.taxes.residual += stats.taxes.residual
			stats_all.cumulative_losses += stats.cumulative_losses
			stats_all.patrimony += stats.patrimony
		return stats_all

	def compile_results(self, stats_categories: OrderedDict[str]) -> tuple[Stats, Stats]:
		asset_model = self.report_class.asset_model
		category_choices = asset_model.category_choices
		category_fii = [category_choices[asset_model.CATEGORY_FII]]
		stats_all_results, stats_fii_results = Stats(), Stats()
		for category_name in stats_categories:
			stats_category = stats_categories[category_name]
			if category_name in category_fii:
				stats = stats_fii_results
			else:
				stats = stats_all_results
			stats.update(stats_category)
			stats.taxes.residual += stats_category.taxes.residual
			stats.cumulative_losses += stats_category.cumulative_losses
			stats.patrimony += stats_category.patrimony
			# O prejuízo é sempre negativo, enquanto os lucro é positivo.
			stats.taxes_results += (stats_category.losses + stats_category.profits)
		return stats_all_results, stats_fii_results

	def get_first(self) -> Stats:
		"""Retorna o relatório do primeiro mês"""
		return self.results[self.start_date.month]

	def get_last(self) -> Stats:
		"""Retorna o relatório do último mês"""
		return self.results[self.end_date.month]

