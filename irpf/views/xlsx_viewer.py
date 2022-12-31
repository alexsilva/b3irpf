import json

import django.forms as django_forms
from openpyxl.reader.excel import load_workbook
import collections
from irpf.views.base import AdminFormView


class XlsxViewerForm(django_forms.Form):
	filestream = django_forms.FileField(label="Arquivo de dados Excel (xlsx)")


class AdminXlsxViewer(AdminFormView):
	"""Visualizador de dados de um arquivo Excel (xlsx)"""

	template_name = "irpf/adminx_report_irpf_viewer.html"
	form_class = XlsxViewerForm

	def process_sheet(self, ws):
		print("SHEET ", ws.title)
		data = collections.OrderedDict()

		rows = ws.iter_rows()

		headers = []
		for cell in next(rows):
			headers.append(cell.value)

		data['title'] = ws.title
		data['headers'] = headers
		items = []

		print(" / ".join(headers))

		for row in rows:
			cells = []
			for index, cell in enumerate(row):
				cells.append(str(cell.value))

			items.append(cells)
			print(" / ".join(cells))

		data['items'] = json.dumps(items)
		return data

	def file_handle(self, file):
		wb = None
		sheets = []
		with file:
			try:
				wb = load_workbook(filename=file, data_only=True)
				for sheet_name in wb.sheetnames:
					sheet_item = self.process_sheet(wb[sheet_name])
					sheets.append(sheet_item)
			finally:
				if wb:
					wb.close()
		return sheets

	def get_media(self):
		media = super().get_media()
		media += django_forms.Media(js=(
			'irpf/datatables-1.13.1/js/jquery.dataTables.js',
			'irpf/datatables-1.13.1/js/dataTables.bootstrap4.js',
			'irpf/js/irpf.xlsx.viewer.js'
		), css={
			'screen': (
				'irpf/datatables-1.13.1/css/jquery.dataTables.css',
				'irpf/datatables-1.13.1/css/dataTables.bootstrap4.css'
			)
		})
		return media

	def get_success_url(self):
		return self.get_admin_url("xlsx_viewer")

	def form_valid(self, form):
		filestream = form.cleaned_data["filestream"]
		sheets = self.file_handle(filestream.file)

		context = self.get_context_data()
		context['sheets'] = sheets

		return self.render_to_response(context)
