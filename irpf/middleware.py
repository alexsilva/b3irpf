from functools import partial


def is_ajax(request):
	"""django:4+"""
	return request.headers.get('x-requested-with') == 'XMLHttpRequest'


class RequestUtilsMiddleware:
	"""Middleware que implementa função removidas do django
	Também pode servir para criar novas funcionalidades
	"""

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		if not hasattr(request, "is_ajax"):
			request.is_ajax = partial(is_ajax, request)
		return self.get_response(request)
