from irpf.models import Enterprise, Negotiation, Earnings, Position
from irpf.plugins import ListActionModelPlugin
from irpf.views.import_list import AdminImportListModelView
from irpf.views.report_irpf import AdminReportIrpfModelView
from xadmin import sites, site
from xadmin.views import ListAdminView

site.register_plugin(ListActionModelPlugin, ListAdminView)
site.register_view("^irpf/import-listmodel/(?P<model_app_label>.+)/$", AdminImportListModelView,
                   "import_listmodel")
site.register_view("^ifpf/report-irpf/(?P<model_app_label>.+)/$", AdminReportIrpfModelView,
                   "reportirpf")


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
class PositionAdmin:
	...


@sites.register(Negotiation)
class NegotiationAdmin:
	list_filter = ("kind",)
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
class EarningsAdmin:
	list_filter = ("kind",)
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
