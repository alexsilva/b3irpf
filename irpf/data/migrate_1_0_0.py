import sys

from correpy.parsers.brokerage_notes.b3_parser.b3_parser import B3Parser
from correpy.parsers.brokerage_notes.b3_parser.nuinvest import NunInvestParser
from irpf.models import BrokerageNote


def init(migration):
	"""
	* Migração dos dados da nota de corretagem (incluindo ID)
	"""
	brokerage_note_parsers = {
		# NU INVEST CORRETORA DE VALORES S.A.
		'62169875000179': NunInvestParser
	}

	for brokerage_note in BrokerageNote.objects.all():
		try:
			b3parser = brokerage_note_parsers[brokerage_note.institution.cnpj_nums]
		except KeyError:
			b3parser = B3Parser
		try:
			print(f"Extraindo dados da nota '{brokerage_note.note.name}'...")
			parser = b3parser(brokerage_note=brokerage_note.note.read())
			for note in parser.parse_brokerage_note():
				brokerage_note.reference_id = note.reference_id
			print("atualizando...")
			brokerage_note.save()
		except FileNotFoundError as exc:
			print(f"Falha na leitura do arquivo '{brokerage_note.note.name}'", file=sys.stderr)
			raise exc from None
