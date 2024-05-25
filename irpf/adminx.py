from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth import get_permission_codename
from django.core.management import call_command
from django.forms import ModelForm
from xadmin.plugins.auth import UserAdmin

from xadmin.sites import NotRegistered

from xadmin.models import Log
from irpf import permissions
from irpf.models import Asset, Negotiation, Earnings, Position, Institution, Bonus, Bookkeeping, \
	BrokerageNote, AssetEvent, FoundsAdministrator, Taxes, Subscription, BonusInfo, TaxRate, DayTrade, \
	SwingTrade, AssetConvert, AssetRefund
from irpf.plugins import ListActionModelPlugin, GuardianAdminPlugin, AssignUserAdminPlugin, \
	ReportSavePositionAdminPlugin, \
	ReportStatsAdminPlugin, BrokerageNoteAdminPlugin, BreadcrumbMonthsAdminPlugin
from irpf.report.earnings import EarningsReportMonth
from irpf.report.negotiation import NegotiationReportMonth
from irpf.themes import themes
from irpf.utils import MonthYearDates
from irpf.views.import_list import AdminImportListModelView
from irpf.views.report_irpf import ReportIRPFFAdminView
from irpf.views.xlsx_viewer import AdminXlsxViewer
from irpf.widgets import MonthYearField, MonthYearWidget
from moneyfield import MoneyModelForm
from xadmin import sites, site
from xadmin.adminx import LogAdmin
from xadmin.views import ListAdminView, ModelFormAdminView, BaseAdminView, ModelAdminView

site.register_view("^irpf/import/(?P<model_app_label>.+)/$", AdminImportListModelView, "import_listmodel")
site.register_view("^irpf/report/(?P<model_app_label>.+)/$", ReportIRPFFAdminView, "reportirpf")
site.register_view("^irpf/xlsx/viewer", AdminXlsxViewer, "xlsx_viewer")

site.register_plugin(ListActionModelPlugin, ListAdminView)
site.register_plugin(GuardianAdminPlugin, ListAdminView)
site.register_plugin(GuardianAdminPlugin, ModelFormAdminView)
site.register_plugin(AssignUserAdminPlugin, ModelFormAdminView)
site.register_plugin(ReportSavePositionAdminPlugin, ReportIRPFFAdminView)
site.register_plugin(ReportStatsAdminPlugin, ReportIRPFFAdminView)
site.register_plugin(BreadcrumbMonthsAdminPlugin, ReportIRPFFAdminView)
site.register_plugin(BrokerageNoteAdminPlugin, ModelFormAdminView)


User = get_user_model()


def _get_field_opts(name, model):
	return model._meta.get_field(name)


@sites.register(ModelAdminView)
class ModelIRPFAdminViewOpts:
	horizontal_form_layout = True


@sites.register(ReportIRPFFAdminView)
class ReportIRPFFAdminViewOptions:
	# Configuração de permissão para cada model (as mesmas usadas no setup_permission)
	# Utilizadas para configurar permissões de objeto
	guardian_permissions_models = permissions.permission_models
	models_report_class = {
		Negotiation: NegotiationReportMonth,
		Earnings: EarningsReportMonth
	}


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

	# Configuração de permissão para cada model (as mesmas usadas no setup_permission)
	# Utilizadas para configurar permissões de objeto
	guardian_permissions_models = permissions.permission_models

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


class BaseHorizontalInline:
	horizontal_form_layout = True


class TradeModelForm(ModelForm):
	def has_changed(self, *args, **kwargs):
		# sempre cria uma nova instância para o inline
		if self.instance.pk is None:
			return True
		return super().has_changed(*args, **kwargs)


class DayTradeInline(BaseHorizontalInline):
	form = TradeModelForm
	model = DayTrade
	style = "one"


class SwingTradeInline(BaseHorizontalInline):
	form = TradeModelForm
	model = SwingTrade
	style = "one"


@sites.register(TaxRate)
class TaxRateAdmin(BaseIRPFAdmin):
	inlines = [DayTradeInline, SwingTradeInline]
	list_display = ['valid_start', 'valid_until']


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
		'institution',
		'is_valid',
		'date'
	)
	search_fields = (
		'asset__code',
		'asset__name',
		'institution__name',
		'date'
	)
	list_display = (
		'asset_code',
		'asset_name',
		'consolidation',
		'institution',
		'quantity',
		'avg_price',
		'is_valid',
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


class NegotiationInline(BaseHorizontalInline):
	form = MoneyModelForm
	model = Negotiation
	style = "accordion"
	extra = 0


@sites.register(BrokerageNote)
class BrokerageNoteAdmin(BaseIRPFAdmin):
	model_icon = "fa fa-book"
	fields = ('note',)
	list_display = (
		'reference_id',
		'reference_date',
		'note',
		'institution',
		'negotiation_count'
	)
	list_filter = (
		'reference_id',
		'institution',
		'reference_date'
	)
	brokerage_note_field_update = [
		'reference_id',
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
		if self.org_obj and self.org_obj.pk is not None:
			for field_name in self.brokerage_note_field_update:
				if field_name not in readonly_fields:
					readonly_fields.append(field_name)
		return readonly_fields


@sites.register(Negotiation)
class NegotiationAdmin(BaseIRPFAdmin):
	collect_related_nested_objects = False
	list_action_activate = True
	model_icon = "fa fa-credit-card-alt"
	list_filter = ("kind", "date", "asset")
	search_fields = ("code",)
	list_display = (
		"code",
		"kind",
		"quantity",
		"date",
		"price",
		"total",
		"tax",
		"institution_name"
	)


class BonusInfoInline(BaseHorizontalInline):
	form = MoneyModelForm
	model = BonusInfo
	style = "one"


@sites.register(Bonus)
class BonusAdmin(BaseIRPFAdmin):
	inlines_options = []
	search_fields = (
		'asset__code',
		'asset__name'
	)
	list_filter = ("date", "asset")
	list_display = (
		'asset',
		'base_value',
		'proportion',
		'date_com',
		'date'
	)

	@property
	def inlines(self):
		view = getattr(self, "admin_view", self)
		inlines = list(view.inlines_options)
		bonus_info_inline = BonusInfoInline
		try:
			if view.org_obj and view.org_obj.bonusinfo:
				inlines.append(bonus_info_inline)
		except bonus_info_inline.model.DoesNotExist:
			...
		return inlines

	@inlines.setter
	def inlines(self, value):
		view = getattr(self, "admin_view", self)
		view.inlines_options = value


@sites.register(Subscription)
class SubscriptionAdmin(BaseIRPFAdmin):
	inlines = [NegotiationInline]
	form = ModelForm
	search_fields = (
		'asset__code',
		'asset__name'
	)
	list_filter = ("date", "asset")
	list_display = (
		'asset',
		'created',
		'date'
	)


@sites.register(AssetRefund)
class AssetRefundAdmin(BaseIRPFAdmin):
	model_icon = "fa fa-money-check-alt"
	search_fields = ("asset__name",)
	list_filter = ("date", "asset")
	list_display = (
		'date',
		'asset_name',
		'value',
	)

	def asset_name(self, instance):
		return instance.asset.name

	asset_name.is_column = True
	asset_name.admin_order_field = "asset__name"
	asset_name.short_description = _get_field_opts("name", Asset).verbose_name


@sites.register(AssetEvent)
class AssetEventAdmin(BaseIRPFAdmin):
	form = ModelForm
	model_icon = "fa fa-sticky-note"
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


@sites.register(AssetConvert)
class AssetConvertAdmin(BaseIRPFAdmin):
	form = ModelForm
	model_icon = "fab fa-sith"
	list_display = (
		'origin',
		'target',
		'date',
		'factor_from',
		'factor_to',
		'limit'
	)


@sites.register(Earnings)
class EarningsAdmin(BaseIRPFAdmin):
	list_action_activate = True
	list_filter = ("kind", "date", "asset")
	search_fields = ("code",)
	list_display = (
		"flow",
		"kind",
		"code",
		"name",
		"institution_name",
		"quantity",
		"total",
		"date"
	)


class TaxesMoneyModelForm(ModelForm):
	def clean_created_date(self):
		created_date: MonthYearDates = self.cleaned_data['created_date']
		return created_date.to_date

	def clean_pay_date(self):
		pay_date: MonthYearDates = self.cleaned_data['pay_date']
		return pay_date.to_date


@sites.register(Taxes)
class TaxesAdmin(BaseIRPFAdmin):
	# para evitar conflito com a meta classe
	form = type("MoneyModelForm", (TaxesMoneyModelForm, MoneyModelForm), {})
	list_display = (
		"created",
		"total",
		"category",
		"tax",
		"taxes_to_pay",
		"created_date",
		"pay_date",
		"paid"
	)
	formfield_classes = {
		'created_date': MonthYearField,
		'pay_date': MonthYearField
	}
	formfield_widgets = {
		'created_date': MonthYearWidget(attrs={'class': "form-control my-1"}),
		'pay_date': MonthYearWidget(attrs={'class': "form-control my-1"})
	}

	def taxes_to_pay(self, instance):
		return str(instance.taxes_to_pay)

	taxes_to_pay.is_column = False
	taxes_to_pay.short_description = "A pagar"

	def get_form_datas(self):
		data = super().get_form_datas()
		if self.request_method == 'get' and data.get('instance') is None:
			initial = data.setdefault('initial', {})
			current_date = datetime.now()
			initial.setdefault('created_date', (current_date.month, current_date.year))
			initial.setdefault('pay_date', (current_date.month, current_date.year))
		return data


try:
	site.unregister(Log)
except NotRegistered:
	...
else:
	@sites.register(Log)
	class LogIRPFAdmin(LogAdmin):

		def queryset(self):
			# permite somente os logs do usuário
			return super().queryset().filter(user=self.user)

		def has_change_permission(self, obj=None):
			return False


try:
	site.unregister(User)
except NotRegistered:
	...
else:
	@sites.register(User)
	class UserIRPFAdmin(UserAdmin):
		horizontal_form_layout = False

		def queryset(self):
			# restringe admins
			qs = super().queryset()
			if not self.request.user.is_superuser:
				qs = qs.exclude(is_superuser=True)
			return qs

		def has_change_permission(self, obj=None):
			has_perm = super().has_change_permission(obj=obj)
			if has_perm and self.request.user != getattr(self, "org_obj", obj):
				has_perm = False
			return has_perm
