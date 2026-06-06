"""Tests for #737 — spread awareness extension + per-society reputation.

When a spread succeeds, every Society in the spreader's current Realm
enters ``deed.societies_aware``. Per-society reputation deltas fire one-
shot on newly-aware societies only.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import (
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import SceneFactory
from world.societies.constants import RenownRisk
from world.societies.factories import SocietyFactory
from world.societies.models import PhilosophicalArchetype, SocietyReputation
from world.societies.renown import extend_deed_awareness, fire_renown_award


def _make_primary_persona():
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


def _make_archetype(**deltas):
    """PhilosophicalArchetype with named principle deltas."""
    fields = {
        "mercy_delta": 0,
        "method_delta": 0,
        "status_delta": 0,
        "change_delta": 0,
        "allegiance_delta": 0,
        "power_delta": 0,
    }
    fields.update(deltas)
    return PhilosophicalArchetype.objects.create(name=f"Archetype-{id(deltas)}", **fields)


def _make_scene_in_realm(realm):
    """Build a Scene whose location → RoomProfile → Area → Realm chain leads to ``realm``."""
    area = AreaFactory(realm=realm)
    room_obj = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
    profile = RoomProfileFactory(objectdb=room_obj, area=area)
    return SceneFactory(location=profile.objectdb)


class ExtendDeedAwarenessTests(TestCase):
    def test_no_scene_returns_empty(self) -> None:
        persona = _make_primary_persona()
        deed = fire_renown_award(persona=persona, risk=RenownRisk.LOW)
        from world.societies.models import LegendEntry

        entry = LegendEntry.objects.get(pk=deed.legend_entry_id)
        newly_aware, deltas = extend_deed_awareness(entry, scene=None)
        self.assertEqual(newly_aware, [])
        self.assertEqual(deltas, {})

    def test_extending_to_realm_with_societies_extends_awareness(self) -> None:
        persona = _make_primary_persona()
        # Originating realm A — deed fires with no awareness.
        deed = fire_renown_award(persona=persona, risk=RenownRisk.LOW)
        from world.societies.models import LegendEntry

        entry = LegendEntry.objects.get(pk=deed.legend_entry_id)
        self.assertEqual(entry.societies_aware.count(), 0)

        # Spread happens in a different realm where 2 societies exist.
        new_realm = RealmFactory(name="SpreadRealm")
        SocietyFactory(name="NewSocA", realm=new_realm)
        SocietyFactory(name="NewSocB", realm=new_realm)
        scene = _make_scene_in_realm(new_realm)

        newly_aware, _deltas = extend_deed_awareness(entry, scene=scene)

        self.assertEqual(len(newly_aware), 2)
        self.assertEqual(entry.societies_aware.count(), 2)

    def test_archetype_deltas_fire_one_shot_on_newly_aware_only(self) -> None:
        persona = _make_primary_persona()
        archetype = _make_archetype(mercy_delta=3)  # honor-aligned

        # First fire — deed has an archetype + lands in realm A.
        realm_a = RealmFactory(name="RealmA")
        society_a = SocietyFactory(name="SocA", realm=realm_a, mercy=2)
        area_a = AreaFactory(realm=realm_a)

        result = fire_renown_award(
            persona=persona,
            risk=RenownRisk.LOW,
            archetypes=[archetype],
            origin_area=area_a,
        )

        from world.societies.models import LegendEntry

        entry = LegendEntry.objects.get(pk=result.legend_entry_id)
        self.assertTrue(entry.societies_aware.filter(pk=society_a.pk).exists())
        # Already-aware society stays out of the newly-aware diff.
        scene_a = _make_scene_in_realm(realm_a)
        newly_aware, deltas = extend_deed_awareness(entry, scene=scene_a)
        self.assertEqual(newly_aware, [])
        self.assertEqual(deltas, {})

        # New realm B with a different society — extend triggers a delta.
        realm_b = RealmFactory(name="RealmB")
        society_b = SocietyFactory(name="SocB", realm=realm_b, mercy=4)
        scene_b = _make_scene_in_realm(realm_b)

        newly_aware_b, deltas_b = extend_deed_awareness(entry, scene=scene_b)
        self.assertEqual(newly_aware_b, [society_b.pk])
        # archetype_mercy_delta (3) * society_b.mercy (4) = 12
        self.assertEqual(deltas_b[society_b.pk], 12)
        rep = SocietyReputation.objects.get(persona=persona, society=society_b)
        self.assertEqual(rep.value, 12)

        # Second extend into the same realm — no double-apply.
        newly_aware_again, deltas_again = extend_deed_awareness(entry, scene=scene_b)
        self.assertEqual(newly_aware_again, [])
        self.assertEqual(deltas_again, {})


class SpreadDeedIntegrationTests(TestCase):
    def test_spread_deed_extends_awareness(self) -> None:
        """End-to-end: spread_deed runs extend_deed_awareness internally."""
        from world.societies.services import spread_deed

        persona = _make_primary_persona()
        spreader = _make_primary_persona()
        deed_result = fire_renown_award(persona=persona, risk=RenownRisk.MODERATE)
        from world.societies.models import LegendEntry

        deed = LegendEntry.objects.get(pk=deed_result.legend_entry_id)

        new_realm = RealmFactory(name="SpreadIntegrationRealm")
        SocietyFactory(name="SpreadSoc", realm=new_realm)
        scene = _make_scene_in_realm(new_realm)

        spread_deed(deed, spreader, value_added=5, scene=scene, audience_factor=Decimal(1))

        deed.refresh_from_db()
        self.assertEqual(deed.societies_aware.count(), 1)
