import calendar
import datetime
from decimal import Decimal
from irpf.models import Asset, Earnings, Bonus, Position, AssetEvent, Subscription, BonusInfo, SubscriptionInfo
from irpf.report.base import BaseReport
from irpf.report.utils import Event, Assets, Buy, MoneyLC
from irpf.utils import range_dates


class EmptyError(KeyError):
	...


class NegotiationReport(BaseReport):
	asset_model = Asset
	earnings_model = Earnings
	position_model = Position
	event_model = AssetEvent
	subscription_model = Subscription
	subscription_info_model = SubscriptionInfo
	bonus_model = Bonus
	bonus_info_model = BonusInfo

	def __init__(self, model, user, **options):
		super().__init__(model, user, **options)
		self.date_start = self.date_end = None
		self._caches = {}

	def get_asset(self, code):
		"""A empresa"""
		try:
			asset = self.asset_model.objects.get(code__iexact=code)
		except self.asset_model.DoesNotExist:
			asset = None
		return asset

	def get_queryset(self, *args, **kwargs):
		return self.model.objects.filter(*args, **kwargs)

	def get_common_qs_options(self, **options) -> dict:
		qs_options = {'user': self.user}
		if assetft := options.get('asset'):
			qs_options['asset'] = assetft
		if categories := options['categories']:
			qs_options['asset__category__in'] = categories
		return qs_options

	def get_cache(self, key: str):
		try:
			return self._caches[key]
		except KeyError as exc:
			raise EmptyError(exc)

	def remove_cache(self, key: str):
		return self._caches.pop(key, None)

	def set_cache(self, key: str, value):
		self._caches[key] = value
		return value

	def reset_cache(self):
		"""Limpa valores de cache"""
		self._caches.clear()

	@staticmethod
	def _update_defaults(instance, defaults):
		"""Atualiza, se necessário a instância com valores padrão"""
		updated = False
		for key in defaults:
			value = defaults[key]
			if not updated and getattr(instance, key) != value:
				updated = True
			setattr(instance, key, value)
		if updated:
			instance.save(update_fields=list(defaults))
		return updated

	def get_bonus_registry_by_date(self, **options) -> dict:
		"""Agrupamento de todos os registros de bônus no intervalo pela data"""
		try:
			return self.get_cache('bonus_registry_by_date')
		except EmptyError:
			by_date = self.set_cache('bonus_registry_by_date', {})
		qs_options = self.get_common_qs_options(**options)
		qs_options['date_com__gte'] = self.date_start
		qs_options['date_com__lte'] = self.date_end
		for instance in self.bonus_model.objects.filter(**qs_options):
			by_date.setdefault(instance.date_com, []).append(instance)
		return by_date

	def get_bonus_by_date(self, **options) -> dict:
		"""Cache dos bônus registrados para a data de incorporação"""
		try:
			return self.get_cache('bonus_by_date')
		except EmptyError:
			by_date = self.set_cache('bonus_by_date', {})
		qs_options = self.get_common_qs_options(**options)
		qs_options['bonus__date__gte'] = self.date_start
		qs_options['bonus__date__lte'] = self.date_end
		if assetft := qs_options.pop('asset', None):
			qs_options['bonus__asset'] = assetft
		if categories := qs_options.pop('asset__category__in', None):
			qs_options['bonus__asset__category__in'] = categories
		queryset = self.bonus_info_model.objects.filter(**qs_options)
		queryset = queryset.select_related("bonus")
		for instance in queryset:
			by_date.setdefault(instance.bonus.date, []).append(instance)
		return by_date

	def add_bonus(self, date, assets, **options):
		"""Adiciona ações bonificadas na data considerando o histórico"""
		bonus_by_date = self.get_bonus_by_date(**options)
		for bonus_info in bonus_by_date.get(date, ()):
			bonus = bonus_info.bonus
			ticker = bonus.asset.code
			try:
				asset = assets[ticker]
			except KeyError:
				continue
			# ignora os registros que já foram contabilizados na posição
			if asset.is_position_interval(bonus.date):
				continue

			# rebalanceando a carteira
			if active := bonus_info.quantity > 0:
				asset.buy.quantity += bonus_info.quantity
				asset.buy.total += bonus_info.total

			try:
				events = asset.events['bonus']
			except KeyError:
				events = asset.events['bonus'] = []

			_events = []
			for event in events:
				if event['bonus_info'] == bonus_info:
					event['active'] = active
					_events.append(event)
					break

			# um evento proveniente do registro já existe
			if not _events:
				event = Event("Valor da bonificação",
				              quantity=bonus_info.quantity,
				              value=bonus_info.total)
				events.append({
					'instance': bonus,
					'active': active,
					'bonus_info': bonus_info,
					'event': event
				})

	def registry_bonus(self, date, assets, **options):
		"""Adiciona ações bonificadas na data considerando o histórico"""
		bonus_by_date = self.get_bonus_registry_by_date(**options)
		for bonus in bonus_by_date.get(date, ()):
			ticker = bonus.asset.code
			try:
				asset = assets[ticker]
			except KeyError:
				continue
			# ignora os registros que já foram contabilizados na posição
			if asset.is_position_interval(bonus.date):
				continue
			try:
				events = asset.events['bonus']
			except KeyError:
				events = asset.events['bonus'] = []

			# valor quantidade e valores recebidos de bonificação
			quantity = asset.buy.quantity * (bonus.proportion / 100)
			bonus_quantity = int(quantity)
			bonus_value = bonus_quantity * bonus.base_value
			defaults = {
				'from_quantity': asset.buy.quantity,
				'from_total': asset.buy.total,
				'quantity': bonus_quantity,
				'total': bonus_value,
				'user': self.user
			}
			bonus_info, created = self.bonus_info_model.objects.get_or_create(
				bonus=bonus,
				defaults=defaults
			)
			if not created:
				# atualiza os dados sempre que necessário
				self._update_defaults(bonus_info, defaults)

			event = Event("Valor da bonificação",
			              quantity=quantity,
			              value=bonus_value)
			events.append({
				'instance': bonus,
				'bonus_info': bonus_info,
				'active': False,
				'event': event
			})

	def get_subscription_group_by_date(self, **options) -> dict:
		"""Agrupamento de todos os registros de subscrição pela 'data com'"""
		try:
			return self.get_cache('subscription_by_date')
		except EmptyError:
			by_date = self.set_cache('subscription_by_date', {})
		qs_options = self.get_common_qs_options(**options)
		qs_options['date_com__gte'] = self.date_start
		qs_options['date_com__lte'] = self.date_end
		for instance in self.subscription_model.objects.filter(**qs_options):
			by_date.setdefault(instance.date_com, []).append(instance)
		return by_date

	def add_subscription(self, date, assets, **options):
		"""Adiciona ativos da subscrição na data da incorporação (composição do preço médio)"""
		qs_options = self.get_common_qs_options(**options)
		qs_options['subscription__date'] = date
		if assetft := qs_options.pop('asset', None):
			qs_options['subscription__asset'] = assetft
		if categories := qs_options.pop('asset__category__in', None):
			qs_options['subscription__asset__category__in'] = categories
		queryset = self.subscription_info_model.objects.filter(**qs_options)
		queryset = queryset.select_related("subscription")
		for subscription_info in queryset:
			subscription = subscription_info.subscription
			ticker = subscription.asset.code
			try:
				asset = assets[ticker]
			except KeyError:
				continue
			# ignora os registros que já foram contabilizados na posição
			if asset.is_position_interval(subscription.date):
				continue

			# rebalanceando a carteira
			if active := subscription_info.quantity > 0:
				asset.buy.quantity += subscription_info.quantity
				asset.buy.total += subscription_info.total

			try:
				events = asset.events['subscription']
			except KeyError:
				events = asset.events['subscription'] = []

			_events = []
			for event in events:
				if event['subscription_info'] == subscription_info:
					event['active'] = active
					_events.append(event)
					break

			# um evento proveniente do registro já existe
			if not _events:
				event = Event("Valor da subscrição",
				              quantity=subscription_info.quantity,
				              value=subscription_info.total)
				events.append({
					'instance': subscription,
					'subscription_info': subscription_info,
					'active': active,
					'event': event
				})

	def registry_subscription(self, date, assets, **options):
		"""Registra subscrições na 'data com'"""
		get_subscription_group_by_date = self.get_subscription_group_by_date(**options)
		for subscription in get_subscription_group_by_date.get(date, ()):
			ticker = subscription.asset.code
			try:
				asset = assets[ticker]
			except KeyError:
				continue
			# ignora os registros que já foram contabilizados na posição
			if asset.is_position_interval(subscription.date):
				continue

			# valor quantidade e valores recebidos de bonificação
			quantity = asset.buy.quantity * (subscription.proportion / 100)
			quantity_proportional = int(quantity)
			subscription_quantity = subscription.quantity or quantity_proportional
			# o preço médio considera as taxas aplicadas.
			subscription_total = subscription_quantity * subscription.price
			defaults = {
				'from_quantity': asset.buy.quantity,
				'from_total': asset.buy.total,
				'quantity_proportional': quantity_proportional,
				'quantity': subscription_quantity,
				'total': subscription_total,
				'user': self.user
			}
			subscription_info, created = self.subscription_info_model.objects.get_or_create(
				subscription=subscription,
				defaults=defaults
			)
			if not created:
				# atualiza os dados sempre que necessário
				self._update_defaults(subscription_info, defaults)
			if subscription_quantity > 0:
				try:
					events = asset.events['subscription']
				except KeyError:
					events = asset.events['subscription'] = []

				event = Event("Valor da subscrição",
				              quantity=subscription_quantity,
				              value=subscription_total)
				events.append({
					'subscription_info': subscription_info,
					'instance': subscription,
					'active': False,
					'event': event
				})

	def get_events_group_by_date(self, **options) -> dict:
		"""Agrupamento de todos os registros de eventos no intervalo pela data"""
		try:
			return self.get_cache('events_by_date')
		except EmptyError:
			by_date = self.set_cache('events_by_date', {})
		qs_options = self.get_common_qs_options(**options)
		qs_options['date_com__gte'] = self.date_start
		qs_options['date_com__lte'] = self.date_end
		related_fields = []
		if (field_name := 'asset') in qs_options:
			related_fields.append(field_name)
		queryset = self.event_model.objects.filter(**qs_options)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		for instance in queryset:
			by_date.setdefault(instance.date, []).append(instance)
		return by_date

	def apply_events(self, date, assets, **options):
		"""Eventos de desdobramento/grupamento"""
		events_group_by_date = self.get_events_group_by_date(**options)
		for instance in events_group_by_date.get(date, ()):
			try:
				asset = assets[instance.asset.code]
			except KeyError:
				continue
			# posição na data
			if asset.buy.quantity == 0:
				continue
			# ignora os registros que já foram contabilizados na posição
			elif asset.is_position_interval(instance.date_com):
				continue
			elif instance.event == self.event_model.SPLIT:  # Desdobramento
				quantity = asset.buy.quantity / instance.factor_from  # correção
				fraction, quantity = quantity % 1, Decimal(int(quantity))
				# nova quantidade altera o preço médio
				asset.buy.quantity = quantity * instance.factor_to
				# reduz a fração valor da fração com o novo preço médio
				asset.buy.total -= fraction * asset.buy.avg_price

			elif instance.event == self.event_model.INPLIT:  # Grupamento
				quantity = asset.buy.quantity / instance.factor_from
				fraction, quantity = quantity % 1, Decimal(int(quantity))
				# nova quantidade altera o preço médio
				asset.buy.quantity = quantity * instance.factor_to  # correção
				# reduz a fração valor da fração com o novo preço médio
				asset.buy.total -= fraction * asset.buy.avg_price

	def consolidate(self, instance, asset: Assets):
		if instance.is_buy:
			# valores de compras
			asset.buy.tax += instance.tax
			asset.buy.quantity += instance.quantity
			asset.buy.total += ((instance.quantity * instance.price) + instance.tax)
		elif instance.is_sell:
			# valores de vendas
			sell_total = instance.quantity * instance.price

			asset.sell.tax += instance.tax
			asset.sell.quantity += instance.quantity
			asset.sell.total += sell_total

			# preço médio de venda
			sell_avg_price = (sell_total - instance.tax) / instance.quantity

			# preço médio de compras
			buy_avg_price = asset.buy.avg_price
			# preço médio de taxas das compras
			buy_tax_avg_price = asset.buy.avg_tax

			# ganho de capital de todas a vendas
			capital = instance.quantity * (sell_avg_price - buy_avg_price)

			# registra lucros e prejuízos
			if capital > MoneyLC(0):
				asset.sell.profits += capital
			else:
				asset.sell.losses += capital

			# ajustando compras
			asset.buy.quantity -= int(instance.quantity)
			asset.buy.tax = asset.buy.quantity * buy_tax_avg_price
			asset.buy.total = asset.buy.quantity * buy_avg_price
		return asset

	def get_earnings_group_by_date(self, **options):
		try:
			return self.get_cache('earnings_by_date')
		except EmptyError:
			by_date = self.set_cache('earnings_by_date', {})
		qs_options = self.get_common_qs_options(**options)
		qs_options['date__gte'] = self.date_start
		qs_options['date__lte'] = self.date_end
		if institution := options.get('institution'):
			qs_options['institution'] = institution.name
		if assetft := qs_options.pop('asset', None):
			qs_options['code__iexact'] = assetft.code
		queryset = self.earnings_model.objects.filter(**qs_options)
		for instance in queryset:
			by_date.setdefault(instance.date, []).append(instance)
		return by_date

	def calc_earnings(self, instance: Earnings, asset: Assets):
		kind_slug = instance.kind_slug
		obj = getattr(asset, "credit" if instance.is_credit else "debit")
		try:
			event = obj[kind_slug]
		except KeyError:
			obj[kind_slug] = event = Event(instance.kind)

		event.items.append(instance)
		event.quantity += instance.quantity
		event.value += instance.total

		# ignora os registros que já foram contabilizados na posição
		if asset.is_position_interval(instance.date):
			return
		elif instance.is_credit:
			if kind_slug == instance.LEILAO_DE_FRACAO:
				# as frações influenciam no valor de venda para cálculo do imposto (se for o caso 20mil+)
				asset.sell.fraction.total += instance.total
				asset.sell.fraction.quantity += instance.quantity
			elif kind_slug == instance.BONIFICAO_EM_ATIVOS:
				# calculada por registro manual
				# asset.buy.quantity += instance.quantity
				# asset.buy.total += instance.total
				...
		elif instance.is_debit:
			if kind_slug == instance.FRACAO_EM_ATIVOS:
				# debito do frações
				...

	def apply_earnings(self, date, assets, **options):
		earnings_group_by_date = self.get_earnings_group_by_date(**options)
		for instance in earnings_group_by_date.get(date, ()):
			try:
				self.calc_earnings(instance, assets[instance.code])
			except KeyError:
				continue

	def get_position_queryset(self, date: datetime.date, **options):
		"""Monta e retorna a queryset de posição"""
		related_fields = []
		qs_options = self.get_common_qs_options(**options)
		if consolidation := options['consolidation']:
			qs_options['consolidation'] = consolidation
		if institution := options.get('institution'):
			qs_options['institution'] = institution
			related_fields.append('institution')
		if (field_name := 'asset') in qs_options:
			related_fields.append(field_name)
		# a data de posição é sempre o último dia do mês ou ano.
		if consolidation == self.position_model.CONSOLIDATION_YEARLY:
			qs_options['date'] = datetime.date.max.replace(year=date.year - 1)
		elif consolidation == self.position_model.CONSOLIDATION_MONTHLY:
			if date.month - 1 > 0:
				max_day = calendar.monthrange(date.year, date.month - 1)[1]
				qs_options['date'] = datetime.date(date.year, date.month - 1, max_day)
			else:
				# começo de ano sempre pega o compilado anual
				qs_options['consolidation'] = self.position_model.CONSOLIDATION_YEARLY
				qs_options['date'] = datetime.date.max.replace(year=date.year - 1)
		else:
			qs_options['date'] = date
		queryset = self.position_model.objects.filter(**qs_options)
		queryset = queryset.exclude(quantity=0)
		if related_fields:
			queryset = queryset.select_related(*related_fields)
		return queryset.order_by('date')

	def get_assets_position(self, date, **options) -> dict:
		"""Retorna dados de posição para caculo do período"""
		assets = {}
		queryset = self.get_position_queryset(date, **options)
		for position in queryset:
			ticker = position.asset.code
			asset = Assets(
				ticker=ticker,
				institution=position.institution,
				instance=position.asset,
				position=position,
				buy=Buy(
					quantity=position.quantity,
					total=position.total,
					tax=position.tax
				))
			assets[ticker] = asset
		return assets

	def report(self, date_start: datetime.date, date_end: datetime.date, **options):
		options.setdefault('consolidation', self.position_model.CONSOLIDATION_YEARLY)
		options.setdefault('categories', ())
		self.date_start, self.date_end = date_start, date_end
		qs_options = self.get_common_qs_options(**options)
		qs_options['date__gte'] = date_start
		qs_options['date__lte'] = date_end
		if assetft := qs_options.pop('asset', None):  # Permite filtrar por empresa (ativo)
			qs_options['code__iexact'] = assetft.code
		if institution := options.get('institution'):
			qs_options['institution'] = institution.name
		# cache
		assets = self.get_assets_position(date=date_start, **options)
		assets_queryset = self.get_queryset(**qs_options)

		for date in range_dates(date_start, date_end):  # calcula um dia por vez
			# inclusão de bônus considera a data da incorporação
			self.add_bonus(date, assets, **options)
			# inclusão de subscrições na data de incorporação
			self.add_subscription(date, assets, **options)

			queryset = assets_queryset.filter(date=date)
			for instance in queryset:
				# cálculo de compra e venda
				ticker = instance.code
				try:
					asset = assets[ticker]
				except KeyError:
					asset = Assets(ticker=ticker,
					               institution=institution,
					               instance=(instance.asset or assetft or
					                         self.get_asset(ticker)))
					assets[ticker] = asset
				# ignora os registros que já foram contabilizados na posição
				if asset.is_position_interval(instance.date):
					continue
				asset.items.append(instance)
				self.consolidate(instance, asset)

			self.apply_earnings(date, assets, **options)
			self.apply_events(date, assets, **options)
			# cria um registro de bônus para os ativos do dia
			self.registry_bonus(date, assets, **options)
			# cria um registro de subscrição para os ativos do dia
			self.registry_subscription(date, assets, **options)
		results = []
		for code in assets:
			asset = assets[code]
			results.append({
				'code': code,
				'institution': institution,
				'instance': asset.instance,
				'asset': asset
			})

		results = sorted(results, key=self.results_sorted)

		# reset cache
		self.reset_cache()
		return results
