from django.db import models


class CharCodeField(models.CharField):
	def to_python(self, value):
		value = super().to_python(value)
		if isinstance(value, str):
			# removes the fractional portion of the code.
			value = value.rstrip("Ff")
		return value
