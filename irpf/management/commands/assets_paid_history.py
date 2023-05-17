from django.utils.timezone import now

from assetprice.management.commands import paid_history
from irpf.models import Asset


class Command(paid_history.Command):
	help = "Armazena o histórico de dividendos dos ativos cadastrados"

	def handle(self, *args, **options):
		interval = 5
		date_now = now()
		for instance in Asset.objects.all():
			queryset = self.get_from_history(instance.code, date_now.year - interval, date_now.year)
			if queryset.count() < interval:
				options['ticker'] = instance.code
				super().handle(**options)
			else:
				print(f'[CACHE] {instance}', file=self.stdout)
