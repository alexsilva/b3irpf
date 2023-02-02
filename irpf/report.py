import collections

from django.utils.text import slugify

from irpf.models import Enterprise, Earnings, Bonus, Position
from irpf.utils import range_dates


class EaningsReport:
	earnings_models = Earnings

	def __init__(self, flow, user, **options):
		self.flow = flow
		self.user = user
		self.options = options

	def get_queryset(self, **options):
		return self.earnings_models.objects.filter(**options)

	def report(self, code, institution, start, end=None, **options):
		earnings = collections.defaultdict(dict)
		qs_options = dict(
			flow__iexact=self.flow,
			user=self.user,
			institution=institution.name,
			date__gte=start,
			code__iexact=code
		)
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['code'] = enterprise.code
		if end is not None:
			qs_options['date__lte'] = end
		try:
			qs = self.get_queryset(**qs_options)
			for instance in qs:
				data = earnings[slugify(instance.kind).replace('-', "_")]
				items = data.setdefault('items', [])
				data.setdefault('title', instance.kind)
				data.setdefault('quantity', 0.0)
				data.setdefault('value', 0.0)

				items.append(instance)
				data['quantity'] += instance.quantity
				data['value'] += instance.total
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

	def get_queryset(self, **options):
		return self.model.objects.filter(**options)

	def add_bonus(self, date, data, **options):
		qs_options = {}
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['enterprise'] = enterprise
		queryset = self.bonus_model.objects.filter(date=date, user=self.user,
		                                           **qs_options)
		for bonus in queryset:
			info = data[bonus.enterprise.code]
			position = info.get('position')
			# ignora os registros que já foram contabilizados na posição
			if position and bonus.date < position.date:
				continue
			quantity = info[self.buy]['quantity']
			total = info[self.buy]['total']

			# valor quantidade e valores recebidos de bonificação
			bonus_quantity = int(quantity * (bonus.proportion / 100.0))
			bonus_value = bonus_quantity * bonus.base_value

			quantity += bonus_quantity
			total += bonus_value

			# novo preço médio já com a bonifição
			avg_price = total / float(quantity)

			info[self.buy]['total'] = total
			info[self.buy]['avg_price'] = avg_price
			info[self.buy]['quantity'] = quantity

	def consolidate(self, instance, data):
		kind = instance.kind.lower()

		quantity = data[kind].setdefault('quantity', 0)
		total = data[kind].setdefault('total', 0.0)

		if kind == self.buy:
			quantity += instance.quantity
			total += (instance.quantity * instance.price)
			avg_price = total / float(quantity)

			data[kind]['quantity'] = quantity
			data[kind]['avg_price'] = avg_price
			data[kind]['total'] = total
		elif kind == self.sell:
			data[kind].setdefault("capital", 0.0)
			quantity += instance.quantity
			total += (instance.quantity * instance.price)
			avg_price = total / float(quantity)

			# valores de venda
			data[kind]['total'] = total
			data[kind]['quantity'] = quantity
			data[kind]['avg_price'] = avg_price

			# valores de compra
			buy_quantity = data[self.buy]['quantity']
			buy_avg_price = data[self.buy]['avg_price']

			# ganho de capital de todas a vendas
			data[kind]['capital'] += (instance.quantity * (instance.price - buy_avg_price))

			# removendo as unidades vendidas
			buy_quantity -= instance.quantity
			buy_total = buy_quantity * buy_avg_price

			# novos valores para compra
			data[self.buy]['total'] = buy_total
			data[self.buy]['quantity'] = buy_quantity
		return data

	def get_position(self, institution, **options):
		"""Retorna dados de posição para caculo do período"""
		data, qs_options = {}, {}
		enterprise = options.get('enterprise')
		if enterprise:
			qs_options['enterprise'] = enterprise
		queryset = self.position_model.objects.filter(
			institution=institution,
			user=self.user,
			**qs_options
		)
		for position in queryset:
			info = collections.defaultdict(dict)
			data[position.enterprise.code] = info

			info[self.buy]['quantity'] = position.quantity
			info[self.buy]['avg_price'] = position.avg_price
			info[self.buy]['total'] = position.total
			info[self.buy]['date'] = position.date

			info['position'] = position
		return data

	def report(self, institution, dtstart, dtend, **options):
		all_data = self.get_position(institution, **options)
		qs_options = {}
		enterprise = options.get('enterprise')
		if enterprise:  # Permite filtrar por empresa (ativo)
			qs_options['code'] = enterprise.code
		for dt in range_dates(dtstart, dtend):  # calcula um dia por vez
			# Adição de bônus antes de inserir compras/vendas na data.
			self.add_bonus(dt, all_data, **options)
			queryset = self.get_queryset(date=dt,
			                             institution=institution.name,
			                             position__isnull=True,
			                             user=self.user,
			                             **qs_options)
			for instance in queryset:
				# instance: compra / venda
				try:
					data = all_data[instance.code]
				except KeyError:
					data = collections.defaultdict(dict)
					all_data[instance.code] = data
				data.setdefault('objs', []).append(instance)
				position = data.get('position')
				# ignora os registros que já foram contabilizados na posição
				if position and instance.date < position.date:
					continue
				self.consolidate(instance, data)
		results = []
		for code in all_data:
			enterprise = self.get_enterprise(code)
			earnings = self.earnings_report.report(code, institution,
			                                       dtstart, dtend,
			                                       **options)
			results.append({
				'code': code,
				'institution': institution,
				'enterprise': enterprise,
				'earnings': earnings,
				'results': all_data[code]
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
