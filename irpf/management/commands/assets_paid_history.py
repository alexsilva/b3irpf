from django.utils.timezone import now

from assetprice.management.commands import paid_history
from irpf.models import Asset


class Command(paid_history.Command):
	help = "Armazena o histórico de dividendos dos ativos cadastrados"

	def add_arguments(self, parser):
		parser.add_argument('-nc', '--nocache', action="store_true")

	def handle(self, *args, **options):
		interval = 5
		date_now = now()
		no_cache = options.get('nocache', False)
		for instance in Asset.objects.filter(category=Asset.CATEGORY_STOCK):
			queryset = self.get_from_history(instance.code, date_now.year - interval, date_now.year)
			if no_cache or queryset.count() < interval:
				options['ticker'] = instance.code
				super().handle(**options)
			else:
				print(f'[CACHE] {instance}', file=self.stdout)
