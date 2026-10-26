"""Journeys for the battle map's drawing columns (#4670, slice 1 of #4651).

A staff-authored blueprint place carries the rectangle it is drawn as and its terrain.
Applying the blueprint to a room gives the live place the same four numbers and terrain.
Drawing only: nothing here changes a rule.
"""

from __future__ import annotations

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import MediaFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.areas.positioning.factories import (
    FeatureTypeFactory,
    MapTerrainFactory,
    PositionFactory,
    PositionFeatureFactory,
)
from world.areas.positioning.models import ObjectPosition
from world.areas.positioning.services import (
    add_blueprint_position,
    attach_feature,
    connect_positions,
    create_blueprint,
    detach_feature,
    instantiate_blueprint,
    place_in_position,
    position_of,
)
from world.combat.constants import CombatAllegiance, OpponentStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatParticipant
from world.conditions.constants import FoundationalCapability
from world.conditions.models import CapabilityType
from world.mechanics.factories import ModifierCategoryFactory
from world.mechanics.models import CharacterModifier, ModifierSource, ModifierTarget
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
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

        movement = CapabilityType.objects.get(name=FoundationalCapability.MOVEMENT)
        target, _ = ModifierTarget.objects.get_or_create(
            name=f"capability_{movement.pk}",
            category=ModifierCategoryFactory(name="capability"),
            defaults={
                "description": "",
                "display_order": 0,
                "is_active": True,
                "target_capability": movement,
            },
        )
        CharacterModifier.objects.create(  # baseline 5 minus 5: rooted
            character=self.ann.sheet_data,
            target=target,
            value=-5,
            source=ModifierSource.objects.create(),
        )

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


class TheEncounterPayloadCarriesTheDrawing(JourneyCase):
    """What the map reads over REST: areas, terrain art, squares and held ground."""

    def setUp(self) -> None:
        super().setUp()
        with override_settings(SEED_SAMPLE_CONTENT=True):  # the movement capability
            ensure_foundational_capabilities()
        self.room = self.make_room("The Manor")
        self.art = MediaFactory()
        self.terrain = MapTerrainFactory(name="Flagstones", art=self.art)
        self.hall = PositionFactory(
            room=self.room,
            name="Hall",
            area_x=2,
            area_y=2,
            area_w=6,
            area_h=4,
            terrain=self.terrain,
        )
        self.porch = PositionFactory(room=self.room, name="Porch")
        self.cellar = PositionFactory(room=self.room, name="Cellar")
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        self.ann = self.make_player("Ann", room=self.room)
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.ann.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        place_in_position(self.ann, self.hall, square=(3, 4))

    def opponent_at(self, position, name: str, *, square=None, **kwargs):
        opponent = CombatOpponentFactory(encounter=self.encounter, name=name, **kwargs)
        place_in_position(opponent.objectdb, position, square=square)
        return opponent

    def body(self) -> dict:
        response = self.api(self.account_of(self.ann)).get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_the_drawing_and_the_standing_square_are_in_the_payload(self):
        body = self.body()

        nodes = {node["name"]: node for node in body["position_nodes"]}
        hall = nodes["Hall"]
        self.assertEqual(
            (hall["area_x"], hall["area_y"], hall["area_w"], hall["area_h"]), (2, 2, 6, 4)
        )
        self.assertEqual(hall["terrain_name"], "Flagstones")
        self.assertEqual(hall["terrain_art_url"], self.art.cloudinary_url)
        porch = nodes["Porch"]
        self.assertIsNone(porch["area_x"])
        self.assertIsNone(porch["terrain_name"])
        self.assertIsNone(porch["terrain_art_url"])
        ann = body["participants"][0]
        self.assertEqual(ann["current_square"], {"x": 3, "y": 4})

    def test_an_opponent_reports_the_square_it_stands_on(self):
        brute = self.opponent_at(self.hall, "Brute", square=(5, 3))

        row = next(o for o in self.body()["opponents"] if o["id"] == brute.pk)

        self.assertEqual(row["current_square"], {"x": 5, "y": 3})

    def test_an_opponent_in_a_place_without_a_square_reports_none(self):
        brute = self.opponent_at(self.porch, "Brute")

        row = next(o for o in self.body()["opponents"] if o["id"] == brute.pk)

        self.assertIsNone(row["current_square"])

    def test_a_step_to_another_square_shows_in_the_payload(self):
        self.assertEqual(self.body()["participants"][0]["current_square"], {"x": 3, "y": 4})

        result = self.web(self.ann, "step_to_square", square_x=4, square_y=4)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(self.body()["participants"][0]["current_square"], {"x": 4, "y": 4})

    def test_ready_enemies_hold_their_place_and_others_do_not(self):
        self.opponent_at(self.porch, "Brute")
        self.opponent_at(self.porch, "Bruiser")
        self.opponent_at(self.cellar, "Ghoul", status=OpponentStatus.DEFEATED)
        self.opponent_at(self.hall, "Hound", allegiance=CombatAllegiance.ALLY)

        held = self.body()["held_positions"]

        self.assertEqual(
            held, [{"position_id": self.porch.pk, "holder_names": ["Brute", "Bruiser"]}]
        )

    @staticmethod
    def reads(captured) -> int:
        """Queries the payload made, leaving out the session row's own bookkeeping."""
        return sum(
            1
            for query in captured.captured_queries
            if "django_session" not in query["sql"] and "SAVEPOINT" not in query["sql"]
        )

    def add_nooks(self, count: int, start: int) -> None:
        for index in range(start, start + count):
            PositionFactory(
                room=self.room,
                name=f"Nook {index}",
                area_x=index,
                area_y=0,
                area_w=1,
                area_h=1,
                terrain=MapTerrainFactory(art=MediaFactory()),
            )

    def test_the_query_count_does_not_grow_with_the_number_of_positions(self):
        self.body()  # warm content types
        self.add_nooks(1, start=0)  # saving a place drops the room's cached graph
        with CaptureQueriesContext(connection) as few:
            self.body()
        self.add_nooks(4, start=1)
        with CaptureQueriesContext(connection) as many:
            self.body()

        self.assertEqual(self.reads(many), self.reads(few))


class TheFeaturesOfAPlaceReachTheMap(TheEncounterPayloadCarriesTheDrawing):
    """What the map draws of a place's features: name, art and square (#4675)."""

    def feature(self, place, name: str, *, art=None, square=None):
        kind = FeatureTypeFactory(name=name, art=art)
        x, y = square if square is not None else (None, None)
        return PositionFeatureFactory(position=place, feature_type=kind, square_x=x, square_y=y)

    def test_the_encounter_lists_each_feature_with_its_art_and_square(self):
        chandelier = self.feature(self.hall, "Chandelier", art=self.art, square=(4, 3))
        rope = self.feature(self.hall, "Rope", square=None)

        nodes = {node["name"]: node for node in self.body()["position_nodes"]}

        self.assertEqual(
            nodes["Hall"]["features"],
            [
                {
                    "id": chandelier.pk,
                    "name": "Chandelier",
                    "art_url": self.art.cloudinary_url,
                    "square_x": 4,
                    "square_y": 3,
                },
                {
                    "id": rope.pk,
                    "name": "Rope",
                    "art_url": None,
                    "square_x": None,
                    "square_y": None,
                },
            ],
        )
        self.assertEqual(nodes["Porch"]["features"], [])

    def test_the_scene_lists_the_same_features(self):
        chandelier = self.feature(self.hall, "Chandelier", art=self.art, square=(4, 3))
        scene = SceneFactory(room=self.room)

        response = self.api(self.account_of(self.ann)).get(f"/api/scenes/{scene.pk}/")

        self.assertEqual(response.status_code, 200, response.content)
        nodes = {node["name"]: node for node in response.json()["position_nodes"]}
        self.assertEqual(
            nodes["Hall"]["features"],
            [
                {
                    "id": chandelier.pk,
                    "name": "Chandelier",
                    "art_url": self.art.cloudinary_url,
                    "square_x": 4,
                    "square_y": 3,
                }
            ],
        )

    def test_the_query_count_does_not_grow_with_the_number_of_features(self):
        self.body()  # warm content types
        self.feature(self.hall, "Chandelier", art=self.art, square=(4, 3))
        with CaptureQueriesContext(connection) as few:
            self.body()
        for index in range(4):
            self.feature(self.hall, f"Rail {index}", art=MediaFactory())
        self.feature(self.porch, "Stairs", art=MediaFactory())
        with CaptureQueriesContext(connection) as many:
            self.body()

        self.assertEqual(self.reads(many), self.reads(few))

    def test_a_feature_added_after_a_read_shows_on_the_next_read(self):
        self.assertEqual(self.body()["position_nodes"][0]["features"], [])
        attach_feature(self.hall, FeatureTypeFactory(name="Balcony rail", art=None))

        nodes = {node["name"]: node for node in self.body()["position_nodes"]}

        self.assertEqual([f["name"] for f in nodes["Hall"]["features"]], ["Balcony rail"])

    def test_a_feature_removed_after_a_read_is_gone_from_the_next_reads(self):
        rope = self.feature(self.hall, "Rope", square=(4, 3))
        scene = SceneFactory(room=self.room)
        client = self.api(self.account_of(self.ann))

        def hall_features(body: dict) -> list[str]:
            nodes = {node["name"]: node for node in body["position_nodes"]}
            return [f["name"] for f in nodes["Hall"]["features"]]

        self.assertEqual(hall_features(self.body()), ["Rope"])
        self.assertEqual(hall_features(client.get(f"/api/scenes/{scene.pk}/").json()), ["Rope"])

        detach_feature(rope)

        self.assertEqual(hall_features(self.body()), [])
        response = client.get(f"/api/scenes/{scene.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(hall_features(response.json()), [])
