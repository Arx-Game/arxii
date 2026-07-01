"""Tests for the battle declaration + resolution engine (Task 6).

Uses patched perform_check to control success/failure deterministically.
All tests run on the SQLite fast tier (no progressive conditions).
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

from django.test import TestCase, tag

from actions.factories import ActionTemplateFactory
from world.battles.constants import (
    BASE_FAILURE_DAMAGE,
    STRIKE_ATTRITION_PER_LEVEL,
    STRIKE_VP_PER_LEVEL,
    SUPPORT_VP,
    BattleActionKind,
    BattleSideRole,
)
from world.battles.services import add_side, add_unit, begin_battle_round, enlist_participant
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.types import CheckResult
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
)
from world.scenes.constants import RoundStatus
from world.vitals.factories import CharacterVitalsFactory, ensure_surrounded_content


def _success_result(level: int = 5) -> types.SimpleNamespace:
    """Stub CheckResult with a positive success_level (pass)."""
    return types.SimpleNamespace(success_level=level)


def _failure_result(level: int = -3) -> types.SimpleNamespace:
    """Stub CheckResult with a non-positive success_level (fail)."""
    return types.SimpleNamespace(success_level=level)


class BattleTechniqueResolverTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

    def test_resolve_battle_technique_returns_check_result(self) -> None:
        from world.battles.resolution import resolve_battle_technique
        from world.battles.services import (
            add_side,
            begin_battle_round,
            create_battle,
            declare_battle_action,
            enlist_participant,
        )

        battle = create_battle(name="Resolver Unit Test Battle")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        participant = enlist_participant(battle=battle, character_sheet=self.sheet, side=side)
        begin_battle_round(battle=battle)
        declaration = declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
        )

        fake_result = CheckResult(
            check_type=self.technique.action_template.check_type,
            outcome=None,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        with patch("world.battles.resolution.perform_check", return_value=fake_result):
            check_result = resolve_battle_technique(declaration=declaration)

        self.assertIs(check_result, fake_result)


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
        from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory

        self.battle = create_battle(name="Resolution Success Battle")
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
            technique=self.technique,
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
            technique=self.technique,
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
        from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory

        self.battle = create_battle(name="Support Battle")
        self.side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side
        )

        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

        self.battle_round = begin_battle_round(battle=self.battle)

    def test_support_success_awards_support_vp(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
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
        from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory

        self.battle = create_battle(name="Failure Test Battle")
        self.attacker_side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = add_side(battle=self.battle, role=BattleSideRole.DEFENDER)

        self.sheet = CharacterSheetFactory()
        self.vitals = CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.attacker_side
        )

        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), damage_profile=False
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

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
            technique=self.technique,
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
            technique=self.technique,
            target_unit=self.unit,
        )
        failure_level = -3
        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _failure_result(failure_level)
            resolve_battle_round(battle_round=self.battle_round)

        decl.refresh_from_db()
        self.assertTrue(decl.resolved)
        self.assertEqual(decl.success_level, failure_level)


class BattleRoundAudereWiringTests(TestCase):
    """Proves resolve_battle_round routes through use_technique, which fires the
    Audere Majora hook (Step 8c) automatically — no battle-specific wiring needed.
    """

    def setUp(self) -> None:
        from world.battles.services import create_battle
        from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory
        from world.traits.factories import CheckSystemSetupFactory

        CheckSystemSetupFactory.create()

        self.battle = create_battle(name="Audere Wiring Test Battle")
        self.side = add_side(battle=self.battle, role=BattleSideRole.ATTACKER)

        self.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.participant = enlist_participant(
            battle=self.battle, character_sheet=self.sheet, side=self.side
        )

        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(),
            damage_profile=False,
            intensity=5,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet.character, current=20, maximum=30)

        self.battle_round = begin_battle_round(battle=self.battle)

    def test_resolve_battle_round_calls_audere_majora_hook(self) -> None:
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import declare_battle_action

        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SUPPORT,
            technique=self.technique,
        )

        # maybe_create_audere_majora_offer is imported function-locally inside
        # use_technique (world/magic/services/techniques.py:1094), not at module
        # level — repo convention for lazy imports is to patch the ORIGIN module
        # so the call-time `from X import Y` re-binds to the patched callable
        # (see reference-module-import-breaks-origin-patch memory).
        with patch("world.magic.audere_majora.maybe_create_audere_majora_offer") as mock_audere:
            resolve_battle_round(battle_round=self.battle_round)

        mock_audere.assert_called_once()
        called_character, called_intensity = mock_audere.call_args[0]
        self.assertEqual(called_character, self.sheet.character)
        self.assertEqual(called_intensity, self.technique.intensity)


class IsolationAndMobilityTests(TestCase):
    def test_is_isolated_true_with_no_ally_at_place(self) -> None:
        from world.battles.resolution import _is_isolated
        from world.battles.services import add_place, create_battle

        battle = create_battle(name="Isolation Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        sheet = CharacterSheetFactory()
        participant = enlist_participant(
            battle=battle, character_sheet=sheet, side=side, place=place
        )
        assert _is_isolated(participant) is True

    def test_is_isolated_false_with_ally_at_same_place(self) -> None:
        from world.battles.resolution import _is_isolated
        from world.battles.services import add_place, create_battle

        battle = create_battle(name="Isolation Test 2")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        p1 = enlist_participant(
            battle=battle, character_sheet=CharacterSheetFactory(), side=side, place=place
        )
        enlist_participant(
            battle=battle, character_sheet=CharacterSheetFactory(), side=side, place=place
        )
        assert _is_isolated(p1) is False


class SelectSurroundedTerminalPoolTests(TestCase):
    def test_routes_to_enemy_pool_when_no_pc_opposes_at_place(self) -> None:
        from world.battles.resolution import select_surrounded_terminal_pool
        from world.battles.services import add_place, create_battle
        from world.vitals.factories import ensure_surrounded_content

        content = ensure_surrounded_content()
        battle = create_battle(name="Routing Test")
        attacker = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        participant = enlist_participant(
            battle=battle, character_sheet=CharacterSheetFactory(), side=attacker, place=place
        )
        pool = select_surrounded_terminal_pool(battle=battle, participant=participant)
        assert pool == content["pools"]["surrounded_terminal_enemy"]

    def test_routes_to_pvp_pool_when_opposing_pc_present_at_place(self) -> None:
        from evennia_extensions.factories import AccountFactory, CharacterFactory
        from world.battles.resolution import select_surrounded_terminal_pool
        from world.battles.services import add_place, create_battle
        from world.vitals.factories import ensure_surrounded_content

        content = ensure_surrounded_content()
        battle = create_battle(name="Routing Test 2")
        attacker = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        defender = add_side(battle=battle, role=BattleSideRole.DEFENDER)
        place = add_place(battle=battle, name="The Gates")
        participant = enlist_participant(
            battle=battle, character_sheet=CharacterSheetFactory(), side=attacker, place=place
        )
        # A bare CharacterSheetFactory() character has db_account=None (NPC by
        # convention — see world/vitals/peril_resolution.py:is_pc_source); attach a
        # real account so this participant is classified as an opposing PC.
        pc_character = CharacterFactory()
        pc_character.db_account = AccountFactory()
        pc_character.save()
        enlist_participant(
            battle=battle,
            character_sheet=CharacterSheetFactory(character=pc_character),
            side=defender,
            place=place,
        )
        pool = select_surrounded_terminal_pool(battle=battle, participant=participant)
        assert pool == content["pools"]["surrounded_terminal_pvp"]


class EntryRollTests(TestCase):
    def setUp(self) -> None:
        self.content = ensure_surrounded_content()

    @tag("postgres")
    def test_isolated_failure_can_apply_surrounded(self) -> None:
        """With the check patched to force the Failure tier, an isolated STRIKE
        failure applies Surrounded via the entry pool's 'surrounded' row.

        PG-only (@tag("postgres")): this test exercises the real production
        _maybe_apply_surrounded -> apply_condition path, which routes through
        _build_bulk_context's PG-only DISTINCT ON query and errors on the SQLite
        fast tier (same known trap Task 3's regression test and Task 7's
        EscalationTickTests fixture route around — here the call is inside the
        code under test, so it can't be avoided). Verify via
        `just test-parity world.battles` or CI's Postgres shard, not
        `just test-fast`.
        """
        from world.battles.constants import BattleActionKind, BattleSideRole
        from world.battles.resolution import resolve_battle_round
        from world.battles.services import (
            add_place,
            add_side,
            add_unit,
            begin_battle_round,
            create_battle,
            declare_battle_action,
            enlist_participant,
        )
        from world.conditions.services import get_active_conditions

        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet)
        technique = TechniqueFactory(action_template=ActionTemplateFactory(), damage_profile=False)
        CharacterTechniqueFactory(character=sheet, technique=technique)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=30)

        battle = create_battle(name="Entry Roll Test")
        side = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        place = add_place(battle=battle, name="The Gates")
        unit = add_unit(battle=battle, side=side, name="Foes", unit_type="infantry")
        participant = enlist_participant(
            battle=battle, character_sheet=sheet, side=side, place=place
        )
        battle_round = begin_battle_round(battle=battle)
        declare_battle_action(
            participant=participant,
            action_kind=BattleActionKind.STRIKE,
            technique=technique,
            target_unit=unit,
        )

        # Two DISTINCT perform_check call sites are involved and must be patched
        # separately: (1) resolve_battle_technique's own STRIKE check (patched directly
        # by replacing resolve_battle_technique itself, same as the existing
        # test_resolution.py convention); (2) the entry roll's check, which runs through
        # select_consequence -> world.checks.consequence_resolution.perform_check (a
        # DIFFERENT imported name than world.battles.resolution.perform_check — patching
        # the wrong one silently no-ops the entry roll). Force the entry roll's outcome
        # tier to Failure so it lands in the pool's "surrounded" row.
        from world.traits.models import CheckOutcome

        failure_outcome = CheckOutcome.objects.get(name="Failure")
        entry_check_result = MagicMock(outcome=failure_outcome, success_level=-1)

        with (
            patch(
                "world.battles.resolution.resolve_battle_technique",
                return_value=_failure_result(-10),
            ),
            patch(
                "world.checks.consequence_resolution.perform_check",
                return_value=entry_check_result,
            ),
        ):
            resolve_battle_round(battle_round=battle_round)

        instance = get_active_conditions(
            sheet.character, condition=self.content["condition"]
        ).first()
        assert instance is not None
        assert instance.current_stage.stage_order == 1
