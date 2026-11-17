"""Helpers shared by admin page tests."""

from django import forms


def form_data(response) -> dict[str, str]:
    """What a browser would post back from a rendered change page: every field as shown."""
    context = response.context
    forms_on_page: list[forms.BaseForm] = [context["adminform"].form]
    data: dict[str, str] = {}
    for inline in context["inline_admin_formsets"]:
        formset = inline.formset
        forms_on_page.append(formset.management_form)
        forms_on_page.extend(formset.forms)
    for form in forms_on_page:
        for name in form.fields:
            bound = form[name]
            value = bound.value()
            if value is None or value is False:
                continue
            data[bound.html_name] = value if isinstance(value, list) else str(value)
    return data
