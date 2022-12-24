from irpf.management.commands import import_earnings
from irpf.models import Provision


class Command(import_earnings.Command):
	help = """imports data from the xlsx file with information on the privision."""

	storage_model = Provision
	storage_ops = storage_model._meta
