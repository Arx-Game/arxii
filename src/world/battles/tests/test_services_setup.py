"""Tests for battle setup service functions (Task 5).

Covers: create_battle, add_side, add_place, add_unit, enlist_participant,
begin_battle_round, and the BattleError exception hierarchy.
"""

from __future__ import annotations

from django.test import TestCase
from evennia import create_object

from world.battles.constants import (
    DEFAULT_ROUND_LIMIT,
    DEFAULT_VICTORY_THRESHOLD,
    BattleOutcome,
    BattleSideRole,
    BattleUnitStatus,
)
from world.battles.exceptions import (
    BattleConcludedError,
    NoCommandHierarchyError,
    NotAChampionError,
    PlaceAlreadyDuelingError,
)
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleSideFactory,
)
from world.battles.services import open_champion_duel
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterType, RiskLevel
from world.combat.factories import ThreatPoolFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, CovenantRankFactory, CovenantRoleFactory
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import set_engaged_membership
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


class OpenChampionDuelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.battle = BattleFactory()
        cls.covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        cls.side = BattleSideFactory(battle=cls.battle, covenant=cls.covenant)
        cls.place = BattlePlaceFactory(battle=cls.battle)
        cls.rank = CovenantRankFactory(covenant=cls.covenant)
        cls.champion_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            is_champion_role=True,
            slug="champion-svc-test",
        )
        cls.threat_pool = ThreatPoolFactory()

    def setUp(self):
        self.room = create_object("typeclasses.rooms.Room", key="Champion Duel Room", nohome=True)
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])
        self.sheet = CharacterSheetFactory()
        self.participant = BattleParticipantFactory(
            battle=self.battle, side=self.side, character_sheet=self.sheet, place=self.place
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.champion_role,
            covenant=self.covenant,
            rank=self.rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)

    def test_open_champion_duel_binds_place_to_new_encounter(self):
        enc = open_champion_duel(
            battle_place=self.place,
            challenger_participant=self.participant,
            opponent_kwargs={
                "name": "Warlord's Champion",
                "max_health": 300,
                "threat_pool": self.threat_pool,
            },
        )
        self.place.refresh_from_db()
        self.assertEqual(self.place.combat_encounter_id, enc.pk)
        self.assertEqual(enc.encounter_type, EncounterType.DUEL)
        self.assertEqual(enc.risk_level, RiskLevel.LETHAL)

    def test_open_champion_duel_rejects_non_champion(self) -> None:
        other_sheet = CharacterSheetFactory()
        other_participant = BattleParticipantFactory(
            battle=self.battle, side=self.side, character_sheet=other_sheet, place=self.place
        )
        with self.assertRaises(NotAChampionError):
            open_champion_duel(
                battle_place=self.place,
                challenger_participant=other_participant,
                opponent_kwargs={
                    "name": "Warlord's Champion",
                    "max_health": 300,
                    "threat_pool": self.threat_pool,
                },
            )

    def test_open_champion_duel_rejects_place_already_dueling(self) -> None:
        open_champion_duel(
            battle_place=self.place,
            challenger_participant=self.participant,
            opponent_kwargs={
                "name": "Warlord's Champion",
                "max_health": 300,
                "threat_pool": self.threat_pool,
            },
        )
        with self.assertRaises(PlaceAlreadyDuelingError):
            open_champion_duel(
                battle_place=self.place,
                challenger_participant=self.participant,
                opponent_kwargs={
                    "name": "Second Boss",
                    "max_health": 300,
                    "threat_pool": self.threat_pool,
                },
            )

    def test_open_champion_duel_rejects_side_with_no_covenant(self) -> None:
        no_covenant_side = BattleSideFactory(
            battle=self.battle, role=BattleSideRole.DEFENDER, covenant=None
        )
        other_sheet = CharacterSheetFactory()
        other_participant = BattleParticipantFactory(
            battle=self.battle,
            side=no_covenant_side,
            character_sheet=other_sheet,
            place=self.place,
        )
        with self.assertRaises(NoCommandHierarchyError):
            open_champion_duel(
                battle_place=self.place,
                challenger_participant=other_participant,
                opponent_kwargs={
                    "name": "Warlord's Champion",
                    "max_health": 300,
                    "threat_pool": self.threat_pool,
                },
            )
