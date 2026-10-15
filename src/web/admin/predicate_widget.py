"""The admin predicate rule widget (#4361): build a faction rule's test without typing JSON.

Renders the mission studio's builder shape (AND / OR / NOT groups, a leaf picker,
typed parameters) in the admin, fed by the same leaf catalog the studio's
``/api/missions/predicate-leaves/`` endpoint serves (``world.predicates.catalog``). The
browser keeps a hidden textarea holding the tree as JSON; the form field parses it and
the model's ``clean()`` runs ``validate_predicate_tree``, the same validator the API uses.
Without JavaScript the textarea stays usable as plain JSON.
"""

from __future__ import annotations

import json
from typing import Any

from django import forms
from django.utils.html import format_html, json_script

from world.predicates.catalog import leaf_catalog

WIDGET_SCRIPT = "admin/js/predicate_widget.js"


class PredicateRuleWidget(forms.Textarea):
    """A textarea of predicate JSON with the builder drawn over it by ``predicate_widget.js``."""

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        super().__init__(attrs={"rows": 3, "cols": 60, "class": "pred-json", **(attrs or {})})

    @property
    def media(self) -> forms.Media:
        return forms.Media(js=[WIDGET_SCRIPT])

    def format_value(self, value: object) -> str:
        if value in (None, ""):
            return "{}"
        if isinstance(value, str):
            return value
        return json.dumps(value)

    def render(
        self,
        name: str,
        value: object,
        attrs: dict[str, Any] | None = None,
        renderer: object = None,
    ) -> str:
        textarea = super().render(name, value, attrs, renderer)
        element_id = (attrs or {}).get("id") or f"id_{name}"
        catalog_id = f"{element_id}-catalog"
        return format_html(
            '<div class="pred-host" data-target="{}" data-catalog="{}">{}{}</div>',
            element_id,
            catalog_id,
            textarea,
            json_script(leaf_catalog(), catalog_id),
        )


class PredicateRuleField(forms.JSONField):
    """A predicate tree edited with ``PredicateRuleWidget``; blank means "matches everyone"."""

    widget = PredicateRuleWidget

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("required", False)
        kwargs.setdefault(
            "help_text",
            "Same builder and leaf catalog as the mission studio's visibility rule. Empty "
            "matches everyone.",
        )
        super().__init__(**kwargs)

    def clean(self, value: object) -> dict:
        return super().clean(value) or {}
