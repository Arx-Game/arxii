"""Every inline that can refuse a doubled row says which row and why (#4380).

Django's stock inline formset answers a ``(parent, field)`` uniqueness clash
with "Please correct the duplicate data for <field>." ``OneRowPerFormSet``
replaces that line with one naming the field and its value. This test walks
the admin registry so a new inline on a model with such a rule cannot ship on
the stock formset by forgetting to name ours.
"""

from django.contrib import admin
from django.forms.models import _get_foreign_key
from django.test import SimpleTestCase

from world.admin_utils import OneRowPerFormSet


def _one_row_per_value_rules(inline, parent_model) -> list[tuple[str, ...]]:
    fk = _get_foreign_key(parent_model, inline.model, fk_name=inline.fk_name)
    opts = inline.model._meta
    rules = [tuple(constraint.fields) for constraint in opts.total_unique_constraints]
    rules.extend(tuple(names) for names in opts.unique_together)
    return [rule for rule in rules if fk.name in rule and len(rule) > 1]


class InlineDuplicateRowMessageTests(SimpleTestCase):
    def test_every_constrained_first_party_inline_names_the_shared_formset(self) -> None:
        stock = []
        covered = 0
        for parent_model, model_admin in admin.site._registry.items():
            for inline in model_admin.inlines:
                if inline.__module__.startswith("evennia."):
                    continue  # dependency code stays as shipped
                if not _one_row_per_value_rules(inline, parent_model):
                    continue
                covered += 1
                if not issubclass(inline.formset, OneRowPerFormSet):
                    stock.append(f"{inline.__module__}.{inline.__name__}")
        self.assertEqual(
            stock,
            [],
            "These inlines refuse a doubled row with Django's bare 'duplicate data' line; "
            "set `formset = OneRowPerFormSet` (or a subclass) on each.",
        )
        self.assertGreater(covered, 100, "the registry walk found almost nothing; is it broken")
