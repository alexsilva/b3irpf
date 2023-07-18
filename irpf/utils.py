import calendar
from datetime import date, timedelta, datetime
from typing import Sequence


class MonthYearDates:
	def __init__(self, month, year):
		self.month = month
		self.year = year

	@property
	def year_interval(self):
		now = datetime.now()
		start = date.min.replace(year=self.year)
		if self.year == now.year and now.month < 12:
			max_day = calendar.monthrange(self.year, now.month)[1]
			end = date(year=self.year, month=now.month, day=max_day)
		else:
			end = date.max.replace(year=start.year)
		return start, end

	@property
	def month_interval(self):
		start = date.min.replace(year=self.year, month=self.month)
		max_day = calendar.monthrange(start.year, start.month)[1]
		end = date(year=self.year, month=self.month, day=max_day)
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
