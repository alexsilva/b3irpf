import calendar
from datetime import date, timedelta
from typing import Sequence


class MonthYearDates:
	def __init__(self, month, year):
		self.month = month
		self.year = year

	@property
	def to_date(self):
		"""Retorna uma data para o mês/ano (final do mês)"""
		day = calendar.monthrange(self.year, self.month)[1]
		return date(self.year, self.month, day)

	@property
	def year_interval(self):
		start = date.min.replace(year=self.year)
		end = date.max.replace(year=start.year)
		return start, end

	def get_year_interval(self, dt: date = None):
		"""dt: limite date"""
		if dt and self.year >= dt.year and dt.month < 12:
			start = date.min.replace(year=dt.year)
			max_day = calendar.monthrange(dt.year, dt.month)[1]
			end = date(year=dt.year, month=dt.month, day=max_day)
		else:
			start, end = self.year_interval
		return start, end

	def get_year_months(self, now: date):
		"""Retorna intervalos que representam os meses do ano
		dt: é um limitado para o ano corrente
		"""
		months = []
		year = now.year if self.year > now.year else self.year
		if year < now.year:
			year_month = 12
		elif year >= now.year:
			year_month = now.month
		else:
			year_month = self.month
		for month in range(1, year_month + 1):
			max_day = calendar.monthrange(year, month)[1]
			months.append([
				date(year, month, 1),
				date(year, month, max_day)
			])
		return months

	@property
	def month_interval(self):
		start = date.min.replace(year=self.year, month=self.month)
		max_day = calendar.monthrange(start.year, start.month)[1]
		end = date(year=self.year, month=self.month, day=max_day)
		return start, end

	def get_month_interval(self, dt: date = None):
		"""dt: limite date"""
		if dt and self.year >= dt.year and self.month > dt.month:
			start = date.min.replace(year=dt.year, month=dt.month)
			max_day = calendar.monthrange(start.year, start.month)[1]
			end = date(year=dt.year, month=dt.month, day=max_day)
		else:
			start, end = self.month_interval
		return start, end


def range_dates(start_of_range: date, end_of_range: date) -> Sequence[date]:
	"""https://stackoverflow.com/questions/993358/creating-a-range-of-dates-in-python"""
	if start_of_range <= end_of_range:
		for x in range(0, (end_of_range - start_of_range).days + 1):
			yield start_of_range + timedelta(days=x)
	else:
		for x in range(0, (start_of_range - end_of_range).days + 1):
			yield start_of_range - timedelta(days=x)


def ticker_validator(ticker: str):
	"""Faz a validação ticker (formato e tamanho)"""
	from irpf.fields import CharCodeField
	return CharCodeField().to_python(ticker)
