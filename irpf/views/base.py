from django.views.generic import FormView

from xadmin.views.base import CommAdminView


class AdminFormView(CommAdminView, FormView):
	"""Base classe que implementa parte de uma view de formulário"""
	title = None

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context.update(self.get_context())
		form_media = context['form'].media
		context['media'] += form_media
		context['title'] = self.title
		return context
