$(function () {
    $('#breadcrumb_months > .breadcrumb').asBreadcrumbs({
        namespace: 'breadcrumb',
        toggleIconClass: 'fa fa-caret-down p-2',
        dropdownItemClass: 'dropdown-item',
        hiddenClass: 'd-none',
    });
})