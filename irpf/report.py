import collections

from django.utils.text import slugify

from irpf.models import Enterprise, Earnings, Bonus
from irpf.utils import range_dates


class EaningsReport:
	earnings_models = Earnings

	def __init__(self, flow, user, **options):
		self.flow = flow
		self.user = user
		self.options = options

	def get_queryset(self, **options):
		return self.earnings_models.objects.filter(**options)

	def report(self, code, institution, start, end=None):
		earnings = collections.defaultdict(dict)
		options = dict(
			flow__iexact=self.flow,
			user=self.user,
			institution=institution,
			date__gte=start,
			code__iexact=code
		)
		if end is not None:
			options['date__lte'] = end
		try:
			qs = self.get_queryset(**options)
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
	bonus_model = Bonus

	buy, sale = "compra", "venda"

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

	def add_bonus(self, date, data):
		queryset = self.bonus_model.objects.filter(date=date, user=self.user)
		for bonus in queryset:
			info = data[bonus.enterprise.code]
			quantity = info[self.buy]['quantity_av']
			total = info[self.buy]['total_av']

			# valor quantidade e valores recebidos de bonificação
			bonus_quantity = int(quantity * (bonus.proportion / 100.0))
			bonus_value = bonus_quantity * bonus.base_value

			quantity += bonus_quantity
			total += bonus_value

			# novo preço médio já com a bonifição
			avg_price = total / float(quantity)

			info[self.buy]['total_av'] = total
			info[self.buy]['avg_price_av'] = avg_price
			info[self.buy]['quantity_av'] = quantity

	def consolidate(self, instance, data):
		kind = instance.kind.lower()

		quantity = data[kind].setdefault('quantity', 0)
		quantity_av = data[kind].setdefault('quantity_av', 0)
		total = data[kind].setdefault('total', 0.0)

		if kind == self.buy:
			quantity += instance.quantity
			quantity_av += instance.quantity
			total += (instance.quantity * instance.price)
			avg_price = total / float(quantity)

			data[kind]['quantity'] = quantity
			data[kind]['avg_price'] = avg_price
			data[kind]['total'] = total

			data[kind]['quantity_av'] = quantity_av
			data[kind]['avg_price_av'] = avg_price
			data[self.buy]['total_av'] = quantity_av * avg_price
		elif kind == self.sale:
			quantity += instance.quantity
			total += (instance.quantity * instance.price)
			avg_price = total / float(quantity)

			# valores de venda
			data[kind]['total'] = total
			data[kind]['quantity'] = quantity
			data[kind]['avg_price'] = avg_price

			# valores de compra
			buy_quantity = data[self.buy]['quantity']
			buy_quantity_av = data[self.buy]['quantity_av']
			buy_avg_price = data[self.buy]['avg_price']

			data[kind]['capital'] = quantity * (avg_price - buy_avg_price)

			# removendo as unidades vendidas
			buy_quantity -= instance.quantity
			buy_quantity_av -= instance.quantity

			buy_total_av = buy_quantity_av * buy_avg_price

			# novos valores para compra
			data[self.buy]['total_av'] = buy_total_av
			data[self.buy]['quantity_av'] = buy_quantity_av
			data[self.buy]['avg_price_av'] = buy_avg_price
		return data

	def report(self, institution, dtstart, dtend):
		options = {
			'institution': institution,
			'user': self.user
		}
		all_data = {}
		for dt in range_dates(dtstart, dtend):
			# calcula um dia por vez
			queryset = self.get_queryset(date=dt, **options)
			for instance in queryset:
				# instance: compra / venda
				try:
					data = all_data[instance.code]
				except KeyError:
					data = collections.defaultdict(dict)
					all_data[instance.code] = data
				self.consolidate(instance, data)
			# bonus
			self.add_bonus(dt, all_data)
		results = []
		for code in all_data:
			enterprise = self.get_enterprise(code)
			earnings = self.earnings_report.report(code, institution, dtstart, dtend)
			results.append({
				'code': code,
				'institution': institution,
				'enterprise': enterprise,
				'earnings': earnings,
				'results': all_data[code]
			})

		def results_sort_category(item):
			return item['enterprise'].category if item['enterprise'] else item['code']

		def results_sort_code(item):
			return item['code']

		results = sorted(results, key=results_sort_code)
		results = sorted(results, key=results_sort_category)
		return results
