from django.conf import settings
from django.db import models
from django.utils.formats import number_format, date_format
from django.utils.functional import cached_property

from irpf.fields import CharCodeField, DateField, CharCodeNameField, FloatZeroField, FloatBRField, DateNoneField
from irpf.storage import FileSystemOverwriteStorage


class Bookkeeping(models.Model):
	name = models.CharField(verbose_name="Nome", max_length=512)
	cnpj = models.CharField(verbose_name="CNPJ", max_length=32,
	                        blank=True, null=True)
	link = models.URLField(verbose_name="Portal do investidor")

	def __str__(self):
		return f"{self.name} / {self.cnpj or self.link}"

	class Meta:
		verbose_name = "Agente escriturador"
		verbose_name_plural = "Agentes escrituradores"


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

	bookkeeping = models.ForeignKey(Bookkeeping,
	                                verbose_name=Bookkeeping._meta.verbose_name,
	                                on_delete=models.SET_NULL,
	                                null=True, blank=False)

	@cached_property
	def category_choices(self):
		return dict(self.CATEGORY_CHOICES)

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
		return f"{self.code} - {self.name} - {self.cnpj}"

	class Meta:
		ordering = ("name", "code")
		verbose_name = "Empresa"
		verbose_name_plural = "Empresas"


class Instituition(models.Model):
	"""Corretora de valores"""
	name = models.CharField(verbose_name="Instituição", max_length=512)
	cnpj = models.CharField(verbose_name="CNPJ", max_length=32)

	def __str__(self):
		return f"{self.name} - {self.cnpj}"

	class Meta:
		verbose_name = "Corretora"
		verbose_name_plural = verbose_name + "s"


class BaseIRPFModel(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL,
	                         verbose_name="Usuário",
	                         on_delete=models.CASCADE,
	                         editable=False,
	                         null=True, blank=False)

	class Meta:
		abstract = True


class Negotiation(BaseIRPFModel):
	"""Data do Negócio / Tipo de Movimentação / Mercado / Prazo/Vencimento / Instituição /
	Código de Negociação / Quantidade / Preço / Valor"""
	KIND_BUY = "Compra"
	KIND_SELL = "Venda"
	KIND_CHOICES = (
		(KIND_BUY, KIND_BUY),
		(KIND_SELL, KIND_SELL)
	)

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

	positions = models.ManyToManyField(to="Position",
									verbose_name="Posições",
									blank=True,
									editable=False,
									help_text="Esta relação serve apenas para fins de histórico de posição")

	tax = models.FloatField(verbose_name="Taxas", default=0.0)
	irrf = models.FloatField(verbose_name="IRRF", default=0.0,
	                         help_text="Imposto que pode ter sido retido na fonte")

	brokerage_note = models.ForeignKey("BrokerageNote",
	                                   on_delete=models.SET_NULL,
	                                   verbose_name="Notas",
		                               null=True,
		                               editable=False)

	# relates the name of the headers with the fields.
	date.sheet_header = "Data do Negócio"
	kind.sheet_header = "Tipo de Movimentação"
	institution.sheet_header = "Instituição"
	code.sheet_header = "Código de Negociação"
	quantity.sheet_header = "Quantidade"
	price.sheet_header = "Preço"
	total.sheet_header = "Valor"

	def __str__(self):
		return f'{self.code}:{self.kind[0]}/{self.quantity} ({self.institution})'

	class Meta:
		verbose_name = "Negociação"
		verbose_name_plural = "Negociações"
		ordering = ("date",)


class Bonus(BaseIRPFModel):
	enterprise = models.ForeignKey(Enterprise, on_delete=models.CASCADE,
	                               verbose_name="Empresa")
	data_com = DateField(verbose_name="Data com")
	date_ex = DateField(verbose_name="Data ex")
	date = DateField(verbose_name="Data de incorporação")
	base_value = models.FloatField(verbose_name="Valor de base", default=0.0)
	proportion = models.FloatField(verbose_name="Proporção", default=0.0,
	                               help_text="valor expresso em porcentagem.")

	def __str__(self):
		value = number_format(self.base_value)
		return f"{self.enterprise} / R$ {value} {self.proportion}%"

	class Meta:
		verbose_name = "Bonificação"
		verbose_name_plural = "Bonificações"
		ordering = ("date",)


class Earnings(BaseIRPFModel):
	date = DateField(verbose_name="Data")
	flow = models.CharField(verbose_name="Entrada/Saída", max_length=16)

	kind = models.CharField(verbose_name="Tipo de Movimentação", max_length=256)
	code = CharCodeNameField(verbose_name="Código", max_length=512, is_code=True)
	name = CharCodeNameField(verbose_name="Empresa", max_length=256)
	institution = models.CharField(verbose_name="Instituição",
	                               max_length=512)
	quantity = FloatBRField(verbose_name="Quantidade", default=0.0)
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


class BrokerageNote(BaseIRPFModel):
	"""Modelo de notas de corretagem"""
	note = models.FileField(verbose_name='Nota de corretagem (PDF)',
	                        upload_to='notes',
	                        storage=FileSystemOverwriteStorage())
	institution = models.ForeignKey(Instituition,
	                                on_delete=models.CASCADE,
	                                verbose_name="Corretora",
	                                help_text="A corretora que gerou esssa nota.")
	reference_date = models.DateField(verbose_name="Data do pregão", null=True)
	settlement_fee = models.FloatField(verbose_name="Taxa de liquidação", default=0.0)
	registration_fee = models.FloatField(verbose_name="Taxa de registro", default=0.0)
	term_fee = models.FloatField(verbose_name="Taxa de termo/opções", default=0.0)
	ana_fee = models.FloatField(verbose_name="Taxa A.N.A", default=0.0)
	emoluments = models.FloatField(verbose_name="Emolumentos", default=0.0)
	operational_fee = models.FloatField(verbose_name="Taxa Operacional", default=0.0)
	execution = models.FloatField(verbose_name="Execução", default=0.0)
	custody_fee = models.FloatField(verbose_name="Taxa de custódia", default=0.0)
	taxes = models.FloatField(verbose_name="Impostos", default=0.0)
	others = models.FloatField(verbose_name="Outros", default=0.0)

	transactions = models.ManyToManyField(Negotiation, verbose_name="Transações")

	def __str__(self):
		return f"{self.note} / {self.institution.name}"

	class Meta:
		verbose_name = "Nota de corretagem"
		verbose_name_plural = "Notas de corretagem"


class Provision(BaseIRPFModel):
	code = CharCodeNameField(verbose_name="Código", max_length=512, is_code=True)
	name = CharCodeNameField(verbose_name="Empresa", max_length=256)
	kind = models.CharField(verbose_name="Tipo de Movimentação", max_length=256)
	institution = models.CharField(verbose_name="Instituição",
	                               max_length=512)
	quantity = FloatBRField(verbose_name="Quantidade", default=0.0)
	total = FloatZeroField(verbose_name="Valor da operação", default=0.0)

	date_ex = DateNoneField(verbose_name="Data Ex", blank=True, null=True)
	date_payment = DateNoneField(verbose_name="Previsão de pagamento",
	                             blank=True, null=True)

	code.sheet_header = "Produto"
	name.sheet_header = "Produto"
	kind.sheet_header = "Tipo de Evento"
	institution.sheet_header = "Instituição"
	quantity.sheet_header = "Quantidade"
	total.sheet_header = "Valor líquido"
	date_payment.sheet_header = "Previsão de pagamento"

	def __str__(self):
		total = number_format(self.total)
		return f"{self.code} - {self.name} R$ {total}"

	class Meta:
		verbose_name = "Provisão"
		verbose_name_plural = "Provisões"
		ordering = ('date_payment',)


class Position(BaseIRPFModel):
	enterprise = models.ForeignKey(Enterprise, on_delete=models.CASCADE,
	                               verbose_name="Empresa")
	institution = models.ForeignKey(Instituition,
	                                on_delete=models.SET_NULL,
	                                verbose_name="Instituição",
	                                blank=True, null=True)
	quantity = models.IntegerField(verbose_name="Quantidade", default=0)
	avg_price = models.FloatField(verbose_name="Preço médio", default=0.0)
	total = FloatZeroField(verbose_name="Valor total", default=0.0)
	tax = models.FloatField(verbose_name="Taxas", default=0.0)
	date = DateField(verbose_name="Data")

	def __str__(self):
		dt = date_format(self.date)
		msg = f"Posição até {dt}"
		if self.institution:
			msg += f" - {self.institution.name}"
		return msg

	class Meta:
		unique_together = ("enterprise", "institution", "user", "date")
		ordering = ('enterprise__code', 'enterprise__category',)
		verbose_name = "Posição"
		verbose_name_plural = "Posições"
