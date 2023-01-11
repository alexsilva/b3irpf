from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter
def moneyformat(value):
	"""money format"""
	return number_format(value, decimal_pos=2)


@register.simple_tag
def exclude_obj_keys(obj, *keys):
	results = {}
	for key in obj:
		if key in keys:
			continue
		results[key] = obj[key]
	return results


@register.simple_tag
def get_obj_val(obj, key):
	return obj[key]
