from django.db import models


class Negotiation(models.Model):
	"""Data do Negócio / Tipo de Movimentação / Mercado / Prazo/Vencimento / Instituição /
	Código de Negociação / Quantidade / Preço / Valor"""

	date = models.DateField(verbose_name="Data do Negócio")
	kind = models.CharField(verbose_name="Tipo de Movimentação",
	                        max_length=16)

	institution = models.CharField(verbose_name="Instituição")

	code = models.CharField(verbose_name="Código de negociação",
	                        max_length=8)

	quantity = models.PositiveBigIntegerField(verbose_name="Quantidade")

	price = models.FloatField(verbose_name="Preço", default=0.0)

	total = models.FloatField(verbose_name="Valor (total)", default=0.0)

	# relates the name of the headers with the fields.
	date.sheet_header = "Data do Negócio"
	kind.sheet_header = "Tipo de Movimentação"
	institution.sheet_header = "Instituição"
	code.sheet_header = "Código de Negociação"
	quantity.sheet_header = "Quantidade"
	price.sheet_header = "Preço"
	total.sheet_header = "Valor"

	def __str__(self):
		return f'{self.code}/{self.quantity} ({self.institution})'

	class Meta:
		verbose_name = "Negotiation"
