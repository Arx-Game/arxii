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
    ConcludeBattleAction,
    DeclareBattleActionAction,
    ResolveBattleRoundAction,
)
from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.battles.constants import BattleActionKind, BattleOutcome
from world.battles.factories import (
    BattleActionDeclarationFactory,
    BattleFactory,
    BattleParticipantFactory,
    BattleRoundFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.battles.models import BattleActionDeclaration
from world.battles.services import conclude_battle
from world.character_sheets.factories import CharacterSheetFactory
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
        from world.checks.factories import CheckTypeFactory

        # Seed a CheckType named "Battle Action" (required by get_battle_check_type()).
        CheckTypeFactory(name="Battle Action")

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
