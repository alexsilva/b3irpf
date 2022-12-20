from xadmin import sites

from irpf.models import Enterprise, Negotiation


@sites.register(Enterprise)
class EnterpriseAdmin:
	...


@sites.register(Negotiation)
class NegotiationAdmin:
	list_filter = ("kind",)
	list_display = (
		"code",
		"kind",
		"institution",
		"quantity",
		"total",
		"date"
	)
