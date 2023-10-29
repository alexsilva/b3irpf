from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
	help = """
	Comando que faz configuração necessárias para a inicialização de um novo projeto.
	"""

	def handle(self, *args, **options):
		# permissões e grupo padrão
		call_command("setup_permission")

		# criação de um novo administrado
		if not User.objects.filter(is_superuser=True).exists():
			print("\nPor favor crie um administrador para o projeto", file=self.stdout)
			call_command("createsuperuser")
			for user in User.objects.filter(is_superuser=True):
				user.groups.add(Group.objects.get(name=settings.XADMIN_DEFAULT_GROUP))

		# configuração assets
		call_command("setup_assets")
