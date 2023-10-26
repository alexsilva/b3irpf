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
            navigator.clipboard.writeText(text.replace(/\s+/g, ' ').trim());
        }
    }
})();