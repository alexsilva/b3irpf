

$(function () {
    $(".card button.card-expand-md").click(function () {
        var $el = $(this),
            $parent = $el.parents(".card.asset"),
            modal = xadmin.bs_modal({
                modal: {
                    size: "modal-lg"
                }
            }),
            $$parent = $("<div>", {
                'class': "card asset" + $parent.data("ticker")
            });
        $$parent.insertAfter($parent);
        modal.$el().on("hide.bs.modal", function () {
            modal.find(".modal-body")
                .find(".card.asset")
                .detach()
                .insertAfter($$parent);
            $$parent.remove();
            $el.show();
        });
        $el.hide();
        $parent.detach()
            .appendTo(modal.find(".modal-body"));
        modal.appendTo("body");
        modal.show();
    })
})