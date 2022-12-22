from django.db import models

from irpf.fields import CharCodeField, DateField, CharCodeNameField, FloatZeroField


class Enterprise(models.Model):
	CATEGORY_ACAO = 1
	CATEGORY_FII = 2
	CATEGORY_BDR = 3
	CATEGORY_CHOICES = (
		(CATEGORY_ACAO, "AÇÃO"),
		(CATEGORY_FII, "FII"),
		(CATEGORY_BDR, "BDR")
	)

	code = models.CharField(verbose_name="Código de negociação",
	                        max_length=8)
	name = models.CharField(verbose_name="Nome", max_length=512)
	cnpj = models.CharField(verbose_name="CNPJ", max_length=32)

	category = models.IntegerField(verbose_name="Categoria",
	                               default=None, null=True, blank=True,
	                               help_text="É tipo de papel que essa empresa representa.",
	                               choices=CATEGORY_CHOICES)

	@property
	def is_acao(self):
		return self.category == self.CATEGORY_ACAO

	@property
	def is_fii(self):
		return self.category == self.CATEGORY_FII

	@property
	def is_bdr(self):
		return self.category == self.CATEGORY_BDR

	def __str__(self):
		return f"{self.name} ({self.cnpj})"

	class Meta:
		verbose_name = "Empresa"
		verbose_name_plural = "Empresas"


class Negotiation(models.Model):
	"""Data do Negócio / Tipo de Movimentação / Mercado / Prazo/Vencimento / Instituição /
	Código de Negociação / Quantidade / Preço / Valor"""

	date = DateField(verbose_name="Data do Negócio")
	kind = models.CharField(verbose_name="Tipo de Movimentação",
	                        max_length=16)

	institution = models.CharField(verbose_name="Instituição",
	                               max_length=512)

	code = CharCodeField(verbose_name="Código de negociação",
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
		verbose_name = "Negociação"
		verbose_name_plural = "Negociações"
		ordering = ("date",)


class Earnings(models.Model):
	date = DateField(verbose_name="Data")
	flow = models.CharField(verbose_name="Entrada/Saída", max_length=16)

	kind = models.CharField(verbose_name="Tipo de Movimentação", max_length=256)
	code = CharCodeNameField(verbose_name="Código", max_length=512, is_code=True)
	name = CharCodeNameField(verbose_name="Empresa", max_length=256)
	institution = models.CharField(verbose_name="Instituição",
	                               max_length=512)
	quantity = models.FloatField(verbose_name="Quantidade", default=0.0)
	total = FloatZeroField(verbose_name="Valor da operação", default=0.0)

	date.sheet_header = "Data"
	flow.sheet_header = "Entrada/Saída"
	kind.sheet_header = "Movimentação"
	code.sheet_header = "Produto"
	name.sheet_header = "Produto"
	institution.sheet_header = "Instituição"
	quantity.sheet_header = "Quantidade"
	total.sheet_header = "Valor da Operação"

	def __str__(self):
		return f'{self.code}/{self.name} ({self.institution}) / R${self.total}'

	class Meta:
		verbose_name = "Provento"
		verbose_name_plural = "Proventos"
		ordering = ("date",)
