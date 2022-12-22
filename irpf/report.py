import collections

from django.utils.text import slugify

from irpf.models import Enterprise, Earnings


class EaningsReport:
	earnings_models = Earnings

	def __init__(self, flow):
		self.flow = flow

	def report(self, code, institution):
		earnings = collections.defaultdict(dict)
		try:
			qs = self.earnings_models.objects.filter(
				flow__iexact=self.flow,
				institution=institution,
				code__iexact=code)

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

	def __init__(self, model, **options):
		self.model = model
		self.options = options
		self.earnings_report = EaningsReport("Credito")

	def consolidate(self, code, items):
		institution = items[0].institution
		earnings = self.earnings_report.report(code, institution)
		data = collections.defaultdict(dict)
		try:
			enterprise = self.enterprise_model.objects.get(code__iexact=code)
		except self.enterprise_model.DoesNotExist:
			enterprise = None
		buy, sale = "compra", "venda"
		for item in items:
			kind = item.kind.lower()

			quantity = data[kind].setdefault('quantity', 0)
			quantity_av = data[kind].setdefault('quantity_av', 0)
			total = data[kind].setdefault('total', 0.0)

			if kind == buy:
				quantity += item.quantity
				quantity_av += item.quantity
				total += (item.quantity * item.price)
				avg_price = total / float(quantity)

				data[kind]['quantity'] = quantity
				data[kind]['avg_price'] = avg_price
				data[kind]['total'] = total

				data[kind]['quantity_av'] = quantity_av
				data[kind]['avg_price_av'] = avg_price
				data[buy]['total_av'] = quantity_av * avg_price
			elif kind == sale:
				quantity += item.quantity
				total += (item.quantity * item.price)
				avg_price = total / float(quantity)

				# valores de venda
				data[kind]['total'] = total
				data[kind]['quantity'] = quantity
				data[kind]['avg_price'] = avg_price

				# valores de compra
				buy_quantity = data[buy]['quantity']
				buy_quantity_av = data[buy]['quantity_av']
				buy_avg_price = data[buy]['avg_price']

				data[kind]['capital'] = quantity * (avg_price - buy_avg_price)

				# removendo as unidades vendidas
				buy_quantity -= item.quantity
				buy_quantity_av -= item.quantity

				buy_total_av = buy_quantity_av * buy_avg_price

				# novos valores para compra
				data[buy]['total_av'] = buy_total_av
				data[buy]['quantity_av'] = buy_quantity_av
				data[buy]['avg_price_av'] = buy_avg_price

		results = {
			'code': code,
			'institution': institution,
			'enterprise': enterprise,
			'earnings': earnings,
			'results': data
		}
		return results

	def report(self):
		groups = collections.defaultdict(list)
		start = self.options['start']
		end = self.options['end']
		for instace in self.model.objects.filter(date__gte=start,
		                                         date__lte=end):
			groups[instace.code].append(instace)
		results = []
		for code in groups:
			results.append(
				self.consolidate(code, groups[code])
			)
		return results
