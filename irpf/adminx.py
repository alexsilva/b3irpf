from xadmin import sites

from irpf.models import Institution, Negotiation


@sites.register(Institution)
class InstitutionAdmin:
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
