from irpf.models import Enterprise, Negotiation
from irpf.plugins import ImportListModelPlugin
from irpf.views import AdminImportListModelView
from xadmin import sites, site
from xadmin.views import ListAdminView

site.register_plugin(ImportListModelPlugin, ListAdminView)
site.register_view("^irpf/import_listmodel/(?P<model_app_label>.+)/$", AdminImportListModelView,
                   "import_listmodel")


@sites.register(Enterprise)
class EnterpriseAdmin:
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
