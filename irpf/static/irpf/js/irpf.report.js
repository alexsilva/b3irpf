$(function () {
    var $form = $("form.exform.rended"),
        form_submit_handler = function ($form, $submit) {
            var input_hidden_class = $submit.attr("name") + "_submit";
            $form.find("input." + input_hidden_class).remove();
            $submit.each(function () {
                var $el = $(this);
                $("<input/>")
                .addClass(input_hidden_class)
                .attr("type", "hidden")
                .attr("name", $el.attr("name"))
                .attr("value", $el.attr("value"))
                .appendTo($form);
            });
        }

    $form.find("#position_locked").click(function () {
        var is_checked = $(this).is(":checked"),
            $btn = $form.find("button[name='position']");
        $btn.prop("disabled", !is_checked);
        form_submit_handler($form, $btn);
    });
    $form.submit(function (evt) {
        var $fm = $(this),
            $btn = $(evt.originalEvent.submitter);
        $fm.data('$submitter', $btn);
        $btn.prop("disabled", true);
        form_submit_handler($fm, $btn);
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