import copy
import datetime

from django.utils.text import slugify

from irpf.models import Enterprise, Earnings, Bonus, Position
from irpf.report.utils import Earning, Asset, Buy
from irpf.utils import range_dates


class EaningsReport:
	earnings_models = Earnings

	def __init__(self, flow, user, **options):
		self.flow = flow
		self.user = user
		self.options = options

	def get_queryset(self, **options):
		return self.earnings_models.objects.filter(**options)

	def report(self, code, start, end=None, **options):
		qs_options = dict(
			flow__iexact=self.flow,
			user=self.user,
			date__gte=start,
			code__iexact=code
		)
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution.name
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['code'] = enterprise.code
		if end is not None:
			qs_options['date__lte'] = end
		earnings = {}
		try:
			qs = self.get_queryset(**qs_options)
			for instance in qs:
				kind = slugify(instance.kind).replace('-', "_")
				try:
					earning = earnings[kind]
				except KeyError:
					earnings[kind] = earning = Earning(instance.kind)

				earning.items.append(instance)
				earning.quantity += instance.quantity
				earning.value += instance.total
		except self.earnings_models.DoesNotExist:
			pass
		return earnings


class NegotiationReport:
	enterprise_model = Enterprise
	position_model = Position
	bonus_model = Bonus

	buy, sell = "compra", "venda"

	def __init__(self, model, user, **options):
		self.model = model
		self.user = user
		self.options = options
		self.earnings_report = EaningsReport("Credito", user=self.user)

	def get_enterprise(self, code):
		"""A empresa"""
		try:
			enterprise = self.enterprise_model.objects.get(code__iexact=code)
		except self.enterprise_model.DoesNotExist:
			enterprise = None
		return enterprise

	def get_queryset(self, *args, **kwargs):
		return self.model.objects.filter(*args, **kwargs)

	def add_bonus(self, date, history, assets, **options):
		"""Adiciona ações bonificadas na data com base no histórico"""
		qs_options = {}
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['enterprise'] = enterprise
		queryset = self.bonus_model.objects.filter(date=date, user=self.user,
		                                           **qs_options)
		for bonus in queryset:
			try:
				asset = assets[bonus.enterprise.code]
			except KeyError:
				continue
			# ignora os registros que já foram contabilizados na posição
			if asset.position and bonus.date < asset.position.date:
				continue

			# total de ativos na data ex
			history_date_ex = history[bonus.date_ex]
			history_asset = history_date_ex[bonus.enterprise.code]

			# valor quantidade e valores recebidos de bonificação
			bonus_quantity = int(history_asset.buy.quantity * (bonus.proportion / 100.0))
			bonus_value = bonus_quantity * bonus.base_value

			# adição dos novos ativos
			asset.buy.quantity += bonus_quantity
			asset.buy.total += bonus_value

			# novo preço médio já com a bonifição
			asset.buy.avg_price = asset.buy.total / float(asset.buy.quantity)

	def consolidate(self, instance, asset: Asset):
		kind = instance.kind.lower()

		if kind == self.buy:
			# valores de compras
			asset.buy.tax += instance.tax
			asset.buy.quantity += instance.quantity
			asset.buy.total += ((instance.quantity * instance.price) + instance.tax)
			asset.buy.avg_price = asset.buy.total / float(asset.buy.quantity)
		elif kind == self.sell:
			# valores de venda
			asset.sell.tax += instance.tax
			asset.sell.quantity += instance.quantity
			asset.sell.total += (instance.quantity * instance.price)
			asset.sell.avg_price = (asset.sell.total / float(asset.sell.quantity))

			# ganho de capital de todas a vendas
			asset.sell.capital += ((instance.quantity * (instance.price - asset.buy.avg_price)) - instance.tax)

			# novos valores para compra
			asset.buy.quantity -= instance.quantity
			asset.buy.total = asset.buy.quantity * asset.buy.avg_price
		return asset

	def get_queryset_position(self, date, **options):
		"""Mota e retorna a queryset de posição"""
		qs_options = {}
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['enterprise'] = enterprise
		startdate = options.get('startdate')
		if startdate is None:
			startdate = date - datetime.timedelta(days=365)
		qs_options.setdefault(options.get('query_startdate', 'date__gte'), startdate)
		qs_options.setdefault(options.get('query_enddate', 'date__lte'), date)
		queryset = self.position_model.objects.filter(
			user=self.user,
			**qs_options
		).order_by('date')
		return queryset

	def get_assets_position(self, date=None, queryset=None, **options):
		"""Retorna dados de posição para caculo do período"""
		assets = {}
		if queryset is None:
			queryset = self.get_queryset_position(date, **options)
		for position in queryset:
			ticker = position.enterprise.code
			asset = Asset(ticker=ticker,
			              institution=position.institution,
			              enterprise=position.enterprise,
			              position=position,
			              buy=Buy(
							quantity=position.quantity,
							avg_price=position.avg_price,
							total=position.total,
							tax=position.tax,
							date=position.date
						))
			assets[ticker] = asset
		return assets

	def report(self, dtstart, dtend, **options):
		assets, history = self.get_assets_position(date=dtstart, **options), {}
		qs_options = {'user': self.user}
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution.name
		enterprise = options.get('enterprise')
		if enterprise:  # Permite filtrar por empresa (ativo)
			qs_options['code'] = enterprise.code

		# cache
		queryset_position = self.get_queryset_position(date=dtend,
		                                               startdate=dtstart,
		                                               **options)
		queryset_assets = self.get_queryset(**qs_options)

		for date in range_dates(dtstart, dtend):  # calcula um dia por vez
			assets_position = self.get_assets_position(queryset=queryset_position.filter(date=date))
			if assets_position:
				assets.update(assets_position)
			queryset = queryset_assets.filter(date=date)
			for instance in queryset:
				# calculo de compra, venda, boficiação, etc
				try:
					asset = assets[instance.code]
				except KeyError:
					asset = Asset(ticker=instance.code,
					              institution=institution,
					              enterprise=enterprise)
					assets[instance.code] = asset
				asset.items.append(instance)
				# ignora os registros que já foram contabilizados na posição
				if asset.position and instance.date < asset.position.date:
					continue
				self.consolidate(instance, asset)

			# histórico das posições no dia
			if assets:
				history[date] = copy.deepcopy(assets)

			# aplica a bonificiação na data do histórico
			self.add_bonus(date, history, assets, **options)
		results = []
		for code in assets:
			asset = assets[code]
			asset.enterprise = asset.enterprise or self.get_enterprise(code)
			earnings = self.earnings_report.report(code, dtstart, dtend, **options)
			asset.earnings.update(earnings)
			results.append({
				'code': code,
				'institution': institution,
				'enterprise': asset.enterprise,
				'earnings': earnings,
				'asset': asset
			})

		def results_sort_category(item):
			_enterprise = item['enterprise']
			return (_enterprise.category_choices[_enterprise.category]
			        if _enterprise and _enterprise.category else item['code'])

		def results_sort_code(item):
			return item['code']

		results = sorted(results, key=results_sort_code)
		results = sorted(results, key=results_sort_category)
		return results
