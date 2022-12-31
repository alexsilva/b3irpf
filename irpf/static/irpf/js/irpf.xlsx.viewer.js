$(function () {
    var $el = $("table.xlsx_viewer:not(.full)");
    if ($el.length) {
        $el.addClass("full");
        $el.DataTable({
            data: $el.data("items")
        });
    }
});