import calendar

import django.forms as django_forms
from django.forms.widgets import MultiWidget, Select, NumberInput

from irpf.utils import MonthYearDates


class YearWidget(NumberInput):
	...


class MonthWidget(Select):
	def __init__(self, attrs=None):
		choices = self._get_month_choices()
		super().__init__(attrs=attrs, choices=choices)

	def _get_month_choices(self):
		# Obtenha os nomes dos meses em uma lista
		months = list(calendar.month_name)[1:]
		# Crie uma lista de tuplas (valor, rótulo) para usar como choices
		choices = [(index, month.capitalize()) for index, month in enumerate(months, start=1)]
		return choices


class MonthYearWidget(MultiWidget):
	template_name = 'irpf/forms/widgets/monthyear.html'

	def __init__(self, attrs=None, monty_attrs=None, year_attrs=None):
		if monty_attrs and attrs:
			monty_attrs.upadte(attrs)
		else:
			monty_attrs = attrs
		if year_attrs and attrs:
			year_attrs.upadte(attrs)
		else:
			year_attrs = attrs
		widgets = (
			MonthWidget(attrs=monty_attrs),
			YearWidget(attrs=year_attrs)
		)
		super().__init__(widgets, attrs=attrs)

	def decompress(self, value):
		if value:
			return value
		return [None, None]


class MonthYearWidgetNavigator(MonthYearWidget):
	template_name = 'irpf/forms/widgets/monthyear_nav.html'


class MonthYearField(django_forms.MultiValueField):
	widget = MonthYearWidget

	def __init__(self, **kwargs):
		fields = (
			django_forms.IntegerField(),
			django_forms.IntegerField()
		)

		super().__init__(fields, **kwargs)

	def compress(self, data_list):
		if data_list:
			return MonthYearDates(*data_list)
		return None


class MonthYearNavigatorField(MonthYearField):
	"""Inclui botões de navegação datas passadas e futuras"""
	widget = MonthYearWidgetNavigator
