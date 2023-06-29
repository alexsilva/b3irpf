$(function () {
    // inicializacao das tabelas de dados
    $("table.xlsx_viewer:not(.full)").each(function () {
        var $el = $(this).addClass("full");
        $el.DataTable({
            data: $el.data("items"),
            language: {
                url: $el.data("language_url")
            }
        });
    })
});