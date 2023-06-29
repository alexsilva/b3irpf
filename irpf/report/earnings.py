from django.utils.text import slugify

from irpf.models import Earnings
from irpf.report.utils import Event


class EarningsReport:
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
					earning = earnings[kind] = Event(instance.kind)

				earning.items.append(instance)
				earning.quantity += instance.quantity
				earning.value += instance.total
		except self.earnings_models.DoesNotExist:
			pass
		return earnings
