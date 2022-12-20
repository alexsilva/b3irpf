import collections

from irpf.models import Enterprise


class NegotiationReport:
	enterprise_model = Enterprise

	def __init__(self, model, **options):
		self.model = model
		self.options = options

	def consolidate(self, code, items):
		data = collections.defaultdict(dict)
		try:
			enterprise = self.enterprise_model.objects.get(code=code)
		except self.enterprise_model.DoesNotExist:
			enterprise = None
		for item in items:
			kind = item.kind.lower()
			if kind == "compra":
				quantity = data[kind].setdefault('quantity', 0)
				total = data[kind].setdefault('total', 0.0)

				quantity += item.quantity
				total += item.quantity * item.price
				avg_price = total / float(quantity)

				data[kind]['quantity'] = quantity
				data[kind]['total'] = total
				data[kind]['avg_price'] = avg_price
		results = {
			'code': code,
			'enterprise': enterprise,
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
