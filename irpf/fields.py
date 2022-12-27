import datetime

from django.db import models


class DateField(models.DateField):
	def to_python(self, value):
		if value and isinstance(value, str):
			try:
				value = datetime.datetime.strptime(value, "%d/%m/%Y")
			except ValueError:
				pass
		value = super().to_python(value)
		return value


class CharCodeField(models.CharField):
	def to_python(self, value):
		value = super().to_python(value)
		if isinstance(value, str):
			# removes the fractional portion of the code.
			value = value.rstrip("Ff")
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
				if self._is_code:
					value = value.rstrip("Ff ")
				else:
					value = value.strip()
			else:
				if self._is_code:
					value = code.rstrip("Ff ")
				else:
					value = name.strip()
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
