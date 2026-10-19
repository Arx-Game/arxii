"""Guard: a constraint condition must compare a choices field to a stored value.

A partial unique index or check constraint written as
``Q(holder_type="PERSONA")`` against a field whose stored values are
``"persona"`` never matches a row, so the database enforces nothing and no test
that goes through the service layer notices (#4476: ``VaultAccessEntry`` let a
persona be granted the same vault twice). This walks every ``condition=`` (a ``CheckConstraint``'s
``check=`` included) in the project, and fails on a string literal compared to a field with
``choices`` when that literal is not one of the field's stored values.
"""

from __future__ import annotations

from collections.abc import Iterator

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Q
from django.test import SimpleTestCase

_LOOKUP_SUFFIXES = {"exact", "iexact", "in"}


def _literals(node: Q) -> Iterator[tuple[str, object]]:
    """Yield (lookup path, value) for every leaf of a Q tree."""
    for child in node.children:
        if isinstance(child, Q):
            yield from _literals(child)
        else:
            yield child


def _resolve_field(model: type[models.Model], path: str) -> models.Field | None:
    """Follow a lookup path to its final field; None when it ends in a transform."""
    parts = path.split("__")
    if parts[-1] in _LOOKUP_SUFFIXES and len(parts) > 1:
        parts = parts[:-1]
    current = model
    field = None
    for part in parts:
        try:
            field = current._meta.get_field(part)
        except FieldDoesNotExist:
            return None
        if field.is_relation and field.related_model is not None:
            current = field.related_model
    return field


def _constraint_conditions(model: type[models.Model]) -> Iterator[tuple[str, Q]]:
    for constraint in model._meta.constraints:
        if isinstance(constraint, (models.UniqueConstraint, models.CheckConstraint)) and isinstance(
            constraint.condition, Q
        ):
            yield constraint.name, constraint.condition


def _condition_problems(model: type[models.Model], name: str, condition: Q) -> list[str]:
    problems: list[str] = []
    for path, value in _literals(condition):
        field = _resolve_field(model, path)
        if field is None or not field.choices:
            continue
        stored = {choice[0] for choice in field.flatchoices}
        values = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
        # "" is the blank option on a nullable-or-optional field, not a choice.
        problems.extend(
            f"{model._meta.label}.{name}: {path}={literal!r} is not a stored value "
            f"of the field (stored: {sorted(map(str, stored))})"
            for literal in values
            if isinstance(literal, str) and literal and literal not in stored
        )
    return problems


def _mismatches() -> list[str]:
    return [
        problem
        for model in apps.get_models()
        for name, condition in _constraint_conditions(model)
        for problem in _condition_problems(model, name, condition)
    ]


class ConstraintChoiceLiteralTests(SimpleTestCase):
    def test_constraint_literals_are_stored_choice_values(self) -> None:
        self.assertEqual(_mismatches(), [])

    def test_guard_flags_the_4476_shape(self) -> None:
        """A wrong-case literal on a choices field is reported; the stored one is not."""
        from world.room_features.models import VaultAccessEntry

        bad = _condition_problems(VaultAccessEntry, "x", Q(holder_type="PERSONA"))
        self.assertEqual(len(bad), 1)
        self.assertIn("'PERSONA'", bad[0])
        self.assertEqual(_condition_problems(VaultAccessEntry, "x", Q(holder_type="persona")), [])
        self.assertEqual(
            len(_condition_problems(VaultAccessEntry, "x", Q(holder_type__in=["persona", "ORG"]))),
            1,
        )
