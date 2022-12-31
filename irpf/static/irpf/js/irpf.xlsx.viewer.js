$(function () {
    // inicializacao das tabelas de dados
    var $el = $("table.xlsx_viewer:not(.full)");
    if ($el.length) {
        $el.addClass("full");
        $el.DataTable({
            data: $el.data("items"),
            language: {
                url: '/static/irpf/datatables-1.13.1/i18n/' + xadmin.language_code +'.json'
            }
        });
    }
});