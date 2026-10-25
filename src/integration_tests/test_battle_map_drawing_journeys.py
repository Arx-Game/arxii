"""Journeys for the battle map's drawing columns (#4670, slice 1 of #4651).

A staff-authored blueprint place carries the rectangle it is drawn as and its terrain.
Applying the blueprint to a room gives the live place the same four numbers and terrain.
Drawing only: nothing here changes a rule.
"""

from __future__ import annotations

from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from evennia_extensions.factories import MediaFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.areas.positioning.factories import MapTerrainFactory, PositionFactory
from world.areas.positioning.models import ObjectPosition
from world.areas.positioning.services import (
    add_blueprint_position,
    connect_positions,
    create_blueprint,
    instantiate_blueprint,
    place_in_position,
    position_of,
)
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatParticipant
from world.scenes.constants import RoundStatus
from world.vitals.seeds import ensure_foundational_capabilities


class BlueprintAreaAndTerrainJourneys(TestCase):
    def test_blueprint_place_area_and_terrain_reach_the_live_room(self):
        art = MediaFactory()
        terrain = MapTerrainFactory(name="Wood planks", art=art)
        blueprint = create_blueprint("Tavern")
        bp_pos = add_blueprint_position(blueprint, "Common Room")
        bp_pos.area_x, bp_pos.area_y, bp_pos.area_w, bp_pos.area_h = 2, 2, 8, 9
        bp_pos.terrain = terrain
        bp_pos.save()
        room = RoomProfileFactory().objectdb

        positions = instantiate_blueprint(blueprint, room)

        live = positions[0]
        live.refresh_from_db()
        self.assertEqual((live.area_x, live.area_y, live.area_w, live.area_h), (2, 2, 8, 9))
        self.assertEqual(live.terrain, terrain)
        self.assertEqual(live.terrain.art, art)

    def test_a_partial_area_is_refused(self):
        blueprint = create_blueprint("Cellar")
        bp_pos = add_blueprint_position(blueprint, "Stairs")
        bp_pos.area_x = 1
        with self.assertRaises(IntegrityError), transaction.atomic():
            bp_pos.save()

    def test_a_zero_sized_area_is_refused(self):
        blueprint = create_blueprint("Attic")
        bp_pos = add_blueprint_position(blueprint, "Loft")
        bp_pos.area_x, bp_pos.area_y, bp_pos.area_w, bp_pos.area_h = 1, 1, 0, 3
        with self.assertRaises(IntegrityError), transaction.atomic():
            bp_pos.save()

    def test_an_area_missing_its_height_is_refused(self):
        blueprint = create_blueprint("Barn")
        bp_pos = add_blueprint_position(blueprint, "Loft")
        bp_pos.area_x, bp_pos.area_y, bp_pos.area_w = 1, 1, 3
        with self.assertRaises(IntegrityError), transaction.atomic():
            bp_pos.save()

    def test_a_live_place_missing_its_height_is_refused(self):
        position = PositionFactory()
        position.area_x, position.area_y, position.area_w = 1, 1, 3
        with self.assertRaises(IntegrityError), transaction.atomic():
            position.save()


class StandingOnASquare(JourneyCase):
    """The Hall is drawn as a 6x4 rectangle at (2, 2); the Porch has no area."""

    def setUp(self) -> None:
        super().setUp()
        with override_settings(SEED_SAMPLE_CONTENT=True):  # the movement capability
            ensure_foundational_capabilities()
        self.room = self.make_room("The Manor")
        self.hall = PositionFactory(
            room=self.room, name="Hall", area_x=2, area_y=2, area_w=6, area_h=4
        )
        self.porch = PositionFactory(room=self.room, name="Porch")
        connect_positions(self.porch, self.hall)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        self.ann = self.make_player("Ann", room=self.room)
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.ann.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        place_in_position(self.ann, self.porch)

    def square_of(self, character) -> tuple[int | None, int | None]:
        row = ObjectPosition.objects.get(objectdb=character)
        return row.square_x, row.square_y

    def hops(self) -> int:
        return CombatParticipant.objects.get(
            encounter=self.encounter, character_sheet=self.ann.sheet_data
        ).hops_used

    def test_move_with_a_square_lands_on_it(self) -> None:
        result = self.web(
            self.ann, "move_to_position", position_id=self.hall.pk, square_x=3, square_y=4
        )

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(position_of(self.ann), self.hall)
        self.assertEqual(self.square_of(self.ann), (3, 4))

    def test_a_square_outside_the_area_is_refused_and_nothing_moves(self) -> None:
        result = self.web(
            self.ann, "move_to_position", position_id=self.hall.pk, square_x=8, square_y=2
        )

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "That square is outside Hall.")
        self.assertEqual(position_of(self.ann), self.porch)
        self.assertEqual(self.hops(), 0)

    def test_an_occupied_square_is_refused(self) -> None:
        bob = self.make_player("Bob", room=self.room)
        place_in_position(bob, self.hall, square=(3, 3))

        result = self.web(
            self.ann, "move_to_position", position_id=self.hall.pk, square_x=3, square_y=3
        )

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "Someone is standing there.")
        self.assertEqual(position_of(self.ann), self.porch)
        self.assertEqual(self.hops(), 0)

    def test_a_place_with_no_area_has_no_squares_to_pick(self) -> None:
        place_in_position(self.ann, self.hall)

        result = self.web(
            self.ann, "move_to_position", position_id=self.porch.pk, square_x=1, square_y=1
        )

        self.assertEqual(result.detail.message, "Porch has no squares to pick.")
        self.assertEqual(position_of(self.ann), self.hall)

    def test_one_coordinate_alone_is_refused(self) -> None:
        result = self.web(self.ann, "move_to_position", position_id=self.hall.pk, square_x=3)

        self.assertEqual(result.detail.message, "Pick a square with both coordinates.")
        self.assertEqual(position_of(self.ann), self.porch)

    def test_stepping_to_a_square_in_her_own_place_costs_no_hop(self) -> None:
        place_in_position(self.ann, self.hall, square=(2, 2))

        result = self.web(self.ann, "step_to_square", square_x=5, square_y=5)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(self.square_of(self.ann), (5, 5))
        self.assertEqual(position_of(self.ann), self.hall)
        self.assertEqual(self.hops(), 0)

    def test_stepping_onto_an_occupied_square_is_refused(self) -> None:
        bob = self.make_player("Bob", room=self.room)
        place_in_position(bob, self.hall, square=(5, 5))
        place_in_position(self.ann, self.hall, square=(2, 2))

        result = self.web(self.ann, "step_to_square", square_x=5, square_y=5)

        self.assertEqual(result.detail.message, "Someone is standing there.")
        self.assertEqual(self.square_of(self.ann), (2, 2))

    def test_an_unplaced_actor_cannot_step(self) -> None:
        cal = self.make_player("Cal", room=self.room)

        result = self.web(cal, "step_to_square", square_x=3, square_y=3)

        self.assertEqual(result.detail.message, "You aren't standing anywhere.")

    def test_a_later_plain_move_clears_the_square(self) -> None:
        place_in_position(self.ann, self.hall, square=(4, 4))

        result = self.web(self.ann, "move_to_position", position_id=self.porch.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(self.square_of(self.ann), (None, None))

    def test_an_actor_who_cannot_move_cannot_step(self) -> None:
        place_in_position(self.ann, self.hall, square=(2, 2))

        with mock.patch("world.areas.positioning.services._can_move", return_value=False):
            result = self.web(self.ann, "step_to_square", square_x=5, square_y=5)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "You cannot move.")
        self.assertEqual(self.square_of(self.ann), (2, 2))

    def test_taking_a_position_with_a_square_lands_on_it(self) -> None:
        cal = self.make_player("Cal", room=self.room)

        result = self.web(cal, "take_position", position_id=self.hall.pk, square_x=7, square_y=5)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(position_of(cal), self.hall)
        self.assertEqual(self.square_of(cal), (7, 5))
