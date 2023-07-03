from django.conf import settings
from django.contrib.auth import get_permission_codename
from django.contrib.auth.models import Group, Permission, ContentType
from django.core.management.base import BaseCommand

from irpf.models import (
	Bookkeeping,
	FoundsAdministrator,
	Asset,
	Institution,
	Negotiation,
	Bonus,
	Earnings,
	BrokerageNote,
	AssetEvent,
	Position,
	Taxes
)


class Command(BaseCommand):
	help = """Configuração o grupo padrão e suas permissões"""
	_cache = {}
	permission_names_all = ('view', 'add', 'change', 'delete')

	permissions_models = {
		Bookkeeping: ('view', 'add'),
		FoundsAdministrator: ('view', 'add'),
		Asset: ('view', 'add', 'change'),
		Institution: ('view', 'add', 'change'),
		Negotiation: permission_names_all,
		Bonus: permission_names_all,
		Earnings: permission_names_all,
		BrokerageNote: permission_names_all,
		AssetEvent: permission_names_all,
		Position: permission_names_all,
		Taxes: permission_names_all
	}

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
		for model in self.permissions_models:
			actions = self.permissions_models[model]
			for action in actions:
				perms.append(
					self.get_permission(action, model)
				)
		print(f" Grupo {obj} ".center(25, '='))
		for pm in perms:
			print(pm)
		obj.permissions.set(perms)
