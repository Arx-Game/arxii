"""Tests for battle lifecycle actions (#1592).

Each action is tested via ``.run(actor=...)``. GM verbs require a staff actor;
a non-GM actor gets a permission failure. The player declare action requires an
active BattleParticipant in a DECLARING round.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.battles import (
    BeginBattleRoundAction,
    ChallengeChampionDuelAction,
    ConcludeBattleAction,
    DeclareBattleActionAction,
    JoinPlaceEncounterAction,
    OpenPlaceEncounterAction,
    ResolveBattleRoundAction,
)
from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.battles.constants import BattleActionKind, BattleActionScope, BattleOutcome
from world.battles.factories import (
    BattleActionDeclarationFactory,
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleRoundFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.battles.models import BattleActionDeclaration
from world.battles.services import conclude_battle
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import ThreatPoolFactory
from world.covenants.constants import CommandTier, CovenantType
from world.covenants.factories import CovenantFactory, CovenantRankFactory, CovenantRoleFactory
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import set_engaged_membership
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus


def _make_room(label: str = "BattleTestRoom") -> object:
    return ObjectDBFactory(
        db_key=label,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_actor_with_account(
    db_key: str,
    room: object,
    account: object,
) -> tuple[object, object]:
    """Create a PC in *room* whose ``active_account`` is *account*."""
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    RosterTenureFactory(
        roster_entry=entry,
        player_data__account=account,
        end_date=None,
    )
    return char, entry.character_sheet


class BattleActionTestBase(TestCase):
    """Shared fixture: room, GM actor, non-GM actor, battle with two sides and a unit."""

    def setUp(self) -> None:
        self.room = _make_room()

        # GM actor — staff account so _actor_may_gm_battle returns True immediately.
        self.gm_account = AccountFactory(username="gm_battle_tester", is_staff=True)
        self.gm_actor, self.gm_sheet = _make_actor_with_account(
            "gm_battle_actor", self.room, self.gm_account
        )

        # Non-GM actor: Character typeclass object, but no roster/account setup,
        # so active_account returns None → _actor_may_gm_battle returns False.
        self.player_char = CharacterFactory(db_key="player_battle_actor", location=self.room)
        self.player_sheet = CharacterSheetFactory(character=self.player_char)

        # Battle whose scene is active and located in this room.
        # BattleFactory auto-creates a Scene with location=None; update location below.
        self.battle = BattleFactory(name="Test Battle")
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])

        # Two sides on the battle.
        self.attacker_side = BattleSideFactory(battle=self.battle, role="attacker")
        self.defender_side = BattleSideFactory(battle=self.battle, role="defender")

        # One unit on the attacker side (used as a strike target).
        self.unit = BattleUnitFactory(battle=self.battle, side=self.attacker_side)

        # A technique the player knows, castable (has an action_template).
        self.technique = TechniqueFactory(action_template=None)


class BeginBattleRoundActionTests(BattleActionTestBase):
    """BeginBattleRoundAction opens a DECLARING round (GM only)."""

    def test_gm_can_begin_round(self) -> None:
        result = BeginBattleRoundAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        battle_round = self.battle.current_round
        self.assertIsNotNone(battle_round)
        self.assertEqual(battle_round.status, RoundStatus.DECLARING)
        self.assertEqual(battle_round.round_number, 1)

    def test_non_gm_denied(self) -> None:
        result = BeginBattleRoundAction().run(self.player_char)
        self.assertFalse(result.success)
        # No round should have been created.
        self.assertIsNone(self.battle.current_round)

    def test_fails_without_active_battle_in_room(self) -> None:
        other_room = _make_room("OtherRoom_begin")
        self.gm_actor.location = other_room
        result = BeginBattleRoundAction().run(self.gm_actor)
        self.assertFalse(result.success)
        self.assertIsNone(self.battle.current_round)

    def test_successive_begins_increment_round_number(self) -> None:
        BeginBattleRoundAction().run(self.gm_actor)
        # Begin again — should close the first round and open round 2.
        result = BeginBattleRoundAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.assertEqual(self.battle.current_round.round_number, 2)


class ResolveBattleRoundActionTests(BattleActionTestBase):
    """ResolveBattleRoundAction processes all declarations and closes the round."""

    def setUp(self) -> None:
        super().setUp()
        from actions.factories import ActionTemplateFactory
        from world.magic.factories import CharacterAnimaFactory

        # Override the bare technique from BattleActionTestBase with a castable one.
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.player_sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.player_sheet.character, current=20, maximum=30)

        # Enlist the player on the defender side.
        self.participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=self.player_sheet,
        )

        # Open a DECLARING round.
        self.battle_round = BattleRoundFactory(
            battle=self.battle,
            round_number=1,
            status=RoundStatus.DECLARING,
        )

        # Create a declaration (STRIKE targeting the attacker unit).
        self.declaration = BattleActionDeclarationFactory(
            battle_round=self.battle_round,
            participant=self.participant,
            technique=self.technique,
            action_kind=BattleActionKind.STRIKE,
            target_unit=self.unit,
            resolved=False,
        )

    def _mock_check(self, success_level: int) -> MagicMock:
        result = MagicMock()
        result.success_level = success_level
        return result

    def test_gm_can_resolve_round(self) -> None:
        with patch(
            "world.battles.resolution.perform_check",
            return_value=self._mock_check(2),
        ):
            result = ResolveBattleRoundAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.battle_round.refresh_from_db()
        self.assertEqual(self.battle_round.status, RoundStatus.COMPLETED)

    def test_non_gm_denied(self) -> None:
        with patch(
            "world.battles.resolution.perform_check",
            return_value=self._mock_check(2),
        ):
            result = ResolveBattleRoundAction().run(self.player_char)
        self.assertFalse(result.success)
        self.battle_round.refresh_from_db()
        self.assertEqual(self.battle_round.status, RoundStatus.DECLARING)

    def test_fails_when_no_active_round(self) -> None:
        self.battle_round.status = RoundStatus.COMPLETED
        self.battle_round.save(update_fields=["status"])
        result = ResolveBattleRoundAction().run(self.gm_actor)
        self.assertFalse(result.success)

    def test_auto_concludes_when_side_hits_threshold(self) -> None:
        # Pre-load the defender side to the victory threshold so check_victory fires.
        self.defender_side.victory_points = self.defender_side.victory_threshold
        self.defender_side.save(update_fields=["victory_points"])
        with patch(
            "world.battles.resolution.perform_check",
            return_value=self._mock_check(2),
        ):
            result = ResolveBattleRoundAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.battle.refresh_from_db()
        self.assertTrue(self.battle.is_concluded)

    def test_resolve_with_failure_applies_damage(self) -> None:
        from world.vitals.factories import CharacterVitalsFactory

        vitals = CharacterVitalsFactory(character_sheet=self.player_sheet)
        initial_health = vitals.health

        with patch(
            "world.battles.resolution.perform_check",
            return_value=self._mock_check(-2),
        ):
            result = ResolveBattleRoundAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        vitals.refresh_from_db()
        self.assertLess(vitals.health, initial_health)


class ConcludeBattleActionTests(BattleActionTestBase):
    """ConcludeBattleAction force-ends the active battle."""

    def test_gm_can_force_conclude(self) -> None:
        result = ConcludeBattleAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.battle.refresh_from_db()
        self.assertTrue(self.battle.is_concluded)
        self.assertEqual(self.battle.outcome, BattleOutcome.DEFENDER_MARGINAL)

    def test_concludes_with_natural_winner(self) -> None:
        # Push defender 10 VP past threshold; margin 10 < DECISIVE_MARGIN 50 → MARGINAL.
        self.defender_side.victory_points = self.defender_side.victory_threshold + 10
        self.defender_side.save(update_fields=["victory_points"])
        result = ConcludeBattleAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.battle.refresh_from_db()
        self.assertEqual(self.battle.outcome, BattleOutcome.DEFENDER_MARGINAL)

    def test_non_gm_denied(self) -> None:
        result = ConcludeBattleAction().run(self.player_char)
        self.assertFalse(result.success)
        self.battle.refresh_from_db()
        self.assertFalse(self.battle.is_concluded)

    def test_already_concluded_returns_failure(self) -> None:
        conclude_battle(battle=self.battle, outcome=BattleOutcome.ATTACKER_DECISIVE)
        # The battle is now concluded — _active_battle_in_room filters it out, so the
        # action must fail with the "no active battle" message (not an in-execute guard).
        result = ConcludeBattleAction().run(self.gm_actor)
        self.assertFalse(result.success)
        self.assertIn("no active battle", result.message.lower())


class DeclareBattleActionActionTests(BattleActionTestBase):
    """DeclareBattleActionAction records a player's action for the current round."""

    def setUp(self) -> None:
        super().setUp()
        self.participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=self.player_sheet,
        )
        # Override the base technique with one that has a real action_template —
        # declare_battle_action (Task 3) requires action_template_id presence even
        # at declare time (TechniqueNotBattleReadyError), so the base class's bare
        # technique (action_template=None) would fail every success-path test here.
        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        CharacterTechniqueFactory(character=self.player_sheet, technique=self.technique)
        self.battle_round = BattleRoundFactory(
            battle=self.battle,
            round_number=1,
            status=RoundStatus.DECLARING,
        )

    def test_player_can_declare_strike(self) -> None:
        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.STRIKE,
            technique_id=self.technique.pk,
            target_unit=self.unit,
        )
        self.assertTrue(result.success, result.message)
        self.assertTrue(
            BattleActionDeclaration.objects.filter(
                battle_round=self.battle_round,
                participant=self.participant,
                action_kind=BattleActionKind.STRIKE,
                technique=self.technique,
                target_unit=self.unit,
            ).exists()
        )

    def test_player_can_declare_support(self) -> None:
        ally_char = CharacterFactory(db_key="battle_ally", location=self.room)
        ally_sheet = CharacterSheetFactory(character=ally_char)
        ally_participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=ally_sheet,
        )
        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.SUPPORT,
            technique_id=self.technique.pk,
            target_ally=ally_participant,
        )
        self.assertTrue(result.success, result.message)
        self.assertTrue(
            BattleActionDeclaration.objects.filter(
                battle_round=self.battle_round,
                participant=self.participant,
                action_kind=BattleActionKind.SUPPORT,
                technique=self.technique,
                target_ally=ally_participant,
            ).exists()
        )

    def test_non_participant_fails(self) -> None:
        outsider = CharacterFactory(db_key="outsider_battle", location=self.room)
        CharacterSheetFactory(character=outsider)
        result = DeclareBattleActionAction().run(
            outsider,
            action_kind=BattleActionKind.STRIKE,
            technique_id=self.technique.pk,
            target_unit=self.unit,
        )
        self.assertFalse(result.success)
        self.assertIn("not", result.message.lower())

    def test_no_open_round_fails(self) -> None:
        # Close the round first.
        self.battle_round.status = RoundStatus.COMPLETED
        self.battle_round.save(update_fields=["status"])
        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.STRIKE,
            technique_id=self.technique.pk,
            target_unit=self.unit,
        )
        self.assertFalse(result.success)

    def test_redeclare_updates_existing(self) -> None:
        # First declaration: STRIKE.
        result1 = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.STRIKE,
            technique_id=self.technique.pk,
            target_unit=self.unit,
        )
        self.assertTrue(result1.success, result1.message)
        # Second declaration: SUPPORT (should update, not create a second row).
        ally_char = CharacterFactory(db_key="battle_ally2", location=self.room)
        ally_sheet = CharacterSheetFactory(character=ally_char)
        ally_participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=ally_sheet,
        )
        result2 = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.SUPPORT,
            technique_id=self.technique.pk,
            target_ally=ally_participant,
        )
        self.assertTrue(result2.success, result2.message)
        count = BattleActionDeclaration.objects.filter(
            battle_round=self.battle_round,
            participant=self.participant,
        ).count()
        self.assertEqual(count, 1)
        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.action_kind, BattleActionKind.SUPPORT)

    def test_unknown_technique_id_fails(self) -> None:
        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.STRIKE,
            technique_id=999999,
            target_unit=self.unit,
        )
        self.assertFalse(result.success)
        self.assertIn("technique", result.message.lower())

    def test_declare_battle_action_passes_through_side_scope(self) -> None:
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.defender_side.covenant = covenant
        self.defender_side.save(update_fields=["covenant"])
        rank = CovenantRankFactory(covenant=covenant)
        supreme_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUPREME,
            slug="action-test-supreme",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.player_sheet,
            covenant_role=supreme_role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)

        # Target the enemy (attacker) side, not the commander's own (defender)
        # side (#1710 Finding 2: STRIKE against target_side == participant's
        # own side is rejected at declare time).
        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.STRIKE,
            technique_id=self.technique.pk,
            scope=BattleActionScope.SIDE,
            target_side=self.attacker_side,
        )

        self.assertTrue(result.success, result.message)
        decl = BattleActionDeclaration.objects.get(pk=result.data["declaration_id"])
        self.assertEqual(decl.scope, BattleActionScope.SIDE)
        self.assertEqual(decl.target_side_id, self.attacker_side.pk)

    def test_declare_battle_action_passes_through_target_fortification_fortify(self) -> None:
        from world.battles.factories import BattlePlaceFactory, FortificationFactory

        place = BattlePlaceFactory(battle=self.battle)
        fort = FortificationFactory(place=place, defending_side=self.defender_side)

        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.FORTIFY,
            technique_id=self.technique.pk,
            target_fortification=fort,
        )

        self.assertTrue(result.success, result.message)
        decl = BattleActionDeclaration.objects.get(pk=result.data["declaration_id"])
        self.assertEqual(decl.action_kind, BattleActionKind.FORTIFY)
        self.assertEqual(decl.target_fortification_id, fort.pk)

    def test_declare_battle_action_passes_through_target_fortification_breach(self) -> None:
        from world.battles.factories import BattlePlaceFactory, FortificationFactory

        place = BattlePlaceFactory(battle=self.battle)
        # The participant is on defender_side; a BREACH target must belong to the
        # *enemy* side (attacker_side) — FORTIFY requires the participant's own
        # side, BREACH requires the opposing side (#1713 ownership check).
        fort = FortificationFactory(place=place, defending_side=self.attacker_side)

        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.BREACH,
            technique_id=self.technique.pk,
            target_fortification=fort,
        )

        self.assertTrue(result.success, result.message)
        decl = BattleActionDeclaration.objects.get(pk=result.data["declaration_id"])
        self.assertEqual(decl.action_kind, BattleActionKind.BREACH)
        self.assertEqual(decl.target_fortification_id, fort.pk)

    def test_declare_battle_action_forwards_reposition_dx_dy(self) -> None:
        from decimal import Decimal

        from world.battles.constants import VehicleKind
        from world.battles.services import create_battle_vehicle

        vehicle = create_battle_vehicle(
            battle=self.battle,
            side=self.defender_side,
            place_name="The Gull",
            vehicle_kind=VehicleKind.SHIP,
        )
        vehicle.unit.commander = self.player_sheet
        vehicle.unit.save(update_fields=["commander"])

        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.REPOSITION,
            technique_id=self.technique.pk,
            scope=BattleActionScope.PLACE,
            target_place=vehicle.place,
            reposition_dx=Decimal(10),
            reposition_dy=Decimal(5),
        )
        self.assertTrue(result.success, result.message)
        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.reposition_dx, Decimal(10))
        self.assertEqual(decl.reposition_dy, Decimal(5))

    def test_player_can_declare_move_self(self) -> None:
        place = BattlePlaceFactory(battle=self.battle, name="The Ford")
        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.MOVE,
            technique_id=self.technique.pk,
            target_place=place,
        )
        self.assertTrue(result.success, result.message)
        self.assertTrue(
            BattleActionDeclaration.objects.filter(
                battle_round=self.battle_round,
                participant=self.participant,
                action_kind=BattleActionKind.MOVE,
                scope=BattleActionScope.UNIT,
                target_place=place,
            ).exists()
        )

    def test_player_can_declare_move_withdraw(self) -> None:
        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.MOVE,
            technique_id=self.technique.pk,
            target_place=None,
        )
        self.assertTrue(result.success, result.message)
        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.action_kind, BattleActionKind.MOVE)
        self.assertIsNone(decl.target_place)

    def test_commander_can_declare_move_order(self) -> None:
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.defender_side.covenant = covenant
        self.defender_side.save(update_fields=["covenant"])
        rank = CovenantRankFactory(covenant=covenant)
        subordinate_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="action-test-move-subordinate",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.player_sheet,
            covenant_role=subordinate_role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)
        own_unit = BattleUnitFactory(battle=self.battle, side=self.defender_side)
        place = BattlePlaceFactory(battle=self.battle, name="The Ford")

        result = DeclareBattleActionAction().run(
            self.player_char,
            action_kind=BattleActionKind.MOVE,
            technique_id=self.technique.pk,
            scope=BattleActionScope.PLACE,
            target_unit=own_unit,
            target_place=place,
        )
        self.assertTrue(result.success, result.message)
        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.action_kind, BattleActionKind.MOVE)
        self.assertEqual(decl.target_unit_id, own_unit.pk)
        self.assertEqual(decl.target_place_id, place.pk)


class ChallengeChampionDuelActionTests(BattleActionTestBase):
    """ChallengeChampionDuelAction opens a lethal duel bound to a BattlePlace."""

    def setUp(self) -> None:
        super().setUp()
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])
        self.covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.defender_side.covenant = self.covenant
        self.defender_side.save(update_fields=["covenant"])
        self.place = BattlePlaceFactory(battle=self.battle)
        self.participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=self.player_sheet,
            place=self.place,
        )
        rank = CovenantRankFactory(covenant=self.covenant)
        champion_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            is_champion_role=True,
            slug="action-test-champion",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.player_sheet,
            covenant_role=champion_role,
            covenant=self.covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)
        self.threat_pool = ThreatPoolFactory()

    def test_challenge_champion_duel_action_binds_place(self) -> None:
        result = ChallengeChampionDuelAction().run(
            self.player_char,
            battle_place_id=self.place.pk,
            opponent_kwargs={
                "name": "Warlord's Champion",
                "max_health": 300,
                "threat_pool": self.threat_pool.pk,
            },
        )
        self.assertTrue(result.success, result.message)
        self.place.refresh_from_db()
        self.assertIsNotNone(self.place.combat_encounter_id)


class OpenPlaceEncounterActionTests(BattleActionTestBase):
    """OpenPlaceEncounterAction opens a general party encounter at a front (#2008)."""

    def setUp(self) -> None:
        super().setUp()
        self.place = BattlePlaceFactory(battle=self.battle)
        # MinimumGMLevelPrerequisite's staff bypass checks the live-puppet
        # `.account` attribute, not `active_account` (roster tenure) —
        # self.gm_actor has no live session here, so it needs its own
        # GMProfile to clear the prerequisite (mirrors
        # actions/tests/test_battle_staging_actions.py's staging-action fixtures).
        GMProfileFactory(account=self.gm_account, level=GMLevel.JUNIOR)

    def test_gm_opens_encounter_at_place(self) -> None:
        result = OpenPlaceEncounterAction().run(self.gm_actor, battle_place_id=self.place.pk)

        self.assertTrue(result.success, result.message)
        self.place.refresh_from_db()
        self.assertIsNotNone(self.place.combat_encounter_id)

    def test_non_gm_is_refused(self) -> None:
        result = OpenPlaceEncounterAction().run(self.player_char, battle_place_id=self.place.pk)

        self.assertFalse(result.success)
        self.place.refresh_from_db()
        self.assertIsNone(self.place.combat_encounter_id)

    def test_already_bound_place_is_refused(self) -> None:
        from world.battles.services import open_place_encounter

        open_place_encounter(battle_place=self.place)

        result = OpenPlaceEncounterAction().run(self.gm_actor, battle_place_id=self.place.pk)

        self.assertFalse(result.success)

    def test_junior_gm_not_this_battles_gm_is_refused(self) -> None:
        # A JUNIOR-trust GM who is *not* this battle's own GM (and not staff)
        # clears MinimumGMLevelPrerequisite but must still be rejected by the
        # execute()-time _actor_may_gm_battle re-check (#2008 Finding 1).
        other_gm_account = AccountFactory(username="other_gm_battle_tester")
        GMProfileFactory(account=other_gm_account, level=GMLevel.JUNIOR)
        other_gm_actor, _ = _make_actor_with_account(
            "other_gm_battle_actor", self.room, other_gm_account
        )

        result = OpenPlaceEncounterAction().run(other_gm_actor, battle_place_id=self.place.pk)

        self.assertFalse(result.success)
        self.place.refresh_from_db()
        self.assertIsNone(self.place.combat_encounter_id)


class JoinPlaceEncounterActionTests(BattleActionTestBase):
    """JoinPlaceEncounterAction lets a stationed participant join an open front (#2008)."""

    def setUp(self) -> None:
        super().setUp()
        from world.battles.services import open_place_encounter

        self.place = BattlePlaceFactory(battle=self.battle)
        self.participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=self.player_sheet,
            place=None,
        )
        self.encounter = open_place_encounter(battle_place=self.place)

    def test_stationed_participant_can_join(self) -> None:
        self.participant.place = self.place
        self.participant.save(update_fields=["place"])

        result = JoinPlaceEncounterAction().run(self.player_char, battle_place_id=self.place.pk)

        self.assertTrue(result.success, result.message)
        self.assertEqual(self.encounter.participants.count(), 1)

    def test_non_stationed_participant_is_refused(self) -> None:
        # self.participant.place is None (set explicitly above) — not stationed
        # at self.place.
        result = JoinPlaceEncounterAction().run(self.player_char, battle_place_id=self.place.pk)

        self.assertFalse(result.success)
        self.assertEqual(self.encounter.participants.count(), 0)

    def test_duel_type_encounter_is_refused(self) -> None:
        # A strict 1v1 Champion Duel bound to this front must not accept a
        # third party joining through the general-join action (#2008 Finding 2a).
        from world.combat.constants import EncounterType

        self.encounter.encounter_type = EncounterType.DUEL
        self.encounter.save(update_fields=["encounter_type"])
        self.participant.place = self.place
        self.participant.save(update_fields=["place"])

        result = JoinPlaceEncounterAction().run(self.player_char, battle_place_id=self.place.pk)

        self.assertFalse(result.success)
        self.assertEqual(self.encounter.participants.count(), 0)

    def test_non_active_participant_is_refused(self) -> None:
        # A WITHDRAWN/INCAPACITATED participant still stationed at the place
        # must not be able to rejoin combat (#2008 Finding 2b).
        from world.battles.constants import BattleParticipantStatus

        self.participant.place = self.place
        self.participant.status = BattleParticipantStatus.WITHDRAWN
        self.participant.save(update_fields=["place", "status"])

        result = JoinPlaceEncounterAction().run(self.player_char, battle_place_id=self.place.pk)

        self.assertFalse(result.success)
        self.assertEqual(self.encounter.participants.count(), 0)
