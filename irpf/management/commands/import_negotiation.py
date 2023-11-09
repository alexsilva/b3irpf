from irpf.management.commands import _import_base

from irpf.models import Negotiation


class Command(_import_base.Command):
	help = """imports data from the xlsx file with information on the year's negotiations."""

	storage_model = Negotiation
	storage_opts = storage_model._meta
