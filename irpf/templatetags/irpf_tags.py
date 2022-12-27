from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter
def moneyformat(value):
	"""money format"""
	if value is None or value == "":
		value = 0.0
	return number_format(value, decimal_pos=2)
