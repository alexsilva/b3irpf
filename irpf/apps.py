from django.apps import AppConfig


class IrpfConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	verbose_name = 'Declaração do imposto anual'
	name = 'irpf'

	def ready(self):
		from irpf.models import DayTrade, SwingTrade

		DayTrade.setup_defaults()
		SwingTrade.setup_defaults()
