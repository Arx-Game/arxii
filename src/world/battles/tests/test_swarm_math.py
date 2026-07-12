"""Tests for swarm-math resolution wired against BattleUnit.individual_count (#1841).

Mirrors world.battles.tests.test_resolution's setup patterns: ResolveBattleRoundSuccessTests
(full technique/participant/round setup, going through resolve_battle_round with a
patched world.battles.resolution.perform_check) and BattleTechniqueResolverModifierStackTests
(direct BattleTechniqueResolver instantiation to inspect the exact extra_modifiers passed to
perform_check). Runs on the SQLite fast tier — no progressive conditions involved.
"""

from __future__ import annotations

import math
from unittest.mock import patch

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.battles.constants import (
    ROUT_MORALE_PER_LEVEL,
    STRIKE_ATTRITION_PER_LEVEL,
    BattleActionKind,
    BattleSideRole,
)
from world.battles.resolution import BattleTechniqueResolver
from world.battles.services import (
    add_side,
    add_unit,
    begin_battle_round,
    create_battle,
    declare_battle_action,
    enlist_participant,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory, TechniqueFactory
from world.vitals.factories import CharacterVitalsFactory


def _success_result(level: int = 1):
    """Stub CheckResult with a positive success_level (pass) — mirrors
    test_resolution._success_result."""
    import types

    return types.SimpleNamespace(success_level=level)


class SwarmStrikeBonusModifierStackTests(TestCase):
    """Item 1: swarm-count band bonus folds into the STRIKE modifier stack;
    a null-count unit gets no such contribution."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

        self.battle = create_battle(name="Swarm Bonus Stack Test")
        self.attacker = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.attacker
        )
        begin_battle_round(battle=self.battle)

    def _declare_strike(self, target_unit):
        return declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=target_unit,
        )

    def test_swarm_unit_strike_gets_band_bonus(self) -> None:
        """A target unit with individual_count=60 (50-199 band) contributes +10 —
        the only nonzero term here (default TRAINED quality, no place, no
        properties, BALANCED posture, no commander)."""
        unit = add_unit(
            battle=self.battle, side=self.defender, name="Goblin Horde", individual_count=60
        )
        declaration = self._declare_strike(unit)

        resolver = BattleTechniqueResolver(
            character=self.sheet.character, technique=self.technique, declaration=declaration
        )
        with patch(
            "world.battles.resolution.perform_check", return_value=_success_result()
        ) as mock_check:
            resolver(power=0, ledger=None, extra_modifiers=0)

        mock_check.assert_called_once()
        self.assertEqual(mock_check.call_args.kwargs["extra_modifiers"], 10)

    def test_null_count_unit_gets_no_swarm_bonus(self) -> None:
        """A target unit with individual_count=None (not swarm-style) contributes 0."""
        unit = add_unit(
            battle=self.battle, side=self.defender, name="Line Infantry", individual_count=None
        )
        declaration = self._declare_strike(unit)

        resolver = BattleTechniqueResolver(
            character=self.sheet.character, technique=self.technique, declaration=declaration
        )
        with patch(
            "world.battles.resolution.perform_check", return_value=_success_result()
        ) as mock_check:
            resolver(power=0, ledger=None, extra_modifiers=0)

        mock_check.assert_called_once()
        self.assertEqual(mock_check.call_args.kwargs["extra_modifiers"], 0)


class SwarmMathRoundResolutionTests(TestCase):
    """Items 2-4: proportional body loss through resolve_battle_round, and the
    non-swarm no-op case. Mirrors test_resolution.ResolveBattleRoundSuccessTests.setUp."""

    def setUp(self) -> None:
        self.battle = create_battle(name="Swarm Math Round Test")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.attacker_side
        )

        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

        self.battle_round = begin_battle_round(battle=self.battle)

    def test_strike_attrition_kills_proportional_bodies(self) -> None:
        """STRIKE's net attrition costs a swarm-style unit ceil-proportional bodies,
        and the round result carries the loss."""
        from world.battles.resolution import resolve_battle_round

        unit = add_unit(
            battle=self.battle,
            side=self.defender_side,
            name="Skeleton Horde",
            strength=100,
            individual_count=60,
        )
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=unit,
        )

        success_level = 1
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(success_level)
            result = resolve_battle_round(battle_round=self.battle_round)

        unit.refresh_from_db()
        net_attrition = success_level * STRIKE_ATTRITION_PER_LEVEL
        expected_lost = math.ceil(60 * net_attrition / 100)
        self.assertEqual(expected_lost, 6)
        self.assertEqual(unit.individual_count, 60 - expected_lost)
        self.assertEqual(unit.strength, 100 - net_attrition)

        self.assertIn(unit.pk, result.unit_losses)
        self.assertEqual(result.unit_losses[unit.pk], expected_lost)

    def test_rout_attrition_costs_bodies_off_morale(self) -> None:
        """ROUT's actual morale loss costs a swarm-style unit ceil-proportional bodies."""
        from world.battles.resolution import resolve_battle_round

        unit = add_unit(
            battle=self.battle,
            side=self.defender_side,
            name="Ghoul Pack",
            morale=70,
            individual_count=80,
        )
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.ROUT,
            technique=self.technique,
            target_unit=unit,
        )

        success_level = 2
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(success_level)
            result = resolve_battle_round(battle_round=self.battle_round)

        unit.refresh_from_db()
        morale_damage = success_level * ROUT_MORALE_PER_LEVEL
        self.assertEqual(unit.morale, 70 - morale_damage)
        expected_lost = math.ceil(80 * morale_damage / 100)
        self.assertEqual(expected_lost, 24)
        self.assertEqual(unit.individual_count, 80 - expected_lost)

        self.assertIn(unit.pk, result.unit_losses)
        self.assertEqual(result.unit_losses[unit.pk], expected_lost)

    def test_non_swarm_unit_fully_unaffected(self) -> None:
        """A unit with individual_count=None takes STRIKE attrition normally (strength
        drops the usual amount), but gets no loss entry and individual_count stays
        None — the swarm-bonus-absence half of this is covered directly by
        SwarmStrikeBonusModifierStackTests.test_null_count_unit_gets_no_swarm_bonus.
        """
        from world.battles.resolution import resolve_battle_round

        unit = add_unit(
            battle=self.battle,
            side=self.defender_side,
            name="Line Infantry",
            strength=100,
            individual_count=None,
        )
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=unit,
        )

        success_level = 1
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(success_level)
            result = resolve_battle_round(battle_round=self.battle_round)

        unit.refresh_from_db()
        self.assertIsNone(unit.individual_count)
        self.assertEqual(unit.strength, 100 - success_level * STRIKE_ATTRITION_PER_LEVEL)
        self.assertNotIn(unit.pk, result.unit_losses)
