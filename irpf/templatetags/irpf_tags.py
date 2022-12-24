from django import template
from django.template.defaultfilters import stringformat

register = template.Library()


@register.filter
def moneyformat(value):
	"""money format"""
	return stringformat(value, ".2f")
