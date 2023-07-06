import calendar

import django.forms as django_forms
from django.forms.widgets import MultiWidget, Select, NumberInput

from irpf.utils import YearMonthDates


class YearWidget(NumberInput):
	...


class MontyWidget(Select):
	def __init__(self, attrs=None):
		choices = self._get_monty_choices()
		super().__init__(attrs=attrs, choices=choices)

	def _get_monty_choices(self):
		# Obtenha os nomes dos meses em uma lista
		months = list(calendar.month_name)[1:]
		# Crie uma lista de tuplas (valor, rótulo) para usar como choices
		choices = [(index, monty) for index, monty in enumerate(months, start=1)]
		return choices


class YearMonthWidget(MultiWidget):
	template_name = 'irpf/forms/widgets/yearmonty.html'

	def __init__(self, attrs=None, year_attrs=None, monty_attrs=None):
		if year_attrs and attrs:
			year_attrs.upadte(attrs)
		else:
			year_attrs = attrs
		if monty_attrs and attrs:
			monty_attrs.upadte(attrs)
		else:
			monty_attrs = attrs
		widgets = (
			YearWidget(attrs=year_attrs),
			MontyWidget(attrs=monty_attrs)
		)
		super().__init__(widgets, attrs=attrs)

	def decompress(self, value):
		if value:
			return value
		return [None, None]


class YearMonthField(django_forms.MultiValueField):
	widget = YearMonthWidget

	def __init__(self, **kwargs):
		fields = (
			django_forms.IntegerField(),
			django_forms.IntegerField()
		)

		super().__init__(fields, **kwargs)

	def compress(self, data_list):
		if data_list:
			return YearMonthDates(*data_list)
		return None
