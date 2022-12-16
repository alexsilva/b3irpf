import os


class SecretKey:
	"""Object that manages the creation and access of django secret keys"""

	def __init__(self, key_path):
		self.key_path = key_path

	def new_secret_key(self):
		"""Creates a new random secret key and saves it to the location key_path"""
		from django.core.management.utils import get_random_secret_key
		secret_key = get_random_secret_key()
		with self.key_path.open('w') as key_file:
			key_file.write(secret_key)
		return secret_key

	def __str__(self):
		return self.value()

	def value(self):
		if os.path.exists(self.key_path):
			with self.key_path.open() as key_file:
				secret_key = key_file.read().strip()
		else:
			secret_key = self.new_secret_key()
		return secret_key
