import datetime
from collections import OrderedDict

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

	@staticmethod
	def compile(date: datetime.date, reports):
		assets = OrderedDict()
		for month in reports:
			for item in reports[month].get_results():
				_asset = item['asset']
				if (asset := assets.get(_asset.ticker)) is None:
					asset = assets[_asset.ticker] = Assets(
						ticker=_asset.ticker,
						institution=_asset.institution,
						instance=_asset.instance
					)
				asset.update(_asset)
		results = []
		for ticker in assets:
			asset = assets[ticker]
			results.append({
				'code': ticker,
				'institution': asset.institution,
				'instance': asset.instance,
				'asset': asset
			})
		return results

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

	def generate(self, date_start, date_end, **options):
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

		self.results.clear()
		for code in assets:
			asset = assets[code]
			self.results.append({
				'code': code,
				'institution': institution,
				'instance': asset.instance,
				'asset': asset
			})
		self.cache.clear()
		self.results.sort(key=self.results_sorted)
		return self.results
