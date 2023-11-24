(function () {
    /* Plugin jquery que copia do conteúdo para o clipboard */
    $.fn.copyClipboard = function () {
        var $el = this,
            text;
        try {
            $el.select();
            $el.setSelectionRange(0, 99999); // For mobile devices
            text = $el.val()
        } catch (e) {
            text = $el.data("content")
        }
        // Copy the text inside the text field
        if (text) {
            text = text.replace(/\s+/g, ' ').trim();
            try {
                navigator.clipboard.writeText(text);
            } catch (e) {
                var $input = $('<textarea>').css({
                    position: "absolute",
                    left: "-9999px"
                }).appendTo($('body'));
                $input.val(text).select();
                document.execCommand('copy');
                $input.remove();
            }
        }
    }
})();