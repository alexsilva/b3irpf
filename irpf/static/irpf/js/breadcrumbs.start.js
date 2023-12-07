(function () {
    $('#breadcrumb_months > .breadcrumb').asBreadcrumbs({
        namespace: 'breadcrumb',
        toggleIconClass: 'fa fa-caret-down p-2',
        dropdownItemClass: 'dropdown-item',
        hiddenClass: 'd-none',
        dropdownItem: function (classes, label, href) {
            var template = '<li class="{{classes.dropdownItemDisableClass}}">' +
                            '<a class="{{classes.dropdownItemClass}}" href="{{href}}">{{label}}</a>' +
                            '</li>',
                options = {
                    classes: classes,
                    label: label
                };
            options.href = href ? href: "#";
            return $.fn.nunjucks_env.renderString(template, options);
        },
    });
})()