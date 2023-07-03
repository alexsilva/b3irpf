from crispy_forms.helper import FormHelper
from django.views.generic import FormView

from xadmin.views.base import CommAdminView


class AdminFormView(CommAdminView, FormView):
	"""Base classe que implementa parte de uma view de formulário"""
	title = None
	form_method_post = False

	def get_helper(self):
		helper = FormHelper()
		helper.disable_csrf = not self.form_method_post
		helper.form_tag = False
		helper.form_class = 'form-horizontal'
		helper.field_class = 'controls col-sm-10'
		helper.label_class = 'col-sm-2'
		helper.use_custom_control = False
		helper.include_media = False
		return helper

	def get_form(self, form_class=None):
		form = super().get_form(form_class=form_class)
		form.helper = self.get_helper()
		return form

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context.update(self.get_context())
		form_media = context['form'].media
		context['media'] += form_media
		context['title'] = self.title
		context['form_method_post'] = self.form_method_post
		return context
