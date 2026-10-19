"""A SET_NULL foreign key must not be one a CheckConstraint requires non-null (#4461).

``ResonanceGrant.outfit_item_facet`` was ``on_delete=SET_NULL`` while
``res_grant_outfit_trickle_shape`` required it on every OUTFIT_TRICKLE grant. Deleting
the target made Postgres reject the SET_NULL with an IntegrityError, so the target
could never be deleted once a grant pointed at it. Nothing failed until a player
sacrificed an item that had fed its wearer resonance. A test cannot see this by
creating rows; the contradiction is between two declarations, so this walks them.
"""

from __future__ import annotations

from django.apps import apps
from django.db import models
from django.db.models import CheckConstraint, Q
from django.test import SimpleTestCase


def _required_non_null_fields(node: Q) -> set[str]:
    """Field names a Q tree asserts non-null somewhere (``field__isnull=False``).

    A disjunction counts: ``(A and f is set) or (B and f is null)`` still rejects a
    row in branch A whose ``f`` becomes null.
    """
    found: set[str] = set()
    for child in node.children:
        if isinstance(child, Q):
            found |= _required_non_null_fields(child)
            continue
        lookup, value = child
        if lookup.endswith("__isnull") and value is False:
            found.add(lookup.removesuffix("__isnull").split("__")[0])
    return found


#: Pairs that already had the defect when this guard landed (#4461). Each is the same
#: contradiction: deleting the target asks the database to null a column its check
#: constraint requires. They need a per-case ruling (PROTECT, a soft-delete, or a
#: constraint that allows the null), so they are listed, not fixed here. The set only
#: shrinks: fixing one fails the second test until its line is removed.
KNOWN_VIOLATIONS: frozenset[str] = frozenset(
    {
        "arxii.ConsequenceOutcome.action_interaction",
        "arxii.ConsequenceOutcome.combat_interaction",
        "arxii.ResonanceGrant.source_project",
        "arxii.DramaticSurgeRecord.subject_sheet",
        "arxii.JournalEntry.parent",
        "arxii.MissionSupportDeclaration.pattern",
        "arxii.MissionSupportDeclaration.support_option",
    }
)


def _violations() -> list[str]:
    out: list[str] = []
    for model in apps.get_models():
        if model._meta.proxy or model._meta.abstract:
            continue
        set_null = {
            f.name
            for f in model._meta.concrete_fields
            if isinstance(f, models.ForeignKey) and f.remote_field.on_delete is models.SET_NULL
        }
        if not set_null:
            continue
        for constraint in model._meta.constraints:
            if not isinstance(constraint, CheckConstraint) or constraint.condition is None:
                continue
            out.extend(
                f"{model._meta.label}.{name}"
                for name in sorted(_required_non_null_fields(constraint.condition) & set_null)
            )
    return out


class SetNullAgainstCheckConstraintTests(SimpleTestCase):
    def test_no_new_set_null_foreign_key_is_required_by_a_check_constraint(self) -> None:
        """A SET_NULL FK that a CheckConstraint requires non-null is PROTECT or a soft delete."""
        self.assertEqual(
            sorted(set(_violations()) - KNOWN_VIOLATIONS),
            [],
            "SET_NULL on a column a CheckConstraint requires: deleting the target raises "
            "IntegrityError. Use on_delete=PROTECT and soft-remove the target (#4461).",
        )

    def test_known_violations_list_only_shrinks(self) -> None:
        self.assertEqual(sorted(KNOWN_VIOLATIONS - set(_violations())), [])
