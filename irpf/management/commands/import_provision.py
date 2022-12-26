from irpf.management.commands import _import_base
from irpf.models import Provision


class Command(_import_base.Command):
	help = """imports data from the xlsx file with information on the privision."""

	storage_model = Provision
	storage_ops = storage_model._meta
