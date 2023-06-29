$(function () {
    // inicializacao das tabelas de dados
    $("table.xlsx_viewer:not(.full)").each(function () {
        var $el = $(this).addClass("full");
        $el.DataTable({
            data: $el.data("items"),
            language: {
                url: '/static/irpf/datatables-1.13.1/i18n/' + xadmin.language_code + '.json'
            }
        });
    })
});