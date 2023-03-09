$(function () {
    var $form = $("form.exform.rended");
    $form.find("#position_locked").click(function () {
        var is_checked = $(this).is(":checked");
        $form.find("button[name='position']").prop("disabled", !is_checked);
    });
    $form.submit(function (evt) {
        var $fm = $(this),
            $btn = $(evt.originalEvent.submitter);
        $fm.data('$submitter', $btn);
        $btn.prop("disabled", true);
    });
    $(document).keyup(function (e) {
        if (e.keyCode === 27 && $form.data('$submitter')) {
            $form.data('$submitter').prop("disabled", false);
            $form.data('$submitter', null);
        }
    });
    $('.irpfreport [data-toggle="popover"]').popover({
        animation: false
    });
})