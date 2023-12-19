from assetprice.models import AssetEarningHistory
from irpf.models import (
	Bookkeeping,
	FoundsAdministrator,
	Asset,
	Institution,
	Negotiation,
	Bonus,
	Earnings,
	BrokerageNote,
	AssetEvent,
	Position,
	Taxes,
	Subscription,
	BonusInfo,
	SubscriptionInfo,
	Statistic,
	TaxRate,
	DayTrade,
	SwingTrade
)

permission_all = ('view', 'add', 'change', 'delete')

permission_models = {
	TaxRate: permission_all,
	DayTrade: permission_all,
	SwingTrade: permission_all,
	AssetEarningHistory: permission_all,
	Bookkeeping: ('view', 'add'),
	FoundsAdministrator: ('view', 'add'),
	Asset: ('view', 'add', 'change'),
	Institution: ('view', 'add', 'change'),
	Negotiation: permission_all,
	Bonus: permission_all,
	BonusInfo: permission_all,
	Subscription: permission_all,
	SubscriptionInfo: permission_all,
	Earnings: permission_all,
	BrokerageNote: permission_all,
	AssetEvent: permission_all,
	Position: permission_all,
	Taxes: permission_all,
	Statistic: permission_all,
}
