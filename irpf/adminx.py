from correpy.parsers.brokerage_notes.b3_parser.nuinvest import NunInvestParser
from django.contrib.auth import get_permission_codename
from django.core.management import call_command
from xadmin import sites, site
from xadmin.views import ListAdminView, ModelFormAdminView, BaseAdminView

from irpf.models import Asset, Negotiation, Earnings, Position, Institution, Bonus, Bookkeeping, \
	BrokerageNote, AssetEvent, FoundsAdministrator, Taxes, Subscription
from irpf.plugins import ListActionModelPlugin, GuardianAdminPlugin, AssignUserAdminPlugin, SaveReportPositionPlugin, \
	ReportStatsAdminPlugin, BrokerageNoteAdminPlugin
from irpf.views.import_list import AdminImportListModelView
from irpf.views.report_irpf import AdminReportIrpfModelView
from irpf.views.xlsx_viewer import AdminXlsxViewer
from moneyfield import MoneyModelForm
from irpf.themes import themes

site.register_view("^irpf/import/(?P<model_app_label>.+)/$", AdminImportListModelView, "import_listmodel")
site.register_view("^irpf/report/(?P<model_app_label>.+)/$", AdminReportIrpfModelView, "reportirpf")
site.register_view("^irpf/xlsx/viewer", AdminXlsxViewer, "xlsx_viewer")

site.register_plugin(ListActionModelPlugin, ListAdminView)
site.register_plugin(GuardianAdminPlugin, ListAdminView)
site.register_plugin(GuardianAdminPlugin, ModelFormAdminView)
site.register_plugin(AssignUserAdminPlugin, ModelFormAdminView)
site.register_plugin(SaveReportPositionPlugin, AdminReportIrpfModelView)
site.register_plugin(ReportStatsAdminPlugin, AdminReportIrpfModelView)
site.register_plugin(BrokerageNoteAdminPlugin, ModelFormAdminView)


def _get_field_opts(name, model):
	return model._meta.get_field(name)


@sites.register(BaseAdminView)
class BaseSetting:
	enable_themes = True
	user_themes = themes
	use_bootswatch = False


@sites.register(Bookkeeping)
class BookkeepingAdmin:
	list_display = (
		"name",
		"cnpj",
		"link"
	)


@sites.register(FoundsAdministrator)
class FoundsAdministratorAdmin:
	list_display = search_fields = (
		"name",
		"cnpj"
	)


@sites.register(Institution)
class InstitutionAdmin:
	model_icon = "fa fa-university"
	list_display = (
		"name",
		"cnpj"
	)


class BaseIRPFAdmin:
	form = MoneyModelForm
	readonly_fields = ()
	# GuardianAdminPlugin
	guardian_protected = True
	# AssignUserAdminPlugin
	assign_current_user = True
	horizontal_form_layout = True

	def has_auth_permission(self, name: str, obj=None):
		if isinstance(self, ModelFormAdminView) and obj is None:
			obj = self.org_obj
		# checks the permission for the object
		permission_codename = get_permission_codename(name, self.opts)
		return self.user.has_perm('%s.%s' % (self.opts.app_label, permission_codename), obj)

	def get_readonly_fields(self):
		readonly_fields = list(super().get_readonly_fields())
		if getattr(self, "org_obj", None):
			readonly_fields.append('user')
		return readonly_fields


@sites.register(Asset)
class AssetAdmin:
	model_icon = "fa fa-coffee"
	list_filter = ("category", "bookkeeping")
	search_fields = ("code", "name", "cnpj", "administrator__name")
	list_display = (
		'code',
		'category',
		'name',
		'cnpj',
		'administrator',
		'bookkeeping_name'
	)

	def bookkeeping_name(self, instance):
		return instance.bookkeeping.name if instance.bookkeeping else None

	bookkeeping_name.is_column = True
	bookkeeping_name.admin_order_field = "bookkeeping__name"
	bookkeeping_name.short_description = "Escriturador"

	def save_models(self):
		try:
			return super().save_models()
		finally:
			try:
				call_command("setup_assets")
			except Exception as exc:
				self.message_user(f"Falha atualizando assets: {exc}")


@sites.register(Position)
class PositionAdmin(BaseIRPFAdmin):
	collect_related_nested_objects = False
	list_filter = (
		"asset__code",
		'consolidation',
		'institution'
	)
	search_fields = (
		'asset__code',
		'asset__name',
		'institution__name'
	)
	list_display = (
		'asset_code',
		'asset_name',
		'consolidation',
		'institution',
		'quantity',
		'avg_price',
		'date'
	)

	def asset_code(self, instance):
		return instance.asset.code

	asset_code.is_column = True
	asset_code.admin_order_field = "asset__code"
	asset_code.short_description = _get_field_opts("code", Asset).verbose_name

	def asset_name(self, instance):
		return instance.asset.name

	asset_name.is_column = True
	asset_name.admin_order_field = "asset__name"
	asset_name.short_description = _get_field_opts("name", Asset).verbose_name


class NegotiationInline:
	form = MoneyModelForm
	model = Negotiation
	style = "accordion"
	extra = 0


@sites.register(BrokerageNote)
class BrokerageNoteAdmin(BaseIRPFAdmin):
	model_icon = "fa fa-book"
	fields = ('note', 'institution')
	list_display = ('note', 'institution', 'reference_date', 'negotiation_count')
	brokerage_note_parsers = {
		# NU INVEST CORRETORA DE VALORES S.A.
		'62169875000179': NunInvestParser
	}
	brokerage_note_field_update = [
		'reference_date',
		'settlement_fee',
		'registration_fee',
		'term_fee',
		'ana_fee',
		'emoluments',
		'operational_fee',
		'execution',
		'custody_fee',
		'taxes',
		'others'
	]
	inlines = [NegotiationInline]

	def negotiation_count(self, instance):
		"""Informa de total de ativos vinculados a nota"""
		return instance.negotiation_set.count()

	negotiation_count.short_description = "Total de negociações"

	def get_readonly_fields(self):
		readonly_fields = list(super().get_readonly_fields())
		for field_name in self.brokerage_note_field_update:
			if field_name not in readonly_fields:
				readonly_fields.append(field_name)
		return readonly_fields


@sites.register(Negotiation)
class NegotiationAdmin(BaseIRPFAdmin):
	collect_related_nested_objects = False
	model_icon = "fa fa-credit-card-alt"
	list_filter = ("kind", "date", "asset")
	search_fields = ("code",)
	list_display = (
		"code",
		"kind",
		"institution",
		"quantity",
		"price",
		"total",
		"tax",
		"date",
	)


@sites.register(Bonus)
class BonusAdmin(BaseIRPFAdmin):
	list_display = (
		'asset',
		'base_value',
		'proportion'
	)


@sites.register(Subscription)
class SubscriptionAdmin(BaseIRPFAdmin):
	search_fields = (
		'asset__code',
		'asset__name'
	)
	list_filter = ("date", "asset")
	list_display = (
		'asset',
		'price',
		'proportion'
	)


@sites.register(AssetEvent)
class AssetEventAdmin(BaseIRPFAdmin):
	model_icon = "fa fa-sticky-note-o"
	list_display = (
		'date',
		'asset_name',
		'date_com',
		'event',
		'factor_from',
		'factor_to'
	)

	def asset_name(self, instance):
		return instance.asset.name

	asset_name.is_column = True
	asset_name.admin_order_field = "asset__name"
	asset_name.short_description = _get_field_opts("name", Asset).verbose_name


@sites.register(Earnings)
class EarningsAdmin(BaseIRPFAdmin):
	list_filter = ("kind", "date", "asset")
	search_fields = ("code",)
	list_display = (
		"flow",
		"kind",
		"code",
		"name",
		"institution",
		"quantity",
		"total",
		"date"
	)


@sites.register(Taxes)
class TaxesAdmin(BaseIRPFAdmin):
	list_display = (
		"created",
		"total",
		"category",
		"tax",
		"taxes_to_pay",
		"paid"
	)

	def taxes_to_pay(self, instance):
		return str(instance.taxes_to_pay)

	taxes_to_pay.is_column = False
	taxes_to_pay.short_description = "A pagar"

