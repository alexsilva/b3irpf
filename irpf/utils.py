import calendar
from datetime import date, timedelta
from typing import Sequence


class MonthYearDates:
	def __init__(self, month: int, year: int):
		self.month = month
		self.year = year

	@property
	def to_date(self):
		"""Retorna uma data para o mês/ano (final do mês)"""
		day = calendar.monthrange(self.year, self.month)[1]
		return date(self.year, self.month, day)

	@property
	def year_range(self):
		"""Data inicial e final do ano"""
		start_date = date.min.replace(year=self.year)
		end_date = date.max.replace(year=start_date.year)
		return start_date, end_date

	@property
	def month_range(self):
		"""Data inicial e final do mês no ano"""
		start_date = date(year=self.year, month=self.month, day=1)
		max_day = calendar.monthrange(start_date.year, start_date.month)[1]
		end_date = date(year=self.year, month=self.month, day=max_day)
		return start_date, end_date

	def get_year_month_range(self, now: date):
		"""Retorna intervalos que representam os meses do ano.
		@type now: É um limitador para o ano corrente.
		"""
		months = []
		year = now.year if self.year > now.year else self.year
		if year < now.year:
			# mês de dezembro do ano anterior
			year_month = 12
		elif year >= now.year:
			# usa o mês atual porque estamos tentando passar para um ano ainda no futuro
			year_month = now.month
		else:
			year_month = self.month
		for month in range(1, year_month + 1):
			max_day = calendar.monthrange(year, month)[1]
			start_date = date(year, month, 1)
			end_date = date(year, month, max_day)
			# nunca ir além da data presente
			if end_date > now:
				end_date = now
			months.append([start_date, end_date])
		return months

	def get_month_range(self, now: date):
		"""now: limite date"""
		if (start_date := date(year=self.year, month=self.month, day=1)) > now:
			start_date = date(year=now.year, month=now.month, day=1)
		max_day = calendar.monthrange(start_date.year, start_date.month)[1]
		if (end_date := date(year=start_date.year, month=start_date.month, day=max_day)) > now:
			end_date = now
		return start_date, end_date


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


def update_defaults(instance, defaults):
	"""Atualiza, se necessário a instância com valores padrão"""
	updated = False
	for key in defaults:
		value = defaults[key]
		if not updated and getattr(instance, key) != value:
			updated = True
		setattr(instance, key, value)
	if updated:
		instance.save(update_fields=list(defaults))
	return updated
