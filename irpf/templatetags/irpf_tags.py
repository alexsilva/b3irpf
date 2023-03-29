from django import template
from django.utils.formats import number_format

from irpf.report.utils import smart_desc as irpf_smart_desc

register = template.Library()


@register.filter
def moneyformat(value):
	"""money format"""
	return number_format(value, decimal_pos=2)


@register.filter
def smart_desc(value):
	return irpf_smart_desc(value)


@register.simple_tag
def exclude_obj_keys(obj, *keys):
	results = {}
	for key in obj:
		if key in keys:
			continue
		results[key] = obj[key]
	return results


@register.simple_tag
def get_obj_val(obj, name):
	return getattr(obj, name)
