import datetime

from django.db import models


class DateField(models.DateField):
	def to_python(self, value):
		if isinstance(value, str):
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
		self._is_code = kwargs.pop("is_code", True)
		super().__init__(*args, **kwargs)

	def to_python(self, value):
		value = super().to_python(value)
		if isinstance(value, str):
			# removes the fractional portion of the code.
			code, name = value.split('-', 1)
			if self._is_code:
				value = code.rstrip("Ff ")
		return value


class FloatZeroField(models.FloatField):

	def to_python(self, value):
		if isinstance(value, str) and not value.isdigit():
			value = 0.0
		return super().to_python(value)
