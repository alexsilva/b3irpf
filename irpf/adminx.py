from guardian.shortcuts import get_objects_for_user

from irpf.models import Enterprise, Negotiation, Earnings, Position, Instituition, Provision
from irpf.plugins import ListActionModelPlugin
from irpf.views.import_list import AdminImportListModelView
from irpf.views.report_irpf import AdminReportIrpfModelView
from xadmin import sites, site
from xadmin.views import ListAdminView, filter_hook

site.register_plugin(ListActionModelPlugin, ListAdminView)
site.register_view("^irpf/import-listmodel/(?P<model_app_label>.+)/$", AdminImportListModelView,
                   "import_listmodel")
site.register_view("^ifpf/report-irpf/(?P<model_app_label>.+)/$", AdminReportIrpfModelView,
                   "reportirpf")


@sites.register(Instituition)
class InstituitionAdmin:
	list_display = (
		"name",
		"cnpj"
	)


class BaseIRPFAdmin:
	readonly_fields = ("user",)

	@filter_hook
	def queryset(self):
		model_perms = self.get_model_perms()
		model_perms = [f"{name}_{self.opts.model_name}"
		               for name in model_perms if model_perms[name]]
		queryset = get_objects_for_user(
			self.user,
			model_perms,
			klass=self.model,
			any_perm=True,
			with_superuser=False,
			accept_global_perms=False)
		return queryset


@sites.register(Enterprise)
class EnterpriseAdmin:
	list_filter = ("category",)
	search_fields = ("code", "name", "cnpj")
	list_display = (
		'code',
		'category',
		'name',
		'cnpj'
	)


@sites.register(Position)
class PositionAdmin(BaseIRPFAdmin):
	...


@sites.register(Negotiation)
class NegotiationAdmin(BaseIRPFAdmin):
	list_filter = ("kind", "date")
	search_fields = ("code",)
	list_display = (
		"code",
		"kind",
		"institution",
		"quantity",
		"total",
		"date"
	)


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


@sites.register(Provision)
class ProvisionAdmin(BaseIRPFAdmin):
	search_fields = ("code", "kind")
	list_display = (
		'code',
		'name',
		'date_ex',
		'date_payment',
		'kind',
		'quantity',
		'total'
	)
