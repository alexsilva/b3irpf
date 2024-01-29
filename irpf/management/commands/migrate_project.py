from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.module_loading import import_string

from irpf.models import ProjectMigration


class Command(BaseCommand):
	help = """
	Comando que executa a migração de dados entre versões
	"""

	def handle(self, *args, **options):
		print("Migração de dado...")
		try:
			migration = ProjectMigration.objects.get(version=settings.IRPF_VERSION)
		except ProjectMigration.DoesNotExist:
			migration = ProjectMigration(version=settings.IRPF_VERSION)
			version = settings.IRPF_VERSION.replace('.', '_')
			try:
				init = import_string(f"irpf.data.migrate_{version}.init")
				init(migration)
			except Exception as exc:
				raise exc from None
			else:
				migration.save()
		print("Migração executada", migration)
