import calendar
from datetime import date, timedelta
from typing import Sequence


class MonthYearDates:
	def __init__(self, month, year):
		self.month = month
		self.year = year

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
