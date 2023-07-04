from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils.formats import number_format, date_format
from django.utils.functional import cached_property, classproperty
from django.utils.text import slugify

from irpf.fields import CharCodeField, DateField, CharCodeNameField, FloatZeroField, FloatBRField, DateNoneField, \
	DecimalZeroField, DecimalBRField
from irpf.storage import FileSystemOverwriteStorage

DECIMAL_MAX_DIGITS = 28
DECMIAL_PLACES = 16


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


class FoundsAdministrator(models.Model):
	"""Geramente quem adminstra Fiis"""
	name = models.CharField(verbose_name="Nome", max_length=512)
	cnpj = models.CharField(verbose_name="CNPJ", max_length=32)

	def __str__(self):
		return f"{self.name} / {self.cnpj}"

	class Meta:
		verbose_name = "Administrador de fundo"
		verbose_name_plural = "Administradores de fundos"


class Asset(models.Model):
	CATEGORY_STOCK = 1
	CATEGORY_FII = 2
	CATEGORY_BDR = 3
	CATEGORY_CHOICES = (
		(CATEGORY_STOCK, "AÇÃO"),
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

	administrator = models.ForeignKey(FoundsAdministrator,
	                                 verbose_name="Administrador",
	                                 help_text="Aquele que administra esse ativo.",
	                                 on_delete=models.SET_NULL,
	                                 null=True, blank=True)

	@cached_property
	def category_choices(self) -> dict:
		return dict(self.CATEGORY_CHOICES)

	@property
	def is_stock(self):
		return self.category == self.CATEGORY_STOCK

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
		verbose_name = "Ativo"
		verbose_name_plural = "Ativos"


class Institution(models.Model):
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
	report_class = "irpf.report.NegotiationReport"
	KIND_BUY = "Compra"
	KIND_SELL = "Venda"
	KIND_CHOICES = (
		(KIND_BUY, KIND_BUY),
		(KIND_SELL, KIND_SELL)
	)

	date = DateField(verbose_name="Data do Negócio")
	kind = models.CharField(verbose_name="Tipo de Movimentação",
	                        choices=KIND_CHOICES,
	                        max_length=16)

	institution = models.CharField(verbose_name="Instituição",
	                               max_length=512)

	code = CharCodeField(verbose_name="Código de negociação",
	                     max_length=8)

	asset = models.ForeignKey(Asset, on_delete=models.CASCADE,
	                          verbose_name="Ativo",
	                          null=True)

	quantity = models.DecimalField(verbose_name="Quantidade",
	                               max_digits=19,
	                               decimal_places=2)

	price = models.DecimalField(verbose_name="Preço",
	                            max_digits=DECIMAL_MAX_DIGITS,
	                            decimal_places=DECMIAL_PLACES,
	                            default=Decimal(0))
	total = models.DecimalField(verbose_name="Valor (total)",
	                            max_digits=DECIMAL_MAX_DIGITS,
	                            decimal_places=DECMIAL_PLACES,
	                            default=Decimal(0))

	tax = models.DecimalField(verbose_name="Taxas",
	                          max_digits=DECIMAL_MAX_DIGITS,
	                          decimal_places=DECMIAL_PLACES,
	                          default=Decimal(0))
	irrf = models.DecimalField(verbose_name="IRRF",
	                           max_digits=DECIMAL_MAX_DIGITS,
	                           decimal_places=DECMIAL_PLACES,
	                           default=Decimal(0),
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

	@classmethod
	def import_before_save_data(cls, **data):
		opts = cls._meta
		try:
			ticker = opts.get_field("code").to_python(data['code'])
			data['asset'] = Asset.objects.get(code__iexact=ticker)
		except Asset.DoesNotExist:
			pass
		return data

	@cached_property
	def is_sell(self):
		"""Se é uma venda"""
		return self.kind.lower() == self.KIND_SELL.lower()

	@cached_property
	def is_buy(self):
		"""Se é uma compra"""
		return self.kind.lower() == self.KIND_BUY.lower()

	def __str__(self):
		return f'{self.code}:{self.kind[0]}/{self.quantity} ({self.institution})'

	class Meta:
		verbose_name = "Negociação"
		verbose_name_plural = "Negociações"
		ordering = ("-date",)


class Bonus(BaseIRPFModel):
	asset = models.ForeignKey(Asset, on_delete=models.CASCADE,
	                          verbose_name="Ativo",
	                          null=True, blank=False)
	data_com = DateField(verbose_name="Data com")
	date_ex = DateField(verbose_name="Data ex")
	date = DateField(verbose_name="Data de incorporação")
	base_value = models.DecimalField(verbose_name="Valor de base",
	                                 max_digits=DECIMAL_MAX_DIGITS,
	                                 decimal_places=DECMIAL_PLACES,
	                                 default=Decimal(0))
	proportion = models.DecimalField(verbose_name="Proporção",
	                                 max_digits=6,
	                                 decimal_places=2,
	                                 default=Decimal(0),
	                                 help_text="valor expresso em porcentagem.")

	notice = models.FileField(verbose_name='Arquivo de anúncio',
	                          upload_to='bonus/notice',
	                          storage=FileSystemOverwriteStorage(),
	                          null=True, blank=True)

	def __str__(self):
		value = number_format(self.base_value)
		return f"{self.asset} / R$ {value} {self.proportion}%"

	class Meta:
		verbose_name = "Bonificação"
		verbose_name_plural = "Bonificações"
		ordering = ("date",)


class Earnings(BaseIRPFModel):
	report_class = "irpf.report.EarningsReport"
	BONIFICAO_EM_ATIVOS = "bonificacao_em_ativos"
	LEILAO_DE_FRACAO = "leilao_de_fracao"
	FRACAO_EM_ATIVOS = "fracao_em_ativos"
	FLOW_CREDIT = "Credito"
	FLOW_DEBIT = "Debito"
	FLOW_CHOICES = (
		(FLOW_CREDIT, FLOW_CREDIT),
		(FLOW_DEBIT, FLOW_DEBIT)
	)

	date = DateField(verbose_name="Data")
	flow = models.CharField(verbose_name="Entrada/Saída", max_length=16)

	kind = models.CharField(verbose_name="Tipo de Movimentação", max_length=256)
	code = CharCodeNameField(verbose_name="Código", max_length=512, is_code=True)
	name = CharCodeNameField(verbose_name="Nome do ativo", max_length=256)
	asset = models.ForeignKey(Asset, on_delete=models.CASCADE,
	                          verbose_name="Ativo",
	                          null=True)
	institution = models.CharField(verbose_name="Instituição",
	                               max_length=512)
	quantity = DecimalBRField(verbose_name="Quantidade",
	                          max_digits=19,
	                          decimal_places=2,
	                          default=Decimal(0))
	total = DecimalZeroField(verbose_name="Valor da operação",
	                         max_digits=DECIMAL_MAX_DIGITS,
	                         decimal_places=DECMIAL_PLACES,
	                         default=Decimal(0))

	date.sheet_header = "Data"
	flow.sheet_header = "Entrada/Saída"
	kind.sheet_header = "Movimentação"
	code.sheet_header = "Produto"
	name.sheet_header = "Produto"
	institution.sheet_header = "Instituição"
	quantity.sheet_header = "Quantidade"
	total.sheet_header = "Valor da Operação"

	@classmethod
	def import_before_save_data(cls, **data):
		opts = cls._meta
		try:
			ticker = opts.get_field("code").to_python(data['code'])
			data['asset'] = Asset.objects.get(code__iexact=ticker)
		except Asset.DoesNotExist:
			pass
		return data

	@cached_property
	def kind_slug(self):
		return slugify(self.kind).replace('-', "_")

	@cached_property
	def is_credit(self):
		"""Se é crédito"""
		return self.flow.lower() == self.FLOW_CREDIT.lower()

	@cached_property
	def is_debit(self):
		"""Se é débito"""
		return self.flow.lower() == self.FLOW_DEBIT.lower()

	def __str__(self):
		return f'{self.code} - {self.name} - R${self.total}'

	class Meta:
		verbose_name = "Provento"
		verbose_name_plural = "Proventos"
		ordering = ("-date",)


class BrokerageNote(BaseIRPFModel):
	"""Modelo de notas de corretagem"""
	note = models.FileField(verbose_name='Nota de corretagem (PDF)',
	                        upload_to='notes',
	                        storage=FileSystemOverwriteStorage())
	institution = models.ForeignKey(Institution,
	                                on_delete=models.CASCADE,
	                                verbose_name="Corretora",
	                                help_text="A corretora que gerou essa nota.")
	reference_date = models.DateField(verbose_name="Data do pregão", null=True)
	settlement_fee = models.DecimalField(verbose_name="Taxa de liquidação",
	                                     max_digits=DECIMAL_MAX_DIGITS,
	                                     decimal_places=4,
	                                     default=Decimal(0))
	registration_fee = models.DecimalField(verbose_name="Taxa de registro",
	                                       max_digits=DECIMAL_MAX_DIGITS,
	                                       decimal_places=4,
	                                       default=Decimal(0))
	term_fee = models.DecimalField(verbose_name="Taxa de termo/opções",
	                               max_digits=DECIMAL_MAX_DIGITS,
	                               decimal_places=4,
	                               default=Decimal(0))
	ana_fee = models.DecimalField(verbose_name="Taxa A.N.A",
	                              max_digits=DECIMAL_MAX_DIGITS,
	                              decimal_places=4,
	                              default=Decimal(0))
	emoluments = models.DecimalField(verbose_name="Emolumentos",
	                                 max_digits=DECIMAL_MAX_DIGITS,
	                                 decimal_places=4,
	                                 default=Decimal(0))
	operational_fee = models.DecimalField(verbose_name="Taxa Operacional",
	                                      max_digits=DECIMAL_MAX_DIGITS,
	                                      decimal_places=4,
	                                      default=Decimal(0))
	execution = models.DecimalField(verbose_name="Execução",
	                                max_digits=DECIMAL_MAX_DIGITS,
	                                decimal_places=4,
	                                default=Decimal(0))
	custody_fee = models.DecimalField(verbose_name="Taxa de custódia",
	                                  max_digits=DECIMAL_MAX_DIGITS,
	                                  decimal_places=4,
	                                  default=Decimal(0))
	taxes = models.DecimalField(verbose_name="Impostos",
	                            max_digits=DECIMAL_MAX_DIGITS,
	                            decimal_places=4,
	                            default=Decimal(0))
	others = models.DecimalField(verbose_name="Outros",
	                             max_digits=DECIMAL_MAX_DIGITS,
	                             decimal_places=4,
	                             default=Decimal(0))

	def __str__(self):
		return f"{self.note} / {self.institution.name}"

	class Meta:
		verbose_name = "Nota de corretagem"
		verbose_name_plural = "Notas de corretagem"
		ordering = ('-reference_date',)


class AssetEvent(BaseIRPFModel):
	SPLIT, INPLIT = 1, 2
	EVENT_CHOICES = (
		(SPLIT, "Desdobramento"),
		(INPLIT, "Grupamento")
	)
	asset = models.ForeignKey(Asset, on_delete=models.CASCADE,
	                          verbose_name="Ativo",
	                          null=True, blank=False)
	date = models.DateField(verbose_name="Data do anúncio")
	date_com = models.DateField(verbose_name="Data com")
	factor_from = models.IntegerField(verbose_name="Fator de")
	factor_to = models.IntegerField(verbose_name="Fator para")
	event = models.IntegerField(verbose_name="Evento", choices=EVENT_CHOICES, help_text="""	
	<span class="fw-900 text-main-secondary-light">Desdobramento (Split):</span> É quando a que empresas divide suas ações disponíveis em um número maior de ações.
	<br>
	<span class="fw-900 text-main-secondary-light">Grupamento (Inplit):</span> É a operação contrária ao split, onde reúne várias ações em uma.
	<br>
	<span class="fw-900 text-main-secondary-light">Fator:</span> É a proporção que o split/inplit será aplicado sobre o total de ações disponíveis
	<br>
	No processo do split/inplit, o número total de ações aumenta/diminui mas o valor das ações cai/sobe na mesma proporção, mantendo o valor do investimento inalterado.
	""")

	def __str__(self):
		return f"{self.asset.name} / {self.event_name} {self.factor_from}:{self.factor_to}"

	@classproperty
	def event_choices(cls):
		return dict(cls.EVENT_CHOICES)

	@property
	def event_name(self):
		return self.event_choices[self.event]

	class Meta:
		verbose_name = "Evento"
		verbose_name_plural = verbose_name + "s"


class Position(BaseIRPFModel):
	CONSOLIDATION_YEARLY = 1
	CONSOLIDATION_MONTHLY = 2
	CONSOLIDATION_CHOICES = [
		(CONSOLIDATION_YEARLY, "Anual"),
		(CONSOLIDATION_MONTHLY, "Mensal")
	]
	asset = models.ForeignKey(Asset, on_delete=models.CASCADE,
	                          verbose_name="Ativo",
	                          null=True, blank=False)
	institution = models.ForeignKey(Institution,
	                                on_delete=models.SET_NULL,
	                                verbose_name="Instituição",
	                                blank=True, null=True)
	quantity = models.DecimalField(verbose_name="Quantidade",
	                               max_digits=19,
	                               decimal_places=2,
	                               default=Decimal(0))
	avg_price = models.DecimalField(verbose_name="Preço médio",
	                                max_digits=DECIMAL_MAX_DIGITS,
	                                decimal_places=DECMIAL_PLACES,
	                                default=Decimal(0))
	total = models.DecimalField(verbose_name="Valor total",
	                            max_digits=DECIMAL_MAX_DIGITS,
	                            decimal_places=DECMIAL_PLACES,
	                            default=Decimal(0))
	tax = models.DecimalField(verbose_name="Taxas",
	                          max_digits=DECIMAL_MAX_DIGITS,
	                          decimal_places=DECMIAL_PLACES,
	                          default=Decimal(0))
	consolidation = models.PositiveIntegerField(verbose_name="Consolidação",
	                                            choices=CONSOLIDATION_CHOICES,
	                                            default=CONSOLIDATION_YEARLY)
	date = DateField(verbose_name="Data")

	@classproperty
	def consolidation_choices(cls):
		return dict(cls.CONSOLIDATION_CHOICES)

	def __str__(self):
		msg = []
		if self.asset:
			msg.append(f"{self.asset.code} - ")
		dt = date_format(self.date)
		label = self.consolidation_choices[self.consolidation]
		msg.append(f"Posição ({label.lower()}) até {dt}")
		if self.institution:
			msg.append(f" - {self.institution.name}")
		return ' '.join(msg)

	class Meta:
		unique_together = ("asset", "institution", "user", "date")
		ordering = ('asset__code', '-date',)
		verbose_name = "Posição"
		verbose_name_plural = "Posições"


class Taxes(BaseIRPFModel):
	"""Modelo usado para registro de impostos a pagar"""
	TAX_CHOICES = [
		(15, "15%"),
		(20, "20%")
	]
	total = models.DecimalField(verbose_name="Valor bruto",
	                            max_digits=DECIMAL_MAX_DIGITS,
	                            decimal_places=DECMIAL_PLACES,
	                            default=Decimal(0))

	category = models.IntegerField(verbose_name="Categoria",
	                               help_text="Categoria de ativo para cálculo do imposto.",
	                               choices=Asset.CATEGORY_CHOICES)

	tax = models.PositiveIntegerField(verbose_name="Taxa",
	                                  choices=TAX_CHOICES,
	                                  help_text="Taxa do imposto.")

	asset = models.ForeignKey(Asset, on_delete=models.SET_NULL,
	                          verbose_name="Ativo",
	                          null=True, blank=True)

	description = models.TextField(verbose_name="Descrição", blank=True)

	paid = models.BooleanField(verbose_name="Pago", default=False,
	                           help_text="Marque quando o imposto for pago.")

	created = models.DateTimeField(verbose_name="Data de registro", auto_now_add=True)

	def __str__(self):
		total = number_format(self.total, 2)
		paid = "pago" if self.paid else "devendo"
		return f"R$ {total} - {self.tax}% - {paid}"

	class Meta:
		verbose_name = "Imposto"
		verbose_name_plural = verbose_name + "s"
