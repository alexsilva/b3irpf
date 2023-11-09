from irpf.management.commands import _import_base
from irpf.models import Earnings


class Command(_import_base.Command):
	help = """imports data from the xlsx file with information on the earnings."""

	storage_model = Earnings
	storage_opts = storage_model._meta
