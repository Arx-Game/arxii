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
    BattleSideRole,
    BattleUnitStatus,
)
from world.battles.exceptions import BattleConcludedError
from world.battles.factories import BattleFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory
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

    def test_add_side_accepts_covenant(self) -> None:
        from world.battles.services import add_side, create_battle

        battle = create_battle(name="Siege of Thornwall")
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER, covenant=covenant)
        self.assertEqual(side.covenant_id, covenant.pk)


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
            unit_type="cavalry",
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
            unit_type="guard",
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
