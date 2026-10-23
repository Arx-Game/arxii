"""Wall integrity, the walker rule and Rampart unsealing (#4606, slice 1 of #4576).

The player paths (a climbed wall crossed, a fallen Rampart's edge walked) are the
journeys in ``integration_tests/test_crossing_a_wall_journeys.py``; these cover the
seams no journey reaches on its own: the walker rule's table, the shared gate a
Rampart's edges hold, the row constraints and the resist floor.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.areas.positioning.factories import (
    PositionFactory,
    RampartElementProfileFactory,
    RampartElementResistanceFactory,
    RampartFactory,
)
from world.areas.positioning.models import PositionEdge
from world.areas.positioning.services import (
    adjacent_open_positions,
    connect_positions,
    create_conjured_obstacle,
    damage_barrier,
    damage_rampart,
    edge_blocks_crossing,
    expire_rampart_rounds,
    position_graph,
    raise_rampart,
    restore_edge,
    teardown_ramparts,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import DamageTypeFactory
from world.mechanics.factories import ChallengeInstanceFactory


class _Yard(TestCase):
    """Three positions in a row: west - middle - east."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="yard", db_typeclass_path="typeclasses.rooms.Room")
        self.west = PositionFactory(room=self.room, name="west")
        self.middle = PositionFactory(room=self.room, name="middle")
        self.east = PositionFactory(room=self.room, name="east")
        self.west_middle = connect_positions(self.west, self.middle)
        self.middle_east = connect_positions(self.middle, self.east)
        self.sheet = CharacterSheetFactory()

    def gate(self, *, active: bool = True):
        return ChallengeInstanceFactory(
            location=self.room, target_object=self.room, is_active=active
        )

    def wall(self, a, b, *, integrity: int = 12, gate=None) -> PositionEdge:
        return create_conjured_obstacle(
            a, b, caster_sheet=self.sheet, integrity=integrity, gating_challenge=gate
        )


class WalkerRuleTests(_Yard):
    """edge_blocks_crossing reads only the edge row."""

    def test_an_open_edge_lets_a_walker_cross(self) -> None:
        self.assertFalse(edge_blocks_crossing(self.west_middle))

    def test_an_active_gate_blocks(self) -> None:
        self.west_middle.gating_challenge = self.gate()
        self.west_middle.save()
        self.assertTrue(edge_blocks_crossing(self.west_middle))

    def test_a_sealed_edge_with_no_gate_is_a_hard_seal(self) -> None:
        edge = self.wall(self.west, self.middle)
        self.assertTrue(edge_blocks_crossing(edge))

    def test_a_sealed_edge_whose_gate_was_resolved_is_open(self) -> None:
        edge = self.wall(self.west, self.middle, gate=self.gate(active=False))
        self.assertFalse(edge.is_passable)
        self.assertFalse(edge_blocks_crossing(edge))
        self.assertIn(edge, adjacent_open_positions(self.west))

    def test_a_deleted_gate_leaves_a_hard_seal(self) -> None:
        gate = self.gate()
        edge = self.wall(self.west, self.middle, gate=gate)
        gate.delete()
        edge.refresh_from_db()
        self.assertIsNone(edge.gating_challenge_id)
        self.assertTrue(edge_blocks_crossing(edge))


class WallRowTests(_Yard):
    """create_conjured_obstacle writes a wall that always satisfies its constraints."""

    def test_a_caster_wall_without_integrity_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            create_conjured_obstacle(
                self.west, self.middle, caster_sheet=self.sheet, integrity=None
            )

    def test_a_wall_carries_its_integrity(self) -> None:
        edge = self.wall(self.west, self.middle, integrity=12)
        self.assertEqual((edge.integrity, edge.max_integrity), (12, 12))
        self.assertIsNone(edge.source_rampart_id)

    def test_a_rampart_seal_reads_the_ramparts_integrity(self) -> None:
        rampart = raise_rampart(
            self.middle,
            caster_sheet=self.sheet,
            element_profile=RampartElementProfileFactory(),
            integrity=30,
        )
        edge = PositionEdge.objects.get(pk=self.west_middle.pk)
        self.assertEqual(edge.source_rampart, rampart)
        self.assertIsNone(edge.integrity)
        self.assertEqual(edge.barrier_integrity, (30, 30))

    def test_the_database_refuses_a_rampart_seal_with_its_own_integrity(self) -> None:
        rampart = RampartFactory(position=self.middle)
        edge = self.west_middle
        edge.source_rampart = rampart
        edge.integrity = edge.max_integrity = 5
        with self.assertRaises(IntegrityError), transaction.atomic():
            edge.save()

    def test_the_database_refuses_integrity_above_its_maximum(self) -> None:
        edge = self.west_middle
        edge.integrity, edge.max_integrity = 9, 5
        with self.assertRaises(IntegrityError), transaction.atomic():
            edge.save()

    def test_a_later_wall_takes_the_edge_and_releases_the_old_gate(self) -> None:
        old_gate = self.gate()
        self.wall(self.west, self.middle, gate=old_gate)
        new_gate = self.gate()
        edge = self.wall(self.west, self.middle, integrity=20, gate=new_gate)
        old_gate.refresh_from_db()
        self.assertFalse(old_gate.is_active)
        self.assertEqual(edge.gating_challenge, new_gate)
        self.assertEqual(edge.integrity, 20)

    def test_the_map_shows_a_walls_integrity(self) -> None:
        self.wall(self.west, self.middle, integrity=12)
        damage_barrier(PositionEdge.objects.get(pk=self.west_middle.pk), 5)
        info = next(e for e in position_graph(self.room).edges if e.position_a_id == self.west.pk)
        self.assertEqual((info.integrity, info.max_integrity), (7, 12))

    def test_the_map_shows_a_climbed_wall_as_open(self) -> None:
        gate = self.gate()
        self.wall(self.west, self.middle, gate=gate)

        def west_middle():
            return next(
                e for e in position_graph(self.room).edges if e.position_a_id == self.west.pk
            )

        self.assertFalse(west_middle().is_passable)
        self.assertEqual(west_middle().gating_challenge_name, gate.template.name)
        gate.is_active = False
        gate.save()
        self.room.__dict__.pop("positions_cached", None)
        self.assertTrue(west_middle().is_passable)
        self.assertIsNone(west_middle().gating_challenge_name)


class RestoreEdgeTests(_Yard):
    """restore_edge is the one way a wall ends."""

    def test_restore_opens_the_edge_and_clears_the_wall(self) -> None:
        gate = self.gate()
        edge = self.wall(self.west, self.middle, gate=gate)
        restore_edge(edge)
        edge.refresh_from_db()
        gate.refresh_from_db()
        self.assertTrue(edge.is_passable)
        self.assertIsNone(edge.gating_challenge_id)
        self.assertIsNone(edge.integrity)
        self.assertIsNone(edge.max_integrity)
        self.assertIsNone(edge.created_by_sheet_id)
        self.assertFalse(gate.is_active)

    def test_a_shared_gate_stays_live_until_its_last_edge_opens(self) -> None:
        gate = self.gate()
        first = self.wall(self.west, self.middle, gate=gate)
        second = self.wall(self.middle, self.east, gate=gate)
        restore_edge(first)
        gate.refresh_from_db()
        self.assertTrue(gate.is_active)
        restore_edge(second)
        gate.refresh_from_db()
        self.assertFalse(gate.is_active)


class DamageBarrierTests(_Yard):
    """damage_barrier is the one mutation seam for wall integrity."""

    def test_chips_add_up_and_the_wall_falls_at_zero(self) -> None:
        self.wall(self.west, self.middle, integrity=12)
        edge = PositionEdge.objects.get(pk=self.west_middle.pk)
        self.assertFalse(damage_barrier(edge, 4))
        self.assertFalse(damage_barrier(edge, 4))
        self.assertEqual(edge.integrity, 4)
        self.assertTrue(damage_barrier(edge, 9))
        edge.refresh_from_db()
        self.assertTrue(edge.is_passable)
        self.assertIsNone(edge.integrity)

    def test_an_indestructible_edge_takes_nothing(self) -> None:
        edge = connect_positions(self.west, PositionFactory(room=self.room), is_passable=False)
        self.assertFalse(damage_barrier(edge, 50))
        edge.refresh_from_db()
        self.assertFalse(edge.is_passable)

    def test_a_rampart_seal_resists_by_element_and_floors_at_one(self) -> None:
        stone = RampartElementProfileFactory()
        fire = DamageTypeFactory()
        RampartElementResistanceFactory(profile=stone, damage_type=fire, value=10)
        rampart = raise_rampart(
            self.middle, caster_sheet=self.sheet, element_profile=stone, integrity=30
        )
        edge = PositionEdge.objects.get(pk=self.west_middle.pk)
        damage_barrier(edge, 4, damage_type=fire)
        rampart.refresh_from_db()
        self.assertEqual(rampart.integrity, 29)
        damage_barrier(edge, 14, damage_type=fire)
        rampart.refresh_from_db()
        self.assertEqual(rampart.integrity, 25)


class RampartUnsealTests(_Yard):
    """A Rampart that ends, by any of its three delete paths, opens what it sealed."""

    def raise_stone(self, **kwargs):
        return raise_rampart(
            self.middle,
            caster_sheet=self.sheet,
            element_profile=RampartElementProfileFactory(),
            integrity=10,
            **kwargs,
        )

    def assertOpen(self, edge: PositionEdge) -> None:  # noqa: N802 - unittest style
        edge.refresh_from_db()
        self.assertTrue(edge.is_passable)
        self.assertIsNone(edge.source_rampart_id)

    def test_collapse_opens_every_sealed_edge(self) -> None:
        rampart = self.raise_stone()
        self.assertTrue(damage_rampart(rampart, 10))
        self.assertOpen(self.west_middle)
        self.assertOpen(self.middle_east)

    def test_expiry_opens_the_seal(self) -> None:
        self.raise_stone(duration_rounds=1)
        expire_rampart_rounds(self.room)
        self.assertOpen(self.west_middle)

    def test_teardown_opens_the_seal(self) -> None:
        self.raise_stone()
        teardown_ramparts(self.room)
        self.assertOpen(self.middle_east)

    def test_a_shared_gate_closes_once_with_the_rampart(self) -> None:
        gate = self.gate()
        rampart = self.raise_stone(gating_challenge=gate)
        damage_rampart(rampart, 10)
        gate.refresh_from_db()
        self.assertFalse(gate.is_active)

    def test_an_edge_a_later_barricade_took_stays_sealed(self) -> None:
        rampart = self.raise_stone()
        self.wall(self.west, self.middle, integrity=12)
        damage_rampart(rampart, 10)
        taken = PositionEdge.objects.get(pk=self.west_middle.pk)
        self.assertFalse(taken.is_passable)
        self.assertEqual(taken.integrity, 12)
        self.assertOpen(self.middle_east)
