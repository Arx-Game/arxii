"""Tests for BattleActionKind.MOVE (#2007): declaration validation, resolution,
and multi-round transit journeys."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.battles.constants import (
    BattleActionKind,
    BattleActionScope,
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
from world.battles.services import begin_battle_round, declare_battle_action
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
