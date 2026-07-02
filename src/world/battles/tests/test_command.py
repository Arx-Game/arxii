"""Tests for CmdBattle (#1592).

Drives the ``battle declare strike <unit>`` subverb through the MagicMock
command harness (patterns doc §"Testing"): instantiate CmdBattle, set
``cmd.caller``, ``cmd.args``, call ``cmd.func()``, assert DB state and
telnet feedback.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from commands.battle import CmdBattle
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.battles.constants import BattleActionKind, BattleActionScope
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleRoundFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.battles.models import BattleActionDeclaration
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CommandTier, CovenantType
from world.covenants.factories import CovenantFactory, CovenantRankFactory, CovenantRoleFactory
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import set_engaged_membership
from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
from world.scenes.constants import RoundStatus


def _make_room(label: str = "CmdBattleRoom") -> object:
    return ObjectDBFactory(
        db_key=label,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _run(cmd: CmdBattle, caller: object, args: str) -> None:
    """Drive ``cmd.func()`` with the given *caller* and *args*."""
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"battle {args}".strip()
    caller.msg = MagicMock()
    cmd.func()


class CmdBattleDeclareTests(TestCase):
    """CmdBattle declare strike / declare support integration tests."""

    def setUp(self) -> None:
        self.room = _make_room()

        # Player character with a CharacterSheet.
        self.player_char = CharacterFactory(db_key="cmd_battle_player", location=self.room)
        self.player_sheet = CharacterSheetFactory(character=self.player_char)

        # Battle in the room.
        self.battle = BattleFactory(name="Cmd Test Battle")
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])

        # Two sides.
        self.attacker_side = BattleSideFactory(battle=self.battle, role="attacker")
        self.defender_side = BattleSideFactory(battle=self.battle, role="defender")

        # Unit on attacker side (strike target).
        self.unit = BattleUnitFactory(
            battle=self.battle,
            side=self.attacker_side,
            name="Iron Guard",
        )

        # Enlist player on defender side.
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

        # A technique the player knows, with a real action_template (declare_battle_action
        # requires action_template_id presence — see TechniqueNotBattleReadyError).
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), name="Lance Thrust"
        )
        CharacterTechniqueFactory(character=self.player_sheet, technique=self.technique)

    def test_declare_strike_creates_declaration(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare strike Iron Guard with Lance Thrust")

        self.assertTrue(
            BattleActionDeclaration.objects.filter(
                battle_round=self.battle_round,
                participant=self.participant,
                action_kind=BattleActionKind.STRIKE,
                technique=self.technique,
                target_unit=self.unit,
            ).exists()
        )

        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("declare", feedback.lower())

    def test_declare_support_creates_declaration(self) -> None:
        ally_char = CharacterFactory(db_key="cmd_battle_ally", location=self.room)
        ally_sheet = CharacterSheetFactory(character=ally_char)
        ally_participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=ally_sheet,
        )

        cmd = CmdBattle()
        _run(cmd, self.player_char, f"declare support {ally_char.db_key} with Lance Thrust")

        self.assertTrue(
            BattleActionDeclaration.objects.filter(
                battle_round=self.battle_round,
                participant=self.participant,
                action_kind=BattleActionKind.SUPPORT,
                technique=self.technique,
                target_ally=ally_participant,
            ).exists()
        )

    def test_declare_without_technique_sends_usage(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare strike Iron Guard")
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("with", feedback.lower())

    def test_declare_unknown_technique_sends_error(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare strike Iron Guard with Nonexistent Technique")
        self.assertFalse(
            BattleActionDeclaration.objects.filter(battle_round=self.battle_round).exists()
        )
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("technique", feedback.lower())

    def test_declare_unknown_unit_sends_error(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare strike NonexistentUnit with Lance Thrust")

        # No declaration should have been created.
        self.assertFalse(
            BattleActionDeclaration.objects.filter(battle_round=self.battle_round).exists()
        )
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        # Should contain an error mentioning the missing unit.
        self.assertIn("NonexistentUnit", feedback)

    def test_declare_rescue_dispatches_rescue_action_kind(self) -> None:
        ally_char = CharacterFactory(db_key="cmd_battle_rescue_ally", location=self.room)
        ally_sheet = CharacterSheetFactory(character=ally_char)
        ally_participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.defender_side,
            character_sheet=ally_sheet,
        )

        cmd = CmdBattle()
        _run(cmd, self.player_char, f"declare rescue {ally_char.db_key} with Lance Thrust")

        self.assertTrue(
            BattleActionDeclaration.objects.filter(
                battle_round=self.battle_round,
                participant=self.participant,
                action_kind=BattleActionKind.RESCUE,
                technique=self.technique,
                target_ally=ally_participant,
            ).exists()
        )

    def test_bare_battle_shows_status(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "")
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("Cmd Test Battle", feedback)

    def test_declare_without_kind_sends_usage(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare")
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("Usage", feedback)

    def test_unknown_subverb_sends_error(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "flurgle")
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("Usage", feedback)

    def test_declare_strike_side_scope_dispatches_side_target(self) -> None:
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.defender_side.covenant = covenant
        self.defender_side.save(update_fields=["covenant"])
        rank = CovenantRankFactory(covenant=covenant)
        supreme_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUPREME,
            slug="cmd-test-supreme",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.player_sheet,
            covenant_role=supreme_role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)

        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare strike side with Lance Thrust")

        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.scope, BattleActionScope.SIDE)
        # The player is on defender_side — "strike side" must target the OPPOSING
        # side (attacker_side), never the caster's own side (#1710 friendly-fire fix).
        self.assertEqual(decl.target_side_id, self.attacker_side.pk)

    def test_declare_strike_place_scope_dispatches_place_target(self) -> None:
        place = BattlePlaceFactory(battle=self.battle, name="North Ridge")
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.defender_side.covenant = covenant
        self.defender_side.save(update_fields=["covenant"])
        rank = CovenantRankFactory(covenant=covenant)
        subordinate_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="cmd-test-subordinate",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.player_sheet,
            covenant_role=subordinate_role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)

        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare strike place North Ridge with Lance Thrust")

        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.scope, BattleActionScope.PLACE)
        self.assertEqual(decl.target_place_id, place.pk)


class CmdBattleDuelTests(TestCase):
    """CmdBattle `duel` subverb dispatches ChallengeChampionDuelAction."""

    def setUp(self) -> None:
        self.room = _make_room("CmdBattleDuelRoom")
        self.player_char = CharacterFactory(db_key="cmd_duel_player", location=self.room)
        self.player_sheet = CharacterSheetFactory(character=self.player_char)

        self.battle = BattleFactory(name="Duel Cmd Test Battle")
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])

        self.covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.defender_side = BattleSideFactory(
            battle=self.battle, role="defender", covenant=self.covenant
        )
        self.place = BattlePlaceFactory(battle=self.battle, name="The Main Gates")
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
            slug="cmd-test-champion",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.player_sheet,
            covenant_role=champion_role,
            covenant=self.covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)

    def test_duel_subverb_challenges_champion_duel(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "duel The Main Gates vs Warlord's Champion")

        self.place.refresh_from_db()
        self.assertIsNotNone(self.place.combat_encounter_id)
