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
	def compile(date: datetime.date, reports: OrderedDict[int]):
		if len(reports) == 1:
			return reports[date.month].get_results()
		assets = OrderedDict()
		for month in reports:
			for _asset in reports[month].get_results():
				if (asset := assets.get(_asset.ticker)) is None:
					asset = assets[_asset.ticker] = Assets(
						ticker=_asset.ticker,
						institution=_asset.institution,
						instance=_asset.instance
					)
				asset.update(_asset)
		return list(assets.values())

	def get_queryset(self, start_date: datetime.date, end_date: datetime.date, **options):
		qs_options = dict(
			user=self.user,
			date__gte=start_date,
			date__lte=end_date,
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

	def generate(self, start_date: datetime.date, end_date: datetime.date, **options):
		self.options.setdefault('start_date', start_date)
		self.options.setdefault('end_date', end_date)
		self.options.update(**options)
		institution = options.get('institution')
		asset = options.get('asset')
		assets = {}
		if asset:
			options['asset'] = asset
			assets[asset.code] = Assets(ticker=asset.code,
			                            institution=institution,
			                            instance=asset)
			for obj in self.get_queryset(start_date, end_date, **options):
				self.consolidate(obj, assets[asset.code])
		else:
			for asset in self.asset_model.objects.all():
				assets[asset.code] = Assets(ticker=asset.code,
				                            institution=institution,
				                            instance=asset)
				options['asset'] = asset
				for obj in self.get_queryset(start_date, end_date, **options):
					self.consolidate(obj, assets[asset.code])

		# atualização resultados
		self.results.clear()
		self.results.extend(assets.values())
		self.results.sort(key=self.results_sorted)

		# limpeza do cache
		self.cache.clear()
		return self.results
