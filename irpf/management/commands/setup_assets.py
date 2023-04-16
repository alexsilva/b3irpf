from django.core.management.base import BaseCommand

from irpf.models import Earnings, Negotiation, Enterprise


class Command(BaseCommand):
	"""Configura os ativos ao modelo cujo valor é Null
	"""
	asset_model = Enterprise

	def get_db_asset(self, ticker: str):
		"""O ativo"""
		try:
			asset = self.asset_model.objects.get(code__iexact=ticker)
		except self.asset_model.DoesNotExist:
			asset = None
		return asset

	def handle(self, *args, **options):
		models = (Earnings, Negotiation)
		for model in models:
			count = 0
			for instance in model.objects.filter(asset__isnull=True):
				instance.asset = self.get_db_asset(instance.code)
				instance.save()
				count += 1

			if count > 0:
				opts = model._meta
				print(f"{count} {opts.verbose_name} atualizados")
