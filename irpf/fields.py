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
