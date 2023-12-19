import datetime
import decimal
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.functional import cached_property, classproperty
from django.utils.text import slugify

from irpf.fields import CharCodeField, DateField, CharCodeNameField, DecimalBRField, MoneyField
from irpf.storage import FileSystemOverwriteStorage

DECIMAL_MAX_DIGITS = 28
DECIMAL_PLACES = 16


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
		indexes = [
			models.Index(fields=['name']),
			models.Index(fields=['cnpj'])
		]


class FoundsAdministrator(models.Model):
	"""Geralmente quem administra FIIS"""
	name = models.CharField(verbose_name="Nome", max_length=512)
	cnpj = models.CharField(verbose_name="CNPJ", max_length=32)

	def __str__(self):
		return f"{self.name} / {self.cnpj}"

	class Meta:
		verbose_name = "Administrador de fundo"
		verbose_name_plural = "Administradores de fundos"
		indexes = [
			models.Index(fields=['name']),
			models.Index(fields=['cnpj'])
		]


class Asset(models.Model):
	CATEGORY_STOCK = 1
	CATEGORY_FII = 2
	CATEGORY_BDR = 3
	CATEGORY_SUBSCRIPTION_STOCK = 4
	CATEGORY_SUBSCRIPTION_FII = 5
	CATEGORY_OTHERS = 5000
	CATEGORY_CHOICES = (
		(CATEGORY_STOCK, "AÇÃO"),
		(CATEGORY_FII, "FII"),
		(CATEGORY_BDR, "BDR"),
		(CATEGORY_SUBSCRIPTION_STOCK, "DIR. SUBSCRIÇÃO - AÇÃO"),
		(CATEGORY_SUBSCRIPTION_FII, "DIR. SUBSCRIÇÃO - FII"),
		(CATEGORY_OTHERS, "OUTROS")
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

	@classproperty
	def category_choices(cls) -> dict:
		return dict(cls.CATEGORY_CHOICES)

	@classproperty
	def category_by_name_choices(cls) -> dict:
		return dict([(v, k) for k, v in cls.category_choices.items()])

	@classmethod
	def get_category_by_name(cls, name):
		return cls.category_by_name_choices[name]

	@cached_property
	def category_name(self) -> str:
		return self.category_choices[self.category]

	@property
	def is_stock(self) -> bool:
		return self.category == self.CATEGORY_STOCK

	@property
	def is_fii(self) -> bool:
		return self.category == self.CATEGORY_FII

	@property
	def is_bdr(self) -> bool:
		return self.category == self.CATEGORY_BDR

	def __str__(self):
		return f"{self.code} - {self.name}"

	class Meta:
		ordering = ("name", "code")
		verbose_name = "Ativo"
		verbose_name_plural = "Ativos"
		indexes = [
			models.Index(fields=['code']),
			models.Index(fields=['name']),
			models.Index(fields=['cnpj'])
		]


class Institution(models.Model):
	"""Corretora de valores"""
	name = models.CharField(verbose_name="Instituição", max_length=512)
	cnpj = models.CharField(verbose_name="CNPJ", max_length=32)

	def __str__(self):
		return f"{self.name[:2].upper()} - {self.cnpj}"

	class Meta:
		verbose_name = "Corretora"
		verbose_name_plural = verbose_name + "s"
		indexes = [
			models.Index(fields=['name']),
			models.Index(fields=['cnpj'])
		]


class BaseIRPFModel(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL,
	                         verbose_name="Usuário",
	                         on_delete=models.CASCADE,
	                         editable=False,
	                         null=False)

	class Meta:
		abstract = True


class ImportModelMixin:

	@staticmethod
	def _convert_decimal(value, *args):
		if value is None:
			return args[0] if args else value
		if isinstance(value, (float, int)):
			return Decimal(value)
		elif (value := value.strip()) == "-":
			return args[0] if args else None
		else:
			try:
				value = Decimal(value.replace(',', '.'))
			except (decimal.InvalidOperation, ValueError) as exc:
				if args:
					value = args[0]
				else:
					raise exc
		return value


class Negotiation(ImportModelMixin, BaseIRPFModel):
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
	                        choices=KIND_CHOICES,
	                        max_length=16)

	institution_name = models.CharField(verbose_name="Instituição",
	                                    max_length=512)

	code = CharCodeField(verbose_name="Código de negociação",
	                     max_length=8)

	asset = models.ForeignKey(Asset, on_delete=models.CASCADE,
	                          verbose_name="Ativo",
	                          null=True)

	quantity = models.DecimalField(verbose_name="Quantidade",
	                               max_digits=19,
	                               decimal_places=0)

	price = MoneyField(verbose_name="Preço",
	                   max_digits=DECIMAL_MAX_DIGITS,
	                   decimal_places=DECIMAL_PLACES,
	                   amount_default=Decimal(0))

	total = MoneyField(verbose_name="Valor (total)",
	                   max_digits=DECIMAL_MAX_DIGITS,
	                   decimal_places=DECIMAL_PLACES,
	                   amount_default=Decimal(0))

	tax = MoneyField(verbose_name="Taxas",
	                 max_digits=DECIMAL_MAX_DIGITS,
	                 decimal_places=DECIMAL_PLACES,
	                 amount_default=Decimal(0))
	irrf = MoneyField(verbose_name="IRRF",
	                  max_digits=DECIMAL_MAX_DIGITS,
	                  decimal_places=DECIMAL_PLACES,
	                  amount_default=Decimal(0),
	                  help_text="Imposto que pode ter sido retido na fonte")

	brokerage_note = models.ForeignKey("BrokerageNote",
	                                   on_delete=models.SET_NULL,
	                                   verbose_name="Notas",
	                                   null=True,
	                                   editable=False)

	# relates the name of the headers with the fields.
	date.sheet_header = "Data do Negócio"
	kind.sheet_header = "Tipo de Movimentação"
	institution_name.sheet_header = "Instituição"
	code.sheet_header = "Código de Negociação"
	quantity.sheet_header = "Quantidade"
	price.amount_field.sheet_header = "Preço"
	total.amount_field.sheet_header = "Valor"

	@classmethod
	def import_before_save_data(cls, **data):
		opts = cls._meta
		data['price'] = cls._convert_decimal(data.get('price'), Decimal(0))
		data['total'] = cls._convert_decimal(data.get('total'), Decimal(0))
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
		return f'{self.code}:{self.kind[0]}/{self.quantity} ({self.institution_name})'

	class Meta:
		verbose_name = "Negociação"
		verbose_name_plural = "Negociações"
		ordering = ("-date",)
		indexes = [
			models.Index(fields=['-date']),
			models.Index(fields=['code']),
			models.Index(fields=['kind']),
			models.Index(fields=['institution_name']),
			models.Index(fields=['-date', 'code', 'kind', 'institution_name'])
		]


class Bonus(BaseIRPFModel):
	asset = models.ForeignKey(Asset, on_delete=models.CASCADE,
	                          verbose_name="Ativo",
	                          null=False)
	date_com = DateField(verbose_name="Data com")
	date_ex = DateField(verbose_name="Data ex")
	date = DateField(verbose_name="Data de incorporação")
	base_value = MoneyField(verbose_name="Valor de base",
	                        max_digits=DECIMAL_MAX_DIGITS,
	                        decimal_places=DECIMAL_PLACES)
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
		return f"{self.asset} / {self.base_value} {self.proportion}%"

	class Meta:
		verbose_name = "Bonificação"
		verbose_name_plural = "Bonificações"
		ordering = ("-date", "-date_com")


class BonusInfo(BaseIRPFModel):
	"""Modelo usado para guardar a posição histórica do ativo e rebalancear a
	carteira quando a data de incorporação for calculada no relatório.
	"""
	bonus = models.OneToOneField(Bonus, on_delete=models.CASCADE)
	from_quantity = models.DecimalField(verbose_name="Ativos",
	                                    max_digits=19,
	                                    decimal_places=0)
	from_total = MoneyField(verbose_name="Valor dos ativos",
	                        max_digits=DECIMAL_MAX_DIGITS,
	                        decimal_places=DECIMAL_PLACES,
	                        amount_default=Decimal(0))
	quantity = models.DecimalField(verbose_name="Quantidade bonificada",
	                               max_digits=DECIMAL_MAX_DIGITS,
	                               decimal_places=DECIMAL_PLACES)
	total = MoneyField(verbose_name="Valor da bonificação",
	                   max_digits=DECIMAL_MAX_DIGITS,
	                   decimal_places=DECIMAL_PLACES,
	                   amount_default=Decimal(0))

	def __str__(self):
		return str(self.bonus)

	class Meta:
		verbose_name = "Resultado da bonificação"
		verbose_name_plural = verbose_name


class Subscription(BaseIRPFModel):
	"""
	 Em muitas ocasiões, quando Fundos Listados (Fundos Imobiliários, FI Agro, etc.) ou empresas
	desejam aumentar o seu capital via nova emissão de cotas/ações, elas concedem aos seus
	cotistas/acionistas um direito de preferência na subscrição a novas cotas/ações, que é proporcional
	aos ativos possuídos pelos cotistas/acionistas em uma data determinada, conforme o especificado
	nas documentações da emissão.
		Isso significa que os investidores atualmente detentores do ativo têm uma espécie prioridade
	na compra das novas cotas/ações, que quando exercida, garante aos investidores a manutenção da
	sua participação no ativo geralmente em uma condição de preço melhor do que a
	observada no mercado (secundário).
	"""
	asset = models.ForeignKey(Asset, on_delete=models.CASCADE,
	                          verbose_name="Ativo",
	                          null=False)

	date_com = DateField(verbose_name="Data com", null=True, blank=False)
	date_ex = DateField(verbose_name="Data ex", null=True, blank=False)
	date = DateField(verbose_name="Data de incorporação", blank=True, null=True)

	quantity = models.DecimalField(verbose_name="Quantidade", max_digits=19, decimal_places=0,
	                               help_text="Quantidade efetivamente subscrita "
	                                         "(deixe vazio para incluir todos os direitos)",
	                               null=True, blank=True)
	price = MoneyField(verbose_name="Preço (unitário)",
	                   max_digits=DECIMAL_MAX_DIGITS,
	                   decimal_places=DECIMAL_PLACES)
	proportion = models.DecimalField(verbose_name="Proporção",
	                                 max_digits=15,
	                                 decimal_places=12,
	                                 default=Decimal(0),
	                                 help_text="valor expresso em porcentagem.")

	notice = models.FileField(verbose_name='Arquivo de anúncio',
	                          upload_to='subscription/notice',
	                          storage=FileSystemOverwriteStorage(),
	                          null=True, blank=True)

	class Meta:
		verbose_name = "Subscrição"
		verbose_name_plural = "Subscrições"
		ordering = ("date", "date_com")
		indexes = [
			models.Index(fields=['-date'])
		]

	def __str__(self):
		return f"{self.asset} / {self.price} {self.proportion}%"


class SubscriptionInfo(BaseIRPFModel):
	"""Modelo usado para guardar a posição histórica do ativo e rebalancear a
	carteira quando a data de incorporação for calculada no relatório.
	"""
	subscription = models.OneToOneField(Subscription, on_delete=models.CASCADE)
	from_quantity = models.DecimalField(verbose_name="Ativos",
	                                    max_digits=19,
	                                    decimal_places=0)
	from_total = MoneyField(verbose_name="Valor dos ativos",
	                        max_digits=DECIMAL_MAX_DIGITS,
	                        decimal_places=DECIMAL_PLACES,
	                        amount_default=Decimal(0))
	quantity = models.DecimalField(verbose_name="Quantidade (subscritas)",
	                               max_digits=DECIMAL_MAX_DIGITS,
	                               decimal_places=DECIMAL_PLACES)
	quantity_proportional = models.DecimalField(verbose_name="Quantidade (direitos)",
	                                            max_digits=DECIMAL_MAX_DIGITS,
	                                            decimal_places=DECIMAL_PLACES,
	                                            default=Decimal(0))
	total = MoneyField(verbose_name="Valor da subscrição",
	                   max_digits=DECIMAL_MAX_DIGITS,
	                   decimal_places=DECIMAL_PLACES,
	                   amount_default=Decimal(0))

	def __str__(self):
		return str(self.subscription)

	class Meta:
		verbose_name = "Resultado da subscrição"
		verbose_name_plural = verbose_name


class Earnings(ImportModelMixin, BaseIRPFModel):
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
	institution_name = models.CharField(verbose_name="Instituição",
	                                    max_length=512)
	quantity = DecimalBRField(verbose_name="Quantidade",
	                          max_digits=19,
	                          decimal_places=2,
	                          default=Decimal(0))
	total = MoneyField(verbose_name="Valor da operação",
	                   max_digits=DECIMAL_MAX_DIGITS,
	                   decimal_places=DECIMAL_PLACES)

	date.sheet_header = "Data"
	flow.sheet_header = "Entrada/Saída"
	kind.sheet_header = "Movimentação"
	code.sheet_header = "Produto"
	name.sheet_header = "Produto"
	institution_name.sheet_header = "Instituição"
	quantity.sheet_header = "Quantidade"
	total.amount_field.sheet_header = "Valor da Operação"

	@classmethod
	def import_before_save_data(cls, **data):
		opts = cls._meta
		data['total'] = cls._convert_decimal(data.get('total'), Decimal(0))
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
		return f'{self.code} - {self.name} - {self.total}'

	class Meta:
		verbose_name = "Provento"
		verbose_name_plural = "Proventos"
		ordering = ("-date",)
		indexes = [
			models.Index(fields=['-date']),
			models.Index(fields=['flow']),
			models.Index(fields=['code']),
			models.Index(fields=['name']),
			models.Index(fields=['-date', 'flow', 'kind', 'code'])
		]


class BrokerageNote(BaseIRPFModel):
	"""Modelo de notas de corretagem"""
	note = models.FileField(verbose_name='Nota de negociação (PDF)',
	                        upload_to='notes',
	                        storage=FileSystemOverwriteStorage())
	institution = models.ForeignKey(Institution,
	                                on_delete=models.CASCADE,
	                                verbose_name="Corretora",
	                                help_text="A corretora que gerou essa nota.")
	reference_date = models.DateField(verbose_name="Data do pregão", null=True)
	settlement_fee = MoneyField(verbose_name="Taxa de liquidação",
	                            max_digits=DECIMAL_MAX_DIGITS,
	                            decimal_places=2)
	registration_fee = MoneyField(verbose_name="Taxa de registro",
	                              max_digits=DECIMAL_MAX_DIGITS,
	                              decimal_places=2)
	term_fee = MoneyField(verbose_name="Taxa de termo/opções",
	                      max_digits=DECIMAL_MAX_DIGITS,
	                      decimal_places=2)
	ana_fee = MoneyField(verbose_name="Taxa A.N.A",
	                     max_digits=DECIMAL_MAX_DIGITS,
	                     decimal_places=2)
	emoluments = MoneyField(verbose_name="Emolumentos",
	                        max_digits=DECIMAL_MAX_DIGITS,
	                        decimal_places=2)
	operational_fee = MoneyField(verbose_name="Taxa Operacional",
	                             max_digits=DECIMAL_MAX_DIGITS,
	                             decimal_places=2)
	execution = MoneyField(verbose_name="Execução",
	                       max_digits=DECIMAL_MAX_DIGITS,
	                       decimal_places=2)
	custody_fee = MoneyField(verbose_name="Taxa de custódia",
	                         max_digits=DECIMAL_MAX_DIGITS,
	                         decimal_places=2)
	taxes = MoneyField(verbose_name="Impostos",
	                   max_digits=DECIMAL_MAX_DIGITS,
	                   decimal_places=2)
	others = MoneyField(verbose_name="Outros",
	                    max_digits=DECIMAL_MAX_DIGITS,
	                    decimal_places=2)

	def __str__(self):
		return f"{self.note} / {self.institution.name}"

	class Meta:
		verbose_name = "Nota de negociação"
		verbose_name_plural = "Notas de negociação"
		ordering = ('-reference_date',)


class AssetEvent(BaseIRPFModel):
	SPLIT, INPLIT = 1, 2
	EVENT_CHOICES = (
		(SPLIT, "Desdobramento"),
		(INPLIT, "Grupamento")
	)
	asset = models.ForeignKey(Asset, on_delete=models.CASCADE,
	                          verbose_name="Ativo",
	                          null=False)
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
	                          null=False)
	institution = models.ForeignKey(Institution,
	                                on_delete=models.SET_NULL,
	                                verbose_name="Instituição",
	                                blank=True, null=True)
	quantity = models.DecimalField(verbose_name="Quantidade",
	                               max_digits=19,
	                               decimal_places=0,
	                               default=Decimal(0))
	avg_price = MoneyField(verbose_name="Preço médio",
	                       max_digits=DECIMAL_MAX_DIGITS,
	                       decimal_places=DECIMAL_PLACES)
	total = MoneyField(verbose_name="Valor total",
	                   max_digits=DECIMAL_MAX_DIGITS,
	                   decimal_places=DECIMAL_PLACES)
	tax = MoneyField(verbose_name="Taxas",
	                 max_digits=DECIMAL_MAX_DIGITS,
	                 decimal_places=DECIMAL_PLACES)
	consolidation = models.PositiveIntegerField(verbose_name="Consolidação",
	                                            choices=CONSOLIDATION_CHOICES,
	                                            default=CONSOLIDATION_YEARLY)
	date = DateField(verbose_name="Data")

	# ao invés de deletar posições, apenas marcamos como inválida
	is_valid = models.BooleanField(verbose_name="Válida", default=True)

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
		indexes = [
			models.Index(fields=['-date'])
		]


class Statistic(BaseIRPFModel):
	"""Estatística de evolução da carteira"""
	CATEGORY_CHOICES = Asset.CATEGORY_CHOICES

	CONSOLIDATION_CHOICES = Position.CONSOLIDATION_CHOICES
	CONSOLIDATION_YEARLY = Position.CONSOLIDATION_YEARLY
	CONSOLIDATION_MONTHLY = Position.CONSOLIDATION_MONTHLY

	category = models.IntegerField(verbose_name="Categoria",
	                               help_text="Categoria de ativos.",
	                               choices=CATEGORY_CHOICES)

	consolidation = models.PositiveIntegerField(
		verbose_name="Consolidação",
		choices=CONSOLIDATION_CHOICES,
		default=CONSOLIDATION_YEARLY
	)

	institution = models.ForeignKey(Institution,
	                                on_delete=models.CASCADE,
	                                verbose_name="Instituição",
	                                blank=True, null=True)
	cumulative_losses = MoneyField(verbose_name="Prejuízos acumulados",
	                               max_digits=DECIMAL_MAX_DIGITS,
	                               decimal_places=DECIMAL_PLACES,
	                               amount_default=Decimal(0),
	                               blank=True)
	residual_taxes = MoneyField(verbose_name="Impostos residuais",
	                            max_digits=DECIMAL_MAX_DIGITS,
	                            decimal_places=DECIMAL_PLACES,
	                            amount_default=Decimal(0),
	                            blank=True)
	date = DateField(verbose_name="Data")
	valid = models.BooleanField(verbose_name="Válido", editable=False, default=True)

	def __str__(self):
		msg = []
		dt = date_format(self.date)
		label = Position.consolidation_choices[self.consolidation]
		msg.append(f"Estatística ({label.lower()}) até {dt}")
		if self.institution:
			msg.append(f" - {self.institution.name}")
		return ' '.join(msg)

	class Meta:
		unique_together = (
			"category",
			"consolidation",
			"institution",
			"user",
			"date"
		)
		ordering = ('category', '-date',)
		verbose_name = "Estatística de dado"
		verbose_name_plural = verbose_name + "s"
		indexes = [
			models.Index(fields=['-date'])
		]


class Taxes(BaseIRPFModel):
	"""Modelo usado para registro de impostos a pagar"""
	TAX_CHOICES = [
		(None, "Valor líquido"),
		(15, "15%"),
		(20, "20%")
	]
	total = MoneyField(verbose_name="Valor",
	                   max_digits=DECIMAL_MAX_DIGITS,
	                   help_text="O valor deve ser bruto quando uma alíquota (taxa) for selecionada.",
	                   decimal_places=DECIMAL_PLACES,
	                   amount_default=None)

	category = models.IntegerField(verbose_name="Categoria",
	                               help_text="Categoria para a qual o valor do imposto de se aplica.",
	                               choices=Asset.CATEGORY_CHOICES)

	tax = models.PositiveIntegerField(verbose_name="Taxa",
	                                  choices=TAX_CHOICES,
	                                  help_text="alíquota (taxa) do imposto.",
	                                  null=True, blank=True)

	asset = models.ForeignKey(Asset, on_delete=models.SET_NULL,
	                          verbose_name="Ativo",
	                          null=True, blank=True)
	description = models.TextField(verbose_name="Descrição", blank=True)

	created_date = DateField(verbose_name="Data inicial de apuração",
	                         help_text="Informe o mês/ano de apuração do imposto (mês válido para o IRPF).",
	                         blank=False, null=True)
	pay_date = DateField(verbose_name="Data do pagamento",
	                     help_text="Informe o mês/ano da data de pagamento do imposto.",
	                     blank=True, null=True)
	auto_created = models.BooleanField(verbose_name="Criação automática",
	                                   editable=False, default=False)
	paid = models.BooleanField(verbose_name="Pago", default=False,
	                           help_text="Uma vez marcado, informa que o imposto já foi pago.")
	created = models.DateTimeField(verbose_name="Data de registro", auto_now_add=True)

	stats = models.ManyToManyField(Statistic, verbose_name="Estatísticas", editable=False)

	@classproperty
	def taxes_choices(cls):
		return dict(cls.TAX_CHOICES)

	@property
	def taxes_to_pay(self):
		# com o valor líquido o total deverá ser pago
		if self.tax:
			taxes = self.total * (self.tax / decimal.Decimal(100))
		else:
			taxes = self.total
		return taxes

	def __str__(self):
		paid = "pago" if self.paid else "devendo"
		return f"{self.total} - {self.taxes_choices[self.tax]} - {paid}"

	class Meta:
		verbose_name = "Imposto"
		verbose_name_plural = verbose_name + "s"
		ordering = ('-created_date', 'category')


class TaxRate(BaseIRPFModel):
	darf = MoneyField(verbose_name="Valor mínimo (DARF)",
	                  max_digits=DECIMAL_MAX_DIGITS,
	                  amount_default=Decimal('10'),
	                  decimal_places=2)

	stock_exempt_profit = MoneyField(
		verbose_name="Ações (Lucro isento)",
		max_digits=DECIMAL_MAX_DIGITS,
		amount_default=Decimal('20000'),
		decimal_places=2
	)

	valid_start = models.DateField(verbose_name="Começa em", default=timezone.now)
	valid_until = models.DateField(verbose_name="Válido até", default=timezone.now)

	valid_ranges = defaultdict(dict)

	class Meta:
		verbose_name = "Alíquota"
		verbose_name_plural = verbose_name + "s"
		ordering = ('-valid_until',)

	def __str__(self):
		return f"{self.valid_start}-{self.valid_until}"

	@classmethod
	def create_instance(cls, start_date: datetime.date, end_date: datetime.date):
		"""Cria um objeto tax rate se pk"""
		stock = settings.TAX_RATE['stock']
		fii = settings.TAX_RATE['fii']
		bdr = settings.TAX_RATE['bdr']
		stock_subscription = settings.TAX_RATE['stock_subscription']
		fii_subscription = settings.TAX_RATE['fii_subscription']
		tax_rate = cls(darf=Decimal(settings.TAX_RATE['darf_min_value']),
		               stock_exempt_profit=Decimal(stock['exempt_profit']),
		               valid_start=start_date,
		               valid_until=end_date)
		tax_rate.daytrade = DayTrade(stock=Decimal(stock['day_trade']),
		                             fii=Decimal(fii['day_trade']),
		                             bdr=Decimal(bdr['day_trade']),
		                             stock_subscription=Decimal(stock_subscription['day_trade']),
		                             fii_subscription=Decimal(fii_subscription['day_trade']))
		tax_rate.swingtrade = SwingTrade(stock=Decimal(stock['swing_trade']),
		                                 fii=Decimal(fii['swing_trade']),
		                                 bdr=Decimal(bdr['swing_trade']),
		                                 stock_subscription=Decimal(stock_subscription['swing_trade']),
		                                 fii_subscription=Decimal(fii_subscription['swing_trade']))
		return tax_rate

	@classmethod
	def get_from_date(cls, user, start_date: datetime.date, end_date: datetime.date):
		if (tax_rate := cls.valid_ranges[user].get((start_date, end_date))) is None:
			qs = cls.objects.filter(valid_start__lte=start_date, valid_until__gte=end_date)
			if (tax_rate := qs.first()) is None:
				tax_rate = cls.create_instance(start_date, end_date)
			cls.valid_ranges[user][(start_date, end_date)] = tax_rate
		return tax_rate

	@classmethod
	def cache_clear(cls, user, forced=False):
		if forced or len(cls.valid_ranges[user]) >= 24:
			cls.valid_ranges[user].clear()

	def save(self, *args, **kwargs):
		try:
			return super().save(*args, **kwargs)
		finally:
			type(self).cache_clear(self.user, forced=True)


class AbstractTradeRate(BaseIRPFModel):
	stock = models.DecimalField(verbose_name="Ações",
	                            max_digits=DECIMAL_MAX_DIGITS,
	                            decimal_places=2)
	stock_subscription = models.DecimalField(verbose_name="Ações (subscrições)",
	                                         max_digits=DECIMAL_MAX_DIGITS,
	                                         decimal_places=2)
	fii = models.DecimalField(verbose_name="Fundos imobiliários",
	                          max_digits=DECIMAL_MAX_DIGITS,
	                          decimal_places=2)

	fii_subscription = models.DecimalField(verbose_name="Fundos imobiliários (subscrições)",
	                                       max_digits=DECIMAL_MAX_DIGITS,
	                                       decimal_places=2)
	bdr = models.DecimalField(verbose_name="BDRS",
	                          max_digits=DECIMAL_MAX_DIGITS,
	                          decimal_places=2)
	alias: str = None

	@staticmethod
	def _get_percent(value: Decimal) -> Decimal:
		return value / Decimal(100)

	@cached_property
	def stock_percent(self):
		return self._get_percent(self.stock)

	@cached_property
	def stock_subscription_percent(self):
		return self._get_percent(self.stock_subscription)

	@cached_property
	def fii_percent(self):
		return self._get_percent(self.fii)

	@cached_property
	def fii_subscription_percent(self):
		return self._get_percent(self.fii_subscription)

	@cached_property
	def bdr_percent(self):
		return self._get_percent(self.bdr)

	@classmethod
	def setup_defaults(cls):
		stock = settings.TAX_RATE['stock']
		fii = settings.TAX_RATE['fii']
		bdr = settings.TAX_RATE['bdr']

		stock_subscription = settings.TAX_RATE['stock_subscription']
		fii_subscription = settings.TAX_RATE['fii_subscription']

		opts = cls._meta

		opts.get_field('stock').default = Decimal(stock[cls.alias])
		opts.get_field('fii').default = Decimal(fii[cls.alias])
		opts.get_field('bdr').default = Decimal(bdr[cls.alias])

		opts.get_field('stock_subscription').default = Decimal(stock_subscription[cls.alias])
		opts.get_field('fii_subscription').default = Decimal(fii_subscription[cls.alias])
		return cls

	class Meta:
		abstract = True


class DayTrade(AbstractTradeRate):
	tax_rate = models.OneToOneField(TaxRate, on_delete=models.CASCADE)
	alias = 'day_trade'

	class Meta:
		verbose_name = "Day trade (negociações)"
		verbose_name_plural = verbose_name


class SwingTrade(AbstractTradeRate):
	tax_rate = models.OneToOneField(TaxRate, on_delete=models.CASCADE)
	alias = 'swing_trade'

	class Meta:
		verbose_name = "Swing trade (negociações)"
		verbose_name_plural = verbose_name
