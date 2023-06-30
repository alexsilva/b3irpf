from irpf.models import Asset, Earnings
from irpf.report.base import BaseReport
from irpf.report.utils import Assets, Event


class EarningsReport(BaseReport):
	asset_model = Asset

	def __init__(self, model, user, **options):
		super().__init__(model, user, **options)

	def consolidate(self, instance: Earnings, asset: Assets):
		obj = getattr(asset, "credit" if instance.is_credit else "debit")
		kind_slug = instance.kind_slug
		try:
			event = obj[kind_slug]
		except KeyError:
			obj[kind_slug] = event = Event(instance.kind)

		event.items.append(instance)
		event.quantity += instance.quantity
		event.value += instance.total

	def get_queryset(self, date_start, date_end, **options):
		qs_options = dict(
			user=self.user,
			date__gte=date_start,
			date__lte=date_end,
		)
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution.name
		asset = options.get('asset')
		if asset:
			qs_options['code'] = asset.code
		categories = options['categories']
		if categories:
			qs_options['asset__category__in'] = categories
		queryset = self.model.objects.filter(**qs_options)
		return queryset

	def report(self, date_start, date_end, **options):
		results = []
		assets = {}
		asset = options.get('asset')
		institution = options.get('institution')
		if asset:
			options['asset'] = asset
			assets[asset.code] = Assets(ticker=asset.code,
			                            institution=institution,
			                            instance=asset)
			for obj in self.get_queryset(date_start, date_end, **options):
				self.consolidate(obj, assets[asset.code])
		else:
			for asset in self.asset_model.objects.all():
				assets[asset.code] = Assets(ticker=asset.code,
				                            institution=institution,
				                            instance=asset)
				options['asset'] = asset
				for obj in self.get_queryset(date_start, date_end, **options):
					self.consolidate(obj, assets[asset.code])

		for code in assets:
			asset = assets[code]
			results.append({
				'code': code,
				'institution': institution,
				'instance': asset.instance,
				'asset': asset
			})

		results = sorted(results, key=self.results_sorted)
		return results
