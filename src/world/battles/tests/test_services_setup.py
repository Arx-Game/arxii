"""Tests for battle setup service functions (Task 5).

Covers: create_battle, add_side, add_place, add_unit, enlist_participant,
begin_battle_round, and the BattleError exception hierarchy.
"""

from __future__ import annotations

from django.test import TestCase

from world.battles.constants import (
    DEFAULT_ROUND_LIMIT,
    DEFAULT_VICTORY_THRESHOLD,
    BattleOutcome,
    BattlePosture,
    BattleSideRole,
    BattleUnitStatus,
    TerrainType,
    UnitComposition,
    UnitQuality,
)
from world.battles.exceptions import BattleConcludedError
from world.battles.factories import BattleFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import RoundStatus


class CreateBattleTests(TestCase):
    def test_create_battle_returns_battle_with_scene(self) -> None:
        from world.battles.services import create_battle

        battle = create_battle(name="Test Battle")

        self.assertEqual(battle.name, "Test Battle")
        self.assertIsNotNone(battle.scene_id)
        self.assertEqual(battle.round_limit, DEFAULT_ROUND_LIMIT)
        self.assertEqual(battle.outcome, BattleOutcome.UNRESOLVED)
        self.assertFalse(battle.is_concluded)

    def test_create_battle_with_round_limit(self) -> None:
        from world.battles.services import create_battle

        battle = create_battle(name="Capped Battle", round_limit=5)

        self.assertEqual(battle.round_limit, 5)

    def test_create_battle_without_campaign_story(self) -> None:
        from world.battles.services import create_battle

        battle = create_battle(name="Standalone Battle")

        self.assertIsNone(battle.campaign_story)


class AddSideTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Side Test Battle")

    def test_add_attacker_side(self) -> None:
        from world.battles.services import add_side

        side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)

        self.assertEqual(side.battle, self.battle)
        self.assertEqual(side.role, BattleSideRole.ATTACKER)
        self.assertEqual(side.victory_threshold, DEFAULT_VICTORY_THRESHOLD)
        self.assertEqual(side.victory_points, 0)

    def test_add_defender_side_with_custom_threshold(self) -> None:
        from world.battles.services import add_side

        side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER, victory_threshold=150)

        self.assertEqual(side.role, BattleSideRole.DEFENDER)
        self.assertEqual(side.victory_threshold, 150)

    def test_two_sides_in_battle(self) -> None:
        from world.battles.services import add_side

        add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.assertEqual(self.battle.sides.count(), 2)


class AddPlaceTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Place Test Battle")

    def test_add_place(self) -> None:
        from world.battles.services import add_place

        place = add_place(battle=self.battle, name="The Main Gates")

        self.assertEqual(place.battle, self.battle)
        self.assertEqual(place.name, "The Main Gates")
        self.assertEqual(self.battle.places.count(), 1)


class AddUnitTests(TestCase):
    def setUp(self) -> None:
        from world.battles.services import add_place, add_side

        self.battle = BattleFactory(name="Unit Test Battle")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.place = add_place(battle=self.battle, name="Front Gate")

    def test_add_unit_defaults(self) -> None:
        from world.battles.services import add_unit

        unit = add_unit(
            battle=self.battle,
            side=self.attacker_side,
            name="Cavalry",
            descriptor="cavalry",
        )

        self.assertEqual(unit.battle, self.battle)
        self.assertEqual(unit.side, self.attacker_side)
        self.assertEqual(unit.strength, 100)
        self.assertEqual(unit.status, BattleUnitStatus.ACTIVE)
        self.assertIsNone(unit.place)

    def test_add_unit_at_place_with_custom_strength(self) -> None:
        from world.battles.services import add_unit

        unit = add_unit(
            battle=self.battle,
            side=self.attacker_side,
            name="Elite Guard",
            descriptor="guard",
            strength=80,
            place=self.place,
        )

        self.assertEqual(unit.strength, 80)
        self.assertEqual(unit.place, self.place)


class EnlistParticipantTests(TestCase):
    def setUp(self) -> None:
        from world.battles.services import add_side

        self.battle = BattleFactory(name="Enlist Test Battle")
        self.side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.sheet = CharacterSheetFactory()

    def test_enlist_participant(self) -> None:
        from world.battles.services import enlist_participant

        participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side
        )

        self.assertEqual(participant.battle, self.battle)
        self.assertEqual(participant.character_sheet, self.sheet)
        self.assertEqual(participant.side, self.side)
        self.assertIsNone(participant.place)

    def test_enlist_at_place(self) -> None:
        from world.battles.services import add_place, enlist_participant

        place = add_place(battle=self.battle, name="Outer Wall")
        participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side, place=place
        )

        self.assertEqual(participant.place, place)


class BeginBattleRoundTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(name="Round Test Battle")

    def test_begin_first_round(self) -> None:
        from world.battles.services import begin_battle_round

        battle_round = begin_battle_round(battle=self.battle)

        self.assertEqual(battle_round.battle, self.battle)
        self.assertEqual(battle_round.round_number, 1)
        self.assertEqual(battle_round.status, RoundStatus.DECLARING)

    def test_begin_second_round_increments_number(self) -> None:
        from world.battles.services import begin_battle_round

        first_round = begin_battle_round(battle=self.battle)
        self.assertEqual(first_round.round_number, 1)
        self.assertEqual(first_round.status, RoundStatus.DECLARING)

        second_round = begin_battle_round(battle=self.battle)

        self.assertEqual(second_round.round_number, 2)
        self.assertEqual(second_round.status, RoundStatus.DECLARING)

        # First round should now be COMPLETED
        first_round.refresh_from_db()
        self.assertEqual(first_round.status, RoundStatus.COMPLETED)

    def test_begin_round_raises_for_concluded_battle(self) -> None:
        from world.battles.services import begin_battle_round

        self.battle.outcome = BattleOutcome.DEFENDER_DECISIVE
        self.battle.save()

        with self.assertRaises(BattleConcludedError):
            begin_battle_round(battle=self.battle)

    def test_begin_round_after_resolve_increments_number(self) -> None:
        """After a round is externally set to COMPLETED (simulating resolution),
        begin_battle_round must still derive the correct next number from the
        last round in the DB — not default back to 1.
        """
        from world.battles.services import begin_battle_round

        first_round = begin_battle_round(battle=self.battle)
        self.assertEqual(first_round.round_number, 1)

        # Simulate external resolution: mark the round COMPLETED directly.
        first_round.status = RoundStatus.COMPLETED
        first_round.save(update_fields=["status"])

        second_round = begin_battle_round(battle=self.battle)

        self.assertEqual(second_round.round_number, 2)
        self.assertEqual(second_round.status, RoundStatus.DECLARING)

    def test_current_round_property(self) -> None:
        from world.battles.services import begin_battle_round

        self.assertIsNone(self.battle.current_round)

        round1 = begin_battle_round(battle=self.battle)
        self.battle.refresh_from_db()

        self.assertEqual(self.battle.current_round.pk, round1.pk)


class AddUnitTaxonomyTests(TestCase):
    def test_add_unit_accepts_composition_quality_commander(self) -> None:
        from world.battles.services import add_side, add_unit, create_battle

        battle = create_battle(name="Taxonomy Setup Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        commander = CharacterSheetFactory()

        unit = add_unit(
            battle=battle,
            side=side,
            name="Iron Cavalry",
            descriptor="armored knights",
            composition=UnitComposition.CAVALRY,
            quality=UnitQuality.ELITE,
            commander=commander,
        )

        self.assertEqual(unit.descriptor, "armored knights")
        self.assertEqual(unit.composition, UnitComposition.CAVALRY)
        self.assertEqual(unit.quality, UnitQuality.ELITE)
        self.assertEqual(unit.commander, commander)

    def test_add_unit_defaults_when_taxonomy_omitted(self) -> None:
        from world.battles.services import add_side, add_unit, create_battle

        battle = create_battle(name="Taxonomy Default Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        unit = add_unit(battle=battle, side=side, name="Rabble")

        self.assertEqual(unit.composition, UnitComposition.IRREGULAR)
        self.assertEqual(unit.quality, UnitQuality.TRAINED)
        self.assertIsNone(unit.commander)


class AddPlaceTerrainTests(TestCase):
    def test_add_place_accepts_terrain_and_movement_cost(self) -> None:
        from world.battles.services import add_place, create_battle

        battle = create_battle(name="Terrain Setup Test")
        place = add_place(
            battle=battle,
            name="The Marsh Crossing",
            terrain_type=TerrainType.FLOODED,
            movement_cost=3,
        )
        self.assertEqual(place.terrain_type, TerrainType.FLOODED)
        self.assertEqual(place.movement_cost, 3)

    def test_add_place_defaults(self) -> None:
        from world.battles.services import add_place, create_battle

        battle = create_battle(name="Terrain Default Test")
        place = add_place(battle=battle, name="Open Field")
        self.assertEqual(place.terrain_type, TerrainType.OPEN)
        self.assertEqual(place.movement_cost, 1)


class SetBattleSidePostureTests(TestCase):
    def test_sets_posture(self) -> None:
        from world.battles.services import add_side, create_battle, set_battle_side_posture

        battle = create_battle(name="Posture Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)

        updated = set_battle_side_posture(side=side, posture=BattlePosture.AGGRESSIVE)

        self.assertEqual(updated.posture, BattlePosture.AGGRESSIVE)
        side.refresh_from_db()
        self.assertEqual(side.posture, BattlePosture.AGGRESSIVE)


class AssignUnitCommanderTests(TestCase):
    def test_assigns_commander(self) -> None:
        from world.battles.services import add_side, add_unit, assign_unit_commander, create_battle

        battle = create_battle(name="Commander Assign Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        unit = add_unit(battle=battle, side=side, name="Levy Spears")
        commander = CharacterSheetFactory()

        updated = assign_unit_commander(unit=unit, commander=commander)

        self.assertEqual(updated.commander, commander)
        unit.refresh_from_db()
        self.assertEqual(unit.commander, commander)

    def test_clears_commander_with_none(self) -> None:
        from world.battles.services import add_side, add_unit, assign_unit_commander, create_battle

        battle = create_battle(name="Commander Clear Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        commander = CharacterSheetFactory()
        unit = add_unit(battle=battle, side=side, name="Levy Spears", commander=commander)

        assign_unit_commander(unit=unit, commander=None)

        unit.refresh_from_db()
        self.assertIsNone(unit.commander)
