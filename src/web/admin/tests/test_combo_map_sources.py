"""The combo map's completeness guard (#4891, slice 3 of #4843).

Every model field that points at a condition property, a condition template or a
condition stage is a setter source, a reader source, or excluded with a reason. A new
field on none of the three fails here by name, so a new setter or reader cannot drop
off the map without someone deciding which it is.
"""

from __future__ import annotations

from django.apps import apps
from django.db.models import Model
from django.test import SimpleTestCase

from web.admin.combo_map.sources import EXCLUDED_FIELDS, READER_SOURCES, SETTER_SOURCES
from world.conditions.models import ConditionStage, ConditionTemplate
from world.mechanics.models import Property

_TARGETS = (Property, ConditionTemplate, ConditionStage)


def _pointing_fields() -> set[tuple[type[Model], str]]:
    found: set[tuple[type[Model], str]] = set()
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if field.auto_created or not field.is_relation:
                continue
            if field.related_model in _TARGETS:
                found.add((model, field.name))
    return found


def _listed() -> set[tuple[type[Model], str]]:
    listed = {source.covers or (source.model, source.field) for source in SETTER_SOURCES}
    listed |= {(source.model, source.field) for source in READER_SOURCES}
    listed |= {(entry.model, entry.field) for entry in EXCLUDED_FIELDS}
    return listed


def _name(entry: tuple[type[Model], str]) -> str:
    return f"{entry[0].__name__}.{entry[1]}"


class ComboMapSourcesTest(SimpleTestCase):
    def test_every_field_pointing_at_a_property_condition_or_stage_is_listed(self) -> None:
        missing = sorted(_name(entry) for entry in _pointing_fields() - _listed())
        self.assertEqual(
            missing,
            [],
            "Add each to SETTER_SOURCES, READER_SOURCES or EXCLUDED_FIELDS "
            "in web/admin/combo_map/sources.py",
        )

    def test_every_listed_field_still_exists_and_points_at_one(self) -> None:
        stale = sorted(_name(entry) for entry in _listed() - _pointing_fields())
        self.assertEqual(stale, [])

    def test_no_field_is_both_excluded_and_a_source(self) -> None:
        excluded = {(entry.model, entry.field) for entry in EXCLUDED_FIELDS}
        sources = {s.covers or (s.model, s.field) for s in SETTER_SOURCES}
        sources |= {(s.model, s.field) for s in READER_SOURCES}
        self.assertEqual(sorted(_name(e) for e in sources & excluded), [])

    def test_every_exclusion_gives_a_reason(self) -> None:
        self.assertEqual([_name((e.model, e.field)) for e in EXCLUDED_FIELDS if not e.reason], [])
