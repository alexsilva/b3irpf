from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.urls import reverse

from b3irpf import settings
from xadmin.models import UserWidget
from xadmin.views.dashboard import QuickBtnWidget

User = get_user_model()


class Command(BaseCommand):
	help = """
	Comando que cria widgets de usuário.
	"""

	widgets = [{
		'page_id': 'home',
		'widget_type': QuickBtnWidget.widget_type,
		'value': {
			"title": "Visualizador de xlsx",
			"url": "xadmin:xlsx_viewer"
		}
	}, {
		'page_id': 'home',
		'widget_type': QuickBtnWidget.widget_type,
		'value': {
			"title": "Relatório IRPF",
			"url": reverse("xadmin:reportirpf", kwargs={"model_app_label": "irpf.negotiation"})
		}
	}]

	def handle(self, *args, **options):
		print("\nCriando widgets...", file=self.stdout)
		for user in User.objects.filter(is_active=True, groups__name__in=[settings.XADMIN_DEFAULT_GROUP]):
			if UserWidget.objects.filter(user=user).exists():
				continue
			for widget in self.widgets:
				instance = UserWidget(
					page_id=widget['page_id'],
					widget_type=widget['widget_type'],
					user=user
				)
				instance.set_value(widget['value'])
				instance.save()
