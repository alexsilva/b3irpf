$(function () {
    $(".exform #position_locked").click(function () {
        var is_checked = $(this).is(":checked");
        $(".exform button[name='position']").prop("disabled", !is_checked);
    })
    $('.irpfreport [data-toggle="popover"]').popover({
        animation: false
    });
})