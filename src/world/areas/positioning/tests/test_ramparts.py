"""Tests for living-barrier ramparts (#2209)."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.areas.positioning.constants import RampartCrackState, RampartSignature
from world.areas.positioning.factories import (
    PositionFactory,
    RampartElementProfileFactory,
    RampartFactory,
)
from world.areas.positioning.models import PositionEdge, Rampart
from world.areas.positioning.services import (
    connect_positions,
    damage_rampart,
    expire_rampart_rounds,
    raise_rampart,
    rampart_at,
    teardown_ramparts,
)
from world.character_sheets.factories import CharacterSheetFactory


class RaiseRampartTest(TestCase):
    """raise_rampart creates a Rampart row and (for SEAL_EDGES) seals adjacent edges."""

    def setUp(self) -> None:
        self.room = ObjectDB.objects.create(db_key="test_room")
        self.pos = PositionFactory(room=self.room, name="courtyard")
        self.neighbor = PositionFactory(room=self.room, name="gate")
        self.edge = connect_positions(self.pos, self.neighbor, is_passable=True)
        self.sheet = CharacterSheetFactory()
        self.stone_profile = RampartElementProfileFactory(
            name="Stone", signature_behavior=RampartSignature.SEAL_EDGES
        )

    def test_raise_rampart_creates_row(self) -> None:
        rampart = raise_rampart(
            self.pos, caster_sheet=self.sheet, element_profile=self.stone_profile, integrity=24
        )
        self.assertEqual(rampart.position, self.pos)
        self.assertEqual(rampart.element_profile, self.stone_profile)
        self.assertEqual(rampart.integrity, 24)
        self.assertEqual(rampart.max_integrity, 24)
        self.assertEqual(rampart.created_by_sheet, self.sheet)

    def test_seal_edges_seals_adjacent_edges(self) -> None:
        raise_rampart(
            self.pos,
            caster_sheet=self.sheet,
            element_profile=self.stone_profile,
            integrity=24,
            duration_rounds=5,
        )
        edge = PositionEdge.objects.get(pk=self.edge.pk)
        self.assertFalse(edge.is_passable)
        self.assertEqual(edge.duration_rounds, 5)
        self.assertEqual(edge.created_by_sheet, self.sheet)

    def test_non_seal_edges_profile_leaves_edges_alone(self) -> None:
        wind_profile = RampartElementProfileFactory(
            name="Wind", signature_behavior=RampartSignature.MISSILE_WARD
        )
        raise_rampart(self.pos, caster_sheet=self.sheet, element_profile=wind_profile, integrity=24)
        edge = PositionEdge.objects.get(pk=self.edge.pk)
        self.assertTrue(edge.is_passable)

    def test_recast_replaces_existing_rampart(self) -> None:
        first = raise_rampart(
            self.pos, caster_sheet=self.sheet, element_profile=self.stone_profile, integrity=24
        )
        damage_rampart(first, 10)
        second_sheet = CharacterSheetFactory()
        second = raise_rampart(
            self.pos,
            caster_sheet=second_sheet,
            element_profile=self.stone_profile,
            integrity=30,
        )
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.integrity, 30)
        self.assertEqual(second.max_integrity, 30)
        self.assertEqual(second.created_by_sheet, second_sheet)
        self.assertEqual(Rampart.objects.filter(position=self.pos).count(), 1)


class RampartAtTest(TestCase):
    def test_returns_none_when_absent(self) -> None:
        pos = PositionFactory()
        self.assertIsNone(rampart_at(pos))

    def test_returns_rampart_when_present(self) -> None:
        rampart = RampartFactory()
        self.assertEqual(rampart_at(rampart.position), rampart)


class DamageRampartTest(TestCase):
    """damage_rampart chips integrity, exposes crack_state bands, and collapses at 0."""

    def test_chip_reduces_integrity(self) -> None:
        rampart = RampartFactory(integrity=24, max_integrity=30)
        collapsed = damage_rampart(rampart, 6)
        self.assertFalse(collapsed)
        rampart.refresh_from_db()
        self.assertEqual(rampart.integrity, 18)

    def test_crack_state_bands(self) -> None:
        rampart = RampartFactory(integrity=30, max_integrity=30)
        self.assertEqual(rampart.crack_state, RampartCrackState.INTACT)
        damage_rampart(rampart, 10)  # 20/30 -> still > 2/3? 20*3=60 > 30*2=60 false -> CRACKED
        rampart.refresh_from_db()
        self.assertEqual(rampart.crack_state, RampartCrackState.CRACKED)
        damage_rampart(rampart, 15)  # 5/30 -> CRUMBLING
        rampart.refresh_from_db()
        self.assertEqual(rampart.crack_state, RampartCrackState.CRUMBLING)

    def test_damage_rampart_collapses_and_deletes_at_zero(self) -> None:
        rampart = RampartFactory(integrity=5, max_integrity=30)
        pk = rampart.pk
        collapsed = damage_rampart(rampart, 5)
        self.assertTrue(collapsed)
        self.assertFalse(Rampart.objects.filter(pk=pk).exists())

    def test_damage_rampart_collapses_on_overkill(self) -> None:
        rampart = RampartFactory(integrity=5, max_integrity=30)
        pk = rampart.pk
        collapsed = damage_rampart(rampart, 50)
        self.assertTrue(collapsed)
        self.assertFalse(Rampart.objects.filter(pk=pk).exists())


class ExpireTeardownTest(TestCase):
    """expire_rampart_rounds / teardown_ramparts restore/remove ramparts in a room."""

    def setUp(self) -> None:
        self.room = ObjectDB.objects.create(db_key="test_room")
        self.pos = PositionFactory(room=self.room, name="courtyard")

    def test_expire_decrements_and_deletes_at_zero(self) -> None:
        rampart = RampartFactory(position=self.pos, duration_rounds=2)
        expire_rampart_rounds(self.room)
        rampart.refresh_from_db()
        self.assertEqual(rampart.duration_rounds, 1)
        expire_rampart_rounds(self.room)
        self.assertFalse(Rampart.objects.filter(pk=rampart.pk).exists())

    def test_staff_authored_rampart_never_expires(self) -> None:
        rampart = RampartFactory(position=self.pos, duration_rounds=None)
        expire_rampart_rounds(self.room)
        self.assertTrue(Rampart.objects.filter(pk=rampart.pk).exists())

    def test_teardown_deletes_all_ramparts_in_room(self) -> None:
        RampartFactory(position=self.pos)
        other_pos = PositionFactory(room=self.room, name="other")
        RampartFactory(position=other_pos)
        teardown_ramparts(self.room)
        self.assertEqual(Rampart.objects.filter(position__room=self.room).count(), 0)
