import copy
import datetime

from django.utils.text import slugify

from irpf.models import Enterprise, Earnings, Bonus, Position, AssetEvent
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
					earning = earnings[kind] = Earning(instance.kind)

				earning.items.append(instance)
				earning.quantity += instance.quantity
				earning.value += instance.total
		except self.earnings_models.DoesNotExist:
			pass
		return earnings


class NegotiationReport:
	earnings_model = Earnings
	enterprise_model = Enterprise
	position_model = Position
	event_model = AssetEvent
	bonus_model = Bonus

	buy, sell = "compra", "venda"
	debt, credit = "debito", "credito"

	BONIFICAO_EM_ATIVOS = "bonificacao_em_ativos"
	LEILAO_DE_FRACAO = "leilao_de_fracao"
	FRACAO_EM_ATIVOS = "fracao_em_ativos"

	def __init__(self, model, user, **options):
		self.model = model
		self.user = user
		self.options = options
		self.earnings_report = EaningsReport("Credito", user=self.user)
		self._caches = {}

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
			try:
				bonus_earnings = asset.earnings['bonificacoes']
			except KeyError:
				bonus_earnings = asset.earnings['bonificacoes'] = []

			# total de ativos na data ex
			history_data_com = history[bonus.data_com]
			history_asset = history_data_com[bonus.enterprise.code]

			# valor quantidade e valores recebidos de bonificação
			bonus_quantity = history_asset.buy.quantity * (bonus.proportion / 100.0)

			# adição dos novos ativos
			bonus_base_quantity = int(bonus_quantity)
			bonus_base_value = bonus_base_quantity * bonus.base_value

			try:
				bonus_frac_quantity = bonus_quantity % bonus_base_quantity
				bonus_frac_value = bonus_frac_quantity * bonus.base_value
			except ZeroDivisionError:
				# bonus_base_quantity == 0, bonus_quantity < 1
				bonus_frac_quantity = bonus_quantity
				bonus_frac_value = bonus_frac_quantity * bonus.base_value

			bonus_earnings.append({
				'spec': bonus,
				'asset': history_asset,
				# o correto é a parte fracionária ser vendidada
				'fractional': Earning("Bônus fracionado",
				                      quantity=bonus_frac_quantity,
				                      value=bonus_frac_value),
				'base': Earning("Bônus principal",
				                quantity=bonus_base_quantity,
				                value=bonus_base_value),
			})
			asset.buy.quantity += bonus_quantity
			asset.buy.total += bonus_base_value

			# novo preço médio já com a bonifição
			asset.buy.avg_price = asset.buy.total / asset.buy.quantity

	def apply_events(self, date, assets, **options):
		"""Eventos de desdobramento/grupamento"""
		qs_options = {}
		enterprise = options.get('enterprise')
		related_fields = []
		if enterprise:
			qs_options['enterprise'] = enterprise
			related_fields.append('enterprise')
		event_model = self.event_model
		queryset = event_model.objects.filter(date_com=date, user=self.user, **qs_options)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		for instance in queryset:
			try:
				asset = assets[instance.enterprise.code]
			except KeyError:
				continue
			if asset.buy.quantity == 0:
				continue
			# ignora os registros que já foram contabilizados na posição
			elif asset.position and instance.date_com < asset.position.date:
				continue
			elif instance.event == event_model.SPLIT:  # Desdobramento
				quantity = asset.buy.quantity / instance.factor_from  # correção
				asset.buy.quantity = quantity * instance.factor_to
				asset.buy.avg_price = asset.buy.total / asset.buy.quantity

			elif instance.event == event_model.INPLIT:  # Grupamento
				quantity = asset.buy.quantity / instance.factor_from  # correção
				asset.buy.quantity = quantity * instance.factor_to
				asset.buy.avg_price = asset.buy.total / asset.buy.quantity

	def consolidate(self, instance, asset: Asset):
		kind = instance.kind.lower()

		if kind == self.buy:
			# valores de compras
			asset.buy.tax += instance.tax
			asset.buy.quantity += instance.quantity
			asset.buy.total += ((instance.quantity * instance.price) + instance.tax)
			asset.buy.avg_price = asset.buy.total / asset.buy.quantity
		elif kind == self.sell:
			# valores de venda
			asset.sell.tax += instance.tax
			asset.sell.quantity += instance.quantity
			asset.sell.total += ((instance.quantity * instance.price) - instance.tax)
			asset.sell.avg_price = asset.sell.total / asset.sell.quantity

			# ganho de capital de todas a vendas
			asset.sell.capital += (instance.quantity * (asset.sell.avg_price - asset.buy.avg_price))

			# novos valores para compra
			asset.buy.quantity -= instance.quantity
			asset.buy.total = asset.buy.quantity * asset.buy.avg_price
		return asset

	def get_earning_kind(self, instance):
		try:
			kind = self._caches[instance.kind]
		except KeyError:
			kind = slugify(instance.kind).replace('-', "_")
			self._caches[instance.kind] = kind
		return kind

	def get_earnings_queryset(self, date, **options):
		qs_options = dict(
			user=self.user,
			date=date
		)
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution.name
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['code'] = enterprise.code
		queryset = self.earnings_model.objects.filter(**qs_options)
		return queryset

	def calc_earnings(self, instance, asset: Asset):
		flow = instance.flow.lower()
		kind = self.get_earning_kind(instance)
		earning_flow_key = f"{kind}_{flow}"
		try:
			earning = asset.earnings[earning_flow_key]
		except KeyError:
			earning = Earning(instance.kind, flow=flow)
			asset.earnings[earning_flow_key] = earning

		earning.items.append(instance)
		earning.quantity += instance.quantity
		earning.value += instance.total

		# ignora os registros que já foram contabilizados na posição
		if asset.position and instance.date < asset.position.date:
			return
		elif flow == self.credit:
			if kind == self.LEILAO_DE_FRACAO:
				asset.sell.total += instance.total
				# ganho de capital de todas a vendas
				asset.sell.capital += instance.total
			elif kind == self.BONIFICAO_EM_ATIVOS:
				asset.buy.quantity += instance.quantity
				asset.buy.total += instance.total
				asset.buy.avg_price = asset.buy.quantity * asset.buy.avg_price
		elif flow == self.debt:
			if kind == self.FRACAO_EM_ATIVOS:
				# redução das frações vendidas
				asset.buy.quantity -= instance.quantity
				asset.buy.total = asset.buy.quantity * asset.buy.avg_price

	def apply_earnings(self, date, assets, **options):
		queryset = self.get_earnings_queryset(date, **options)
		for instance in queryset:
			try:
				self.calc_earnings(instance, assets[instance.code])
			except KeyError:
				continue

	def get_position_queryset(self, date, **options):
		"""Mota e retorna a queryset de posição"""
		qs_options = {}
		related_fields = []
		institution = options.get('institution')
		if institution:
			qs_options['institution'] = institution
			related_fields.append('institution')
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['enterprise'] = enterprise
			related_fields.append('enterprise')
		startdate = options.get('startdate')
		if startdate is None:
			startdate = date - datetime.timedelta(days=365)
		qs_options.setdefault(options.get('startdate_lookup', 'date__gte'), startdate)
		qs_options.setdefault(options.get('enddate_lookup', 'date__lte'), date)
		queryset = self.position_model.objects.filter(
			user=self.user,
			**qs_options
		)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		return queryset.order_by('date')

	def get_assets_position(self, date=None, queryset=None, **options):
		"""Retorna dados de posição para caculo do período"""
		assets = {}
		if queryset is None:
			queryset = self.get_position_queryset(date, **options)
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
		position_queryset = self.get_position_queryset(date=dtend, startdate=dtstart, **options)
		assets_queryset = self.get_queryset(**qs_options)

		for date in range_dates(dtstart, dtend):  # calcula um dia por vez
			assets_position = self.get_assets_position(queryset=position_queryset.filter(date=date))
			if assets_position:
				assets.update(assets_position)
			queryset = assets_queryset.filter(date=date)
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
			self.apply_earnings(date, assets, **options)
			self.apply_events(date, assets, **options)
			# self.add_bonus(date, history, assets, **options)
		results = []
		for code in assets:
			asset = assets[code]
			asset.enterprise = asset.enterprise or self.get_enterprise(code)
			results.append({
				'code': code,
				'institution': institution,
				'enterprise': asset.enterprise,
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
