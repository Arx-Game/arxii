"""Tests for BattleActionKind.MOVE (#2007): declaration validation, resolution,
and multi-round transit journeys."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.battles.constants import (
    MOVE_COST_DIFFICULTY_PER_POINT,
    BattleActionKind,
    BattleActionScope,
    BattleParticipantStatus,
    BattleUnitStatus,
)
from world.battles.exceptions import (
    InsufficientCommandTierError,
    InvalidMoveScopeError,
    MissingScopeTargetError,
    MoveOrderRequiresTargetUnitError,
)
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.battles.resolution import resolve_battle_round
from world.battles.services import begin_battle_round, declare_battle_action
from world.conditions.constants import FoundationalCapability
from world.conditions.factories import CapabilityTypeFactory
from world.covenants.constants import CommandTier, CovenantType
from world.covenants.factories import CovenantFactory, CovenantRankFactory, CovenantRoleFactory
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import set_engaged_membership
from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory, TechniqueFactory


def _mock_check(success_level: int) -> MagicMock:
    """Mirrors test_siege.py's _mock_check exactly."""
    result = MagicMock()
    result.success_level = success_level
    return result


class MoveDeclarationTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(round_limit=10)
        self.side = BattleSideFactory(battle=self.battle, role="attacker")
        self.place = BattlePlaceFactory(battle=self.battle, name="The Ford")
        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        self.participant = BattleParticipantFactory(battle=self.battle, side=self.side)
        CharacterTechniqueFactory(
            character=self.participant.character_sheet, technique=self.technique
        )
        CharacterAnimaFactory(
            character=self.participant.character_sheet.character, current=30, maximum=30
        )

    def test_self_move_requires_no_command_tier(self) -> None:
        begin_battle_round(battle=self.battle)
        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.MOVE,
            technique=self.technique,
            target_place=self.place,
        )
        self.assertEqual(declaration.action_kind, BattleActionKind.MOVE)
        self.assertEqual(declaration.scope, BattleActionScope.UNIT)
        self.assertEqual(declaration.target_place_id, self.place.pk)

    def test_self_move_withdraw_allows_null_target_place(self) -> None:
        begin_battle_round(battle=self.battle)
        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.MOVE,
            technique=self.technique,
            target_place=None,
        )
        self.assertEqual(declaration.action_kind, BattleActionKind.MOVE)
        self.assertIsNone(declaration.target_place)

    def test_move_side_scope_rejected(self) -> None:
        begin_battle_round(battle=self.battle)
        with self.assertRaises(InvalidMoveScopeError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.MOVE,
                technique=self.technique,
                scope=BattleActionScope.SIDE,
                target_place=self.place,
            )

    def test_move_place_scope_requires_target_place(self) -> None:
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.side.covenant = covenant
        self.side.save(update_fields=["covenant"])
        rank = CovenantRankFactory(covenant=covenant)
        subordinate_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="move-test-no-target-place-subordinate",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.participant.character_sheet,
            covenant_role=subordinate_role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)
        begin_battle_round(battle=self.battle)
        unit = BattleUnitFactory(battle=self.battle, side=self.side)
        with self.assertRaises(MissingScopeTargetError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.MOVE,
                technique=self.technique,
                scope=BattleActionScope.PLACE,
                target_unit=unit,
                target_place=None,
            )

    def test_move_place_scope_requires_target_unit(self) -> None:
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.side.covenant = covenant
        self.side.save(update_fields=["covenant"])
        rank = CovenantRankFactory(covenant=covenant)
        subordinate_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="move-test-no-target-unit-subordinate",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.participant.character_sheet,
            covenant_role=subordinate_role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)
        begin_battle_round(battle=self.battle)
        with self.assertRaises(MoveOrderRequiresTargetUnitError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.MOVE,
                technique=self.technique,
                scope=BattleActionScope.PLACE,
                target_place=self.place,
            )

    def test_move_place_scope_requires_command_tier(self) -> None:
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.side.covenant = covenant
        self.side.save(update_fields=["covenant"])
        begin_battle_round(battle=self.battle)
        unit = BattleUnitFactory(battle=self.battle, side=self.side)
        with self.assertRaises(InsufficientCommandTierError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.MOVE,
                technique=self.technique,
                scope=BattleActionScope.PLACE,
                target_unit=unit,
                target_place=self.place,
            )

    def test_commander_can_order_unit_move(self) -> None:
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.side.covenant = covenant
        self.side.save(update_fields=["covenant"])
        rank = CovenantRankFactory(covenant=covenant)
        subordinate_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="move-test-subordinate",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.participant.character_sheet,
            covenant_role=subordinate_role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)
        unit = BattleUnitFactory(battle=self.battle, side=self.side)
        begin_battle_round(battle=self.battle)

        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.MOVE,
            technique=self.technique,
            scope=BattleActionScope.PLACE,
            target_unit=unit,
            target_place=self.place,
        )
        self.assertEqual(declaration.target_unit_id, unit.pk)
        self.assertEqual(declaration.target_place_id, self.place.pk)


class MoveResolutionTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(round_limit=10)
        self.side = BattleSideFactory(battle=self.battle, role="attacker")
        self.origin = BattlePlaceFactory(battle=self.battle, name="Origin", x=0, y=0)
        self.destination = BattlePlaceFactory(battle=self.battle, name="Destination", x=3, y=4)
        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        self.participant = BattleParticipantFactory(
            battle=self.battle, side=self.side, place=self.origin
        )
        CharacterTechniqueFactory(
            character=self.participant.character_sheet, technique=self.technique
        )
        CharacterAnimaFactory(
            character=self.participant.character_sheet.character, current=30, maximum=30
        )
        self.movement = CapabilityTypeFactory(
            name=FoundationalCapability.MOVEMENT, innate_baseline=10
        )

    def test_self_move_arrives_in_one_round_when_within_capability(self) -> None:
        # Origin (0,0) -> Destination (3,4): distance 5, well within baseline 10.
        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.MOVE,
            technique=self.technique,
            target_place=self.destination,
        )
        with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
            resolve_battle_round(battle_round=battle_round)

        self.participant.refresh_from_db()
        self.assertEqual(self.participant.place_id, self.destination.pk)
        self.assertIsNone(self.participant.transit_x)
        self.assertIsNone(self.participant.transit_y)
        self.assertIsNone(self.participant.transit_target_place)

    def test_self_move_spans_multiple_rounds_when_capability_bounded(self) -> None:
        # Shrink MOVEMENT so a distance-5 move can't complete in one round.
        self.movement.innate_baseline = 2
        self.movement.save(update_fields=["innate_baseline"])

        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.MOVE,
            technique=self.technique,
            target_place=self.destination,
        )
        with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
            resolve_battle_round(battle_round=battle_round)

        self.participant.refresh_from_db()
        # Still en route — hasn't arrived, place unchanged, transit fields advanced.
        self.assertEqual(self.participant.place_id, self.origin.pk)
        self.assertEqual(self.participant.transit_target_place_id, self.destination.pk)
        self.assertIsNotNone(self.participant.transit_x)
        self.assertIsNotNone(self.participant.transit_y)

        # Redeclare toward the same target — should keep progressing and
        # eventually arrive within a small, deterministic number of rounds.
        for _ in range(5):
            if self.participant.place_id == self.destination.pk:
                break
            battle_round = begin_battle_round(battle=self.battle)
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.MOVE,
                technique=self.technique,
                target_place=self.destination,
            )
            with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
                resolve_battle_round(battle_round=battle_round)
            self.participant.refresh_from_db()

        self.assertEqual(self.participant.place_id, self.destination.pk)
        self.assertIsNone(self.participant.transit_target_place)

    def test_withdraw_sets_status_and_clears_place(self) -> None:
        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.MOVE,
            technique=self.technique,
            target_place=None,
        )
        with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
            resolve_battle_round(battle_round=battle_round)

        self.participant.refresh_from_db()
        self.assertEqual(self.participant.status, BattleParticipantStatus.WITHDRAWN)
        self.assertIsNone(self.participant.place)
        self.assertIsNone(self.participant.transit_target_place)

    def test_movement_cost_measurably_changes_check_difficulty(self) -> None:
        self.destination.movement_cost = 4
        self.destination.save(update_fields=["movement_cost"])
        begin_battle_round(battle=self.battle)
        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.MOVE,
            technique=self.technique,
            target_place=self.destination,
        )

        from world.battles.resolution import BattleTechniqueResolver

        resolver = BattleTechniqueResolver(
            character=self.participant.character_sheet.character,
            technique=self.technique,
            declaration=declaration,
        )
        expected_penalty = -self.destination.movement_cost * MOVE_COST_DIFFICULTY_PER_POINT
        self.assertEqual(resolver._battle_modifier_stack(), expected_penalty)

    def test_routed_unit_can_declare_move(self) -> None:
        commander_side = self.side
        unit = BattleUnitFactory(
            battle=self.battle,
            side=commander_side,
            place=self.origin,
            status=BattleUnitStatus.ROUTED,
        )
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        commander_side.covenant = covenant
        commander_side.save(update_fields=["covenant"])
        rank = CovenantRankFactory(covenant=covenant)
        role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="move-test-routed-subordinate",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.participant.character_sheet,
            covenant_role=role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)
        from world.military.models import MilitaryUnitCapability

        MilitaryUnitCapability.objects.create(
            unit=unit.military_unit, capability=self.movement, value=10
        )

        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.MOVE,
            technique=self.technique,
            scope=BattleActionScope.PLACE,
            target_unit=unit,
            target_place=self.destination,
        )
        with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
            resolve_battle_round(battle_round=battle_round)

        unit.refresh_from_db()
        self.assertEqual(unit.place_id, self.destination.pk)
        self.assertEqual(unit.status, BattleUnitStatus.ROUTED)

    def test_surrounded_participant_can_declare_and_resolve_move(self) -> None:
        from world.conditions.constants import SURROUNDED_CONDITION_NAME
        from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory

        surrounded = ConditionTemplateFactory(name=SURROUNDED_CONDITION_NAME)
        ConditionInstanceFactory(
            target=self.participant.character_sheet.character,
            condition=surrounded,
        )

        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.MOVE,
            technique=self.technique,
            target_place=self.destination,
        )
        with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
            resolve_battle_round(battle_round=battle_round)

        self.participant.refresh_from_db()
        self.assertEqual(self.participant.place_id, self.destination.pk)
