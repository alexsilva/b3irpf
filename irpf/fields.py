import decimal

import datetime
import re
from decimal import Decimal
import moneyfield
import moneyfield.fields
from django.db import models

from correpy.domain.entities.security import BDR_TICKER_PATTERN


class MoneyField(moneyfield.MoneyField):
	"""Cria um campo moneyfield sem o proxy field_amount e currency fixo"""
	def __init__(self, *args, **kwargs):
		kwargs.setdefault("amount_proxy", False)
		kwargs.setdefault('amount_default', Decimal(0))
		kwargs.setdefault('currency', 'BRL')
		super().__init__(*args, **kwargs)

	def formfield(self, **kwargs):
		field = super().formfield(**kwargs)
		if isinstance(field.widget, moneyfield.fields.MoneyWidget):
			field.widget.template_name = "irpf/widgets/money_widget.html"
		return field


class DateField(models.DateField):
	DATE_FORMAT = "%d/%m/%Y"

	def to_python(self, value):
		if value and isinstance(value, str):
			try:
				value = datetime.datetime.strptime(value, self.DATE_FORMAT)
			except ValueError:
				pass
		value = super().to_python(value)
		return value


class CharCodeField(models.CharField):
	TICKER_PATTERN = (
		re.compile(BDR_TICKER_PATTERN),
		re.compile("([A-Z-0-9]{4})(2|3|4|5|6|10|11|12)")
	)

	@classmethod
	def _get_simple_ticker(cls, ticker):
		"""Retorna o ticker (code) sem a parte fracionária"""
		for pattern in cls.TICKER_PATTERN:
			if result := pattern.search(ticker):
				return result[0]
		raise ValueError(f"unknown format ticker '{ticker}'")

	def to_python(self, value):
		value = super().to_python(value)
		if isinstance(value, str):
			# removes the fractional portion of the code.
			value = self._get_simple_ticker(value)
		return value


class CharCodeNameField(models.CharField):
	def __init__(self, *args, **kwargs):
		self._is_code = kwargs.pop("is_code", False)
		super().__init__(*args, **kwargs)

	def to_python(self, value):
		value = super().to_python(value)
		if isinstance(value, str):
			# removes the fractional portion of the code.
			try:
				code, name = value.split('-', 1)
			except ValueError:
				value = value.strip()
				if self._is_code:
					value = CharCodeField().to_python(value)
			else:
				value = name.strip()
				if self._is_code:
					value = CharCodeField().to_python(code)
		return value


class DateNoneField(DateField):

	@staticmethod
	def _get_date_or_none(value):
		if value and value.strip() == "-":
			value = None
		return value

	def to_python(self, value):
		value = self._get_date_or_none(value)
		return super().to_python(value)

	def get_prep_value(self, value):
		value = self._get_date_or_none(value)
		return super().get_prep_value(value)


class DecimalBRField(models.DecimalField):
	def _get_safe_value(self, value):
		if isinstance(value, str):
			try:
				value = Decimal(value.replace(',', '.'))
			except (decimal.InvalidOperation, ValueError):
				value = Decimal(0)
		return value

	def get_prep_value(self, value):
		value = self._get_safe_value(value)
		return super().get_prep_value(value)

	def to_python(self, value):
		value = self._get_safe_value(value)
		return super().to_python(value)


class FloatBRField(models.FloatField):
	def _get_safe_value(self, value):
		if isinstance(value, str):
			value = float(value.replace(',', '.'))
		return value

	def get_prep_value(self, value):
		value = self._get_safe_value(value)
		return super().get_prep_value(value)

	def to_python(self, value):
		value = self._get_safe_value(value)
		return super().to_python(value)


class DecimalZeroField(models.DecimalField):
	def _get_safe_value(self, value):
		if isinstance(value, str):
			try:
				value = Decimal(value)
			except (decimal.InvalidOperation, ValueError):
				value = Decimal(0)
		return value

	def get_prep_value(self, value):
		value = self._get_safe_value(value)
		return super().get_prep_value(value)

	def to_python(self, value):
		value = self._get_safe_value(value)
		return super().to_python(value)


class FloatZeroField(models.FloatField):

	def _get_safe_value(self, value):
		if isinstance(value, str):
			try:
				value = float(value)
			except ValueError:
				value = 0.0
		return value

	def get_prep_value(self, value):
		value = self._get_safe_value(value)
		return super().get_prep_value(value)

	def to_python(self, value):
		value = self._get_safe_value(value)
		return super().to_python(value)
