import sys
import io
from correpy.parsers.brokerage_notes.b3_parser.b3_parser import B3Parser
from correpy.parsers.brokerage_notes.nuinvest_parser import NuInvestParser
from irpf.models import BrokerageNote


def init(migration):
	"""
	* Migração dos dados da nota de corretagem (incluindo ID)
	"""
	brokerage_note_parsers = {
		# NU INVEST CORRETORA DE VALORES S.A.
		'62169875000179': NuInvestParser
	}

	for brokerage_note in BrokerageNote.objects.all():
		try:
			b3parser = brokerage_note_parsers[brokerage_note.institution.cnpj_nums]
		except KeyError:
			b3parser = B3Parser
		try:
			print(f"Extraindo dados da nota '{brokerage_note.note.name}'...")
			with brokerage_note.note.file as note_file:
				parser = b3parser(brokerage_note=io.BytesIO(note_file.read()))
				has_changed = False
				for note in parser.parse_brokerage_note():
					brokerage_note.reference_id = note.reference_id
					if brokerage_note.reference_id:
						has_changed = True
						break
				if has_changed:
					print("atualizando...")
					brokerage_note.save()
		except FileNotFoundError as exc:
			print(f"Falha na leitura do arquivo '{brokerage_note.note.name}'", file=sys.stderr)
			raise exc from None
