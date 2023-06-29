
class BaseReport:
	"""Base report"""
	def __init__(self, model, user, **options):
		self.model = model
		self.user = user
		self.options = options

	def report(self, date_start, date_end, **options):
		raise NotImplementedError
