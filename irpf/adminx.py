from correpy.parsers.brokerage_notes.b3_parser.nuinvest import NunInvestParser
from django.contrib.auth import get_permission_codename
from django.core.management import call_command

from xadmin import sites, site
from xadmin.views import ListAdminView, ModelFormAdminView

from irpf.models import Enterprise, Negotiation, Earnings, Position, Instituition, Bonus, Bookkeeping, \
	BrokerageNote, AssetEvent, FoundsAdministrator
from irpf.plugins import ListActionModelPlugin, GuardianAdminPlugin, AssignUserAdminPlugin, SaveReportPositionPlugin, \
	ReportStatsAdminPlugin, BrokerageNoteAdminPlugin
from irpf.views.import_list import AdminImportListModelView
from irpf.views.report_irpf import AdminReportIrpfModelView
from irpf.views.xlsx_viewer import AdminXlsxViewer

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


@sites.register(Instituition)
class InstituitionAdmin:
	model_icon = "fa fa-university"
	list_display = (
		"name",
		"cnpj"
	)


class BaseIRPFAdmin:
	readonly_fields = ()
	# GuardianAdminPlugin
	guardian_protected = True
	# AssignUserAdminPlugin
	assign_current_user = True

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


@sites.register(Enterprise)
class EnterpriseAdmin:
	model_icon = "fa fa-coffee"
	list_filter = ("category", "bookkeeping")
	search_fields = ("code", "name", "cnpj", "adminstrator__name")
	list_display = (
		'code',
		'category',
		'name',
		'cnpj',
		'adminstrator',
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
	list_filter = ("enterprise__code", 'institution')
	search_fields = (
		'enterprise__code',
		'enterprise__name',
		'institution__name'
	)
	list_display = (
		'enterprise_code',
		'enterprise_name',
		'institution',
		'quantity',
		'avg_price',
		'date'
	)

	def enterprise_code(self, instance):
		return instance.enterprise.code

	enterprise_code.is_column = True
	enterprise_code.admin_order_field = "enterprise__code"
	enterprise_code.short_description = _get_field_opts("code", Enterprise).verbose_name

	def enterprise_name(self, instance):
		return instance.enterprise.name

	enterprise_name.is_column = True
	enterprise_name.admin_order_field = "enterprise__name"
	enterprise_name.short_description = _get_field_opts("name", Enterprise).verbose_name


class NegotiationInline:
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
	list_filter = ("kind", "date")
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
		'enterprise',
		'base_value',
		'proportion'
	)


@sites.register(AssetEvent)
class AssetEventAdmin(BaseIRPFAdmin):
	model_icon = "fa fa-sticky-note-o"
	list_display = (
		'date',
		'enterprise_name',
		'date_com',
		'event',
		'factor_from',
		'factor_to'
	)

	def enterprise_name(self, instance):
		return instance.enterprise.name

	enterprise_name.is_column = True
	enterprise_name.admin_order_field = "enterprise__name"
	enterprise_name.short_description = _get_field_opts("name", Enterprise).verbose_name


@sites.register(Earnings)
class EarningsAdmin(BaseIRPFAdmin):
	list_filter = ("kind", "date")
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
