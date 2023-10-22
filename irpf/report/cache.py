class EmptyCacheError(KeyError):
	...


class Cache:
	"""Sistema simples de cache em memória"""

	def __init__(self):
		self._cache = {}

	def get(self, key: str, *args):
		try:
			return self._cache[key]
		except KeyError as exc:
			if not args:
				raise EmptyCacheError(exc)
			return args[0]

	def remove(self, key: str):
		return self._cache.pop(key, None)

	def set(self, key: str, value):
		self._cache[key] = value
		return value

	def clear(self):
		self._cache.clear()
