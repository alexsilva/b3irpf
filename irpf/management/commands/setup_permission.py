from django.conf import settings
from django.contrib.auth import get_permission_codename
from django.contrib.auth.models import Group, Permission, ContentType
from django.core.management.base import BaseCommand

from irpf import permissions


class Command(BaseCommand):
	help = """Configuração o grupo padrão e suas permissões"""
	_cache = {}

	def get_content_type(self, model, opts):
		try:
			ctype = self._cache[opts.label_lower]
		except KeyError:
			ctype = self._cache[opts.label_lower] = ContentType.objects.get_for_model(model)
		return ctype

	def get_permission(self, action: str, model):
		opts = model._meta
		ctype = self.get_content_type(model, opts)
		codename = get_permission_codename(action, opts)
		return Permission.objects.get(content_type=ctype, codename=codename)

	def handle(self, *args, **options):
		obj, created = Group.objects.get_or_create(name=settings.XADMIN_DEFAULT_GROUP)
		perms = []
		for model in permissions.permission_models:
			actions = permissions.permission_models[model]
			for action in actions:
				perms.append(
					self.get_permission(action, model)
				)
		print(f" Grupo {obj} ".center(25, '='))
		for pm in perms:
			print(pm)
		obj.permissions.set(perms)
