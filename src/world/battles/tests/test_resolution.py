"""Tests for the battle declaration + resolution engine (Task 6).

Uses patched perform_check to control success/failure deterministically.
All tests run on the SQLite fast tier (no progressive conditions).
"""

from __future__ import annotations

import types
from unittest.mock import patch

from django.test import TestCase

from world.battles.constants import (
    BASE_FAILURE_DAMAGE,
    BATTLE_CHECK_TYPE_NAME,
    STRIKE_ATTRITION_PER_LEVEL,
    STRIKE_VP_PER_LEVEL,
    SUPPORT_VP,
    BattleActionKind,
    BattleSideRole,
)
from world.battles.services import add_side, add_unit, begin_battle_round, enlist_participant
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.scenes.constants import RoundStatus
from world.vitals.factories import CharacterVitalsFactory


def _success_result(level: int = 5) -> types.SimpleNamespace:
    """Stub CheckResult with a positive success_level (pass)."""
    return types.SimpleNamespace(success_level=level)


def _failure_result(level: int = -3) -> types.SimpleNamespace:
    """Stub CheckResult with a non-positive success_level (fail)."""
    return types.SimpleNamespace(success_level=level)


class DeclareBattleActionTests(TestCase):
    def setUp(self) -> None:
        from actions.factories import ActionTemplateFactory
        from world.battles.services import create_battle
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        self.battle = create_battle(name="Declaration Test Battle")
        self.side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.sheet = CharacterSheetFactory()
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side
        )
        self.unit_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.unit = add_unit(
            battle=self.battle,
            side=self.unit_side,
            name="Enemy Archers",
            unit_type="archers",
        )
        self.battle_round = begin_battle_round(battle=self.battle)
        # Castable technique (action_template set) for the happy-path declarations
        # below; test_declare_raises_when_technique_has_no_action_template covers
        # the bare-technique (no action_template) rejection path separately.
        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)

    def test_declare_strike_action(self) -> None:
        from world.battles.services import declare_battle_action

        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.unit,
        )

        self.assertEqual(declaration.participant, self.participant)
        self.assertEqual(declaration.action_kind, BattleActionKind.STRIKE)
        self.assertEqual(declaration.technique, self.technique)
        self.assertEqual(declaration.target_unit, self.unit)
        self.assertFalse(declaration.resolved)

    def test_declare_support_action(self) -> None:
        from world.battles.services import declare_battle_action

        # Ally participant on the same side
        ally_sheet = CharacterSheetFactory()
        ally = enlist_participant(battle=self.battle, character_sheet=ally_sheet, side=self.side)
        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
            target_ally=ally,
        )

        self.assertEqual(declaration.action_kind, BattleActionKind.SUPPORT)
        self.assertEqual(declaration.target_ally, ally)

    def test_redeclare_updates_existing(self) -> None:
        """A second declare in the same round replaces the first."""
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
        )
        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.unit,
        )

        self.assertEqual(declaration.action_kind, BattleActionKind.STRIKE)
        # Only one declaration per (round, participant)
        self.assertEqual(self.battle_round.declarations.count(), 1)

    def test_declare_raises_when_no_open_round(self) -> None:
        from world.battles.exceptions import RoundNotOpenError
        from world.battles.services import declare_battle_action

        # Complete the round to close declarations
        self.battle_round.status = RoundStatus.COMPLETED
        self.battle_round.save()

        with self.assertRaises(RoundNotOpenError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.STRIKE,
                technique=self.technique,
            )

    def test_declare_raises_when_character_does_not_know_technique(self) -> None:
        from world.battles.exceptions import CharacterDoesNotKnowTechniqueError
        from world.battles.services import declare_battle_action
        from world.magic.factories import TechniqueFactory

        unknown_technique = TechniqueFactory()
        with self.assertRaises(CharacterDoesNotKnowTechniqueError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.STRIKE,
                technique=unknown_technique,
                target_unit=self.unit,
            )

    def test_declare_raises_when_technique_has_no_action_template(self) -> None:
        from world.battles.exceptions import TechniqueNotBattleReadyError
        from world.battles.services import declare_battle_action
        from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory

        # Default TechniqueFactory leaves action_template unset (None).
        bare_technique = TechniqueFactory()
        CharacterTechniqueFactory(character=self.sheet, technique=bare_technique)
        with self.assertRaises(TechniqueNotBattleReadyError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.STRIKE,
                technique=bare_technique,
                target_unit=self.unit,
            )


class ResolveBattleRoundSuccessTests(TestCase):
    """STRIKE success: unit strength drops, side VP increases, no PC damage."""

    def setUp(self) -> None:
        from world.battles.services import create_battle

        # Seed the CheckType
        category = CheckCategoryFactory(name="Combat")
        CheckTypeFactory(name=BATTLE_CHECK_TYPE_NAME, category=category)

        self.battle = create_battle(name="Resolution Success Battle")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.attacker_side
        )

        self.unit = add_unit(
            battle=self.battle,
            side=self.defender_side,
            name="Skeleton Horde",
            unit_type="undead",
            strength=100,
        )

        self.battle_round = begin_battle_round(battle=self.battle)

    def test_strike_success_reduces_unit_strength_and_awards_vp(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            target_unit=self.unit,
        )

        success_level = 5
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(success_level)
            result = resolve_battle_round(battle_round=self.battle_round)

        self.unit.refresh_from_db()
        expected_attrition = success_level * STRIKE_ATTRITION_PER_LEVEL
        self.assertEqual(self.unit.strength, 100 - expected_attrition)

        self.attacker_side.refresh_from_db()
        expected_vp = success_level * STRIKE_VP_PER_LEVEL
        self.assertEqual(self.attacker_side.victory_points, expected_vp)

        self.assertIn(self.attacker_side.pk, result.vp_awarded)
        self.assertEqual(result.vp_awarded[self.attacker_side.pk], expected_vp)

        # Round should be COMPLETED
        self.battle_round.refresh_from_db()
        self.assertEqual(self.battle_round.status, RoundStatus.COMPLETED)

        # Health should be unchanged (success)
        vitals = self.sheet.vitals
        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 100)

    def test_strike_success_marks_declaration_resolved(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            target_unit=self.unit,
        )
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result()
            resolve_battle_round(battle_round=self.battle_round)

        declare.refresh_from_db()
        self.assertTrue(declare.resolved)
        self.assertGreater(declare.success_level, 0)


class ResolveBattleRoundSupportTests(TestCase):
    """SUPPORT success: side VP increases by SUPPORT_VP."""

    def setUp(self) -> None:
        from world.battles.services import create_battle

        category = CheckCategoryFactory(name="Combat")
        CheckTypeFactory(name=BATTLE_CHECK_TYPE_NAME, category=category)

        self.battle = create_battle(name="Support Battle")
        self.side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side
        )
        self.battle_round = begin_battle_round(battle=self.battle)

    def test_support_success_awards_support_vp(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SUPPORT,
        )
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result()
            resolve_battle_round(battle_round=self.battle_round)

        self.side.refresh_from_db()
        self.assertEqual(self.side.victory_points, SUPPORT_VP)


class ResolveBattleRoundFailureTests(TestCase):
    """STRIKE failure: PC health debited."""

    def setUp(self) -> None:
        from world.battles.services import create_battle

        category = CheckCategoryFactory(name="Combat")
        CheckTypeFactory(name=BATTLE_CHECK_TYPE_NAME, category=category)

        self.battle = create_battle(name="Failure Test Battle")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.sheet = CharacterSheetFactory()
        self.vitals = CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.attacker_side
        )

        self.unit = add_unit(
            battle=self.battle,
            side=self.defender_side,
            name="Zombie Wall",
            unit_type="undead",
        )
        self.battle_round = begin_battle_round(battle=self.battle)

    def test_failure_debits_pc_health(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            target_unit=self.unit,
        )

        failure_level = -3
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _failure_result(failure_level)
            resolve_battle_round(battle_round=self.battle_round)

        self.vitals.refresh_from_db()
        expected_damage = BASE_FAILURE_DAMAGE + abs(failure_level)
        self.assertEqual(self.vitals.health, 100 - expected_damage)

        # VP should be unchanged (failure)
        self.attacker_side.refresh_from_db()
        self.assertEqual(self.attacker_side.victory_points, 0)

        # Unit strength should be unchanged (failure)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.strength, 100)

    def test_failure_records_success_level(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        decl = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            target_unit=self.unit,
        )
        failure_level = -3
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _failure_result(failure_level)
            resolve_battle_round(battle_round=self.battle_round)

        decl.refresh_from_db()
        self.assertTrue(decl.resolved)
        self.assertEqual(decl.success_level, failure_level)


class GetBattleCheckTypeTests(TestCase):
    def test_get_battle_check_type_returns_correct_type(self) -> None:
        from world.battles.resolution import get_battle_check_type

        category = CheckCategoryFactory(name="Combat")
        expected = CheckTypeFactory(name=BATTLE_CHECK_TYPE_NAME, category=category)

        result = get_battle_check_type()

        self.assertEqual(result.pk, expected.pk)
        self.assertEqual(result.name, BATTLE_CHECK_TYPE_NAME)
