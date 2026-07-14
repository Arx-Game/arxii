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
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
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
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
from world.military.factories import MilitaryUnitFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneParticipationFactory


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
            military_unit=MilitaryUnitFactory(name="Iron Guard"),
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

    def test_declare_rout_creates_declaration(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare rout Iron Guard with Lance Thrust")

        self.assertTrue(
            BattleActionDeclaration.objects.filter(
                battle_round=self.battle_round,
                participant=self.participant,
                action_kind=BattleActionKind.ROUT,
                target_unit=self.unit,
            ).exists()
        )

    def test_declare_rally_targets_own_routed_unit(self) -> None:
        from world.battles.constants import BattleUnitStatus

        own_unit = BattleUnitFactory(
            battle=self.battle,
            side=self.defender_side,
            military_unit=MilitaryUnitFactory(name="Broken Wing", morale=5),
            status=BattleUnitStatus.ROUTED,
        )
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare rally Broken Wing with Lance Thrust")

        self.assertTrue(
            BattleActionDeclaration.objects.filter(
                battle_round=self.battle_round,
                participant=self.participant,
                action_kind=BattleActionKind.RALLY,
                target_unit=own_unit,
            ).exists()
        )

    def test_declare_rally_rejects_enemy_side_unit_by_name(self) -> None:
        """_resolve_own_unit only matches units on the participant's own side —
        the attacker's `Iron Guard` unit must not be rally-able by the defender."""
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare rally Iron Guard with Lance Thrust")

        self.assertFalse(
            BattleActionDeclaration.objects.filter(battle_round=self.battle_round).exists()
        )
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("Iron Guard", feedback)

    def test_declare_repel_place_creates_declaration(self) -> None:
        place = BattlePlaceFactory(battle=self.battle, name="South Wall")
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.defender_side.covenant = covenant
        self.defender_side.save(update_fields=["covenant"])
        rank = CovenantRankFactory(covenant=covenant)
        subordinate_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="cmd-test-repel-subordinate",
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
        _run(cmd, self.player_char, "declare repel place South Wall with Lance Thrust")

        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.action_kind, BattleActionKind.REPEL)
        self.assertEqual(decl.scope, BattleActionScope.PLACE)
        self.assertEqual(decl.target_place_id, place.pk)

    def test_declare_hold_without_place_scope_sends_usage(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare hold Iron Guard with Lance Thrust")

        self.assertFalse(
            BattleActionDeclaration.objects.filter(battle_round=self.battle_round).exists()
        )
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("Usage", feedback)

    def test_declare_fortify_creates_declaration(self) -> None:
        from world.battles.factories import FortificationFactory

        place = BattlePlaceFactory(battle=self.battle, name="East Wall")
        fort = FortificationFactory(place=place, defending_side=self.defender_side, kind="wall")

        cmd = CmdBattle()
        _run(
            cmd,
            self.player_char,
            "declare fortify place East Wall fortification wall with Lance Thrust",
        )

        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.action_kind, BattleActionKind.FORTIFY)
        self.assertEqual(decl.target_fortification_id, fort.pk)

    def test_declare_breach_creates_declaration(self) -> None:
        from world.battles.factories import FortificationFactory

        place = BattlePlaceFactory(battle=self.battle, name="Siege Gate")
        # BREACH targets the enemy's structure — attacker_side, not the
        # defender participant's own side (#1713 ownership check).
        fort = FortificationFactory(place=place, defending_side=self.attacker_side, kind="gate")

        cmd = CmdBattle()
        _run(
            cmd,
            self.player_char,
            "declare breach place Siege Gate fortification gate with Lance Thrust",
        )

        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.action_kind, BattleActionKind.BREACH)
        self.assertEqual(decl.target_fortification_id, fort.pk)

    def test_declare_breach_without_fortification_token_sends_usage(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare breach place East Wall with Lance Thrust")

        self.assertFalse(
            BattleActionDeclaration.objects.filter(battle_round=self.battle_round).exists()
        )
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("Usage", feedback)

    def test_declare_breach_unknown_fortification_sends_error(self) -> None:
        BattlePlaceFactory(battle=self.battle, name="Empty Yard")

        cmd = CmdBattle()
        _run(
            cmd,
            self.player_char,
            "declare breach place Empty Yard fortification wall with Lance Thrust",
        )

        self.assertFalse(
            BattleActionDeclaration.objects.filter(battle_round=self.battle_round).exists()
        )
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("wall", feedback.lower())

    def test_declare_move_self_creates_declaration(self) -> None:
        place = BattlePlaceFactory(battle=self.battle, name="The Ford")
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare move The Ford with Lance Thrust")

        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.action_kind, BattleActionKind.MOVE)
        self.assertEqual(decl.scope, BattleActionScope.UNIT)
        self.assertEqual(decl.target_place_id, place.pk)

    def test_declare_move_withdraw_creates_declaration(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare move withdraw with Lance Thrust")

        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.action_kind, BattleActionKind.MOVE)
        self.assertIsNone(decl.target_place)

    def test_declare_move_commander_order_creates_declaration(self) -> None:
        place = BattlePlaceFactory(battle=self.battle, name="The Ford")
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.defender_side.covenant = covenant
        self.defender_side.save(update_fields=["covenant"])
        rank = CovenantRankFactory(covenant=covenant)
        subordinate_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="cmd-test-move-subordinate",
        )
        membership = CharacterCovenantRole.objects.create(
            character_sheet=self.player_sheet,
            covenant_role=subordinate_role,
            covenant=covenant,
            rank=rank,
            engaged=False,
        )
        set_engaged_membership(membership=membership)
        own_unit = BattleUnitFactory(
            battle=self.battle,
            side=self.defender_side,
            military_unit=MilitaryUnitFactory(name="Own Guard"),
        )

        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare move Own Guard to The Ford with Lance Thrust")

        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.action_kind, BattleActionKind.MOVE)
        self.assertEqual(decl.scope, BattleActionScope.PLACE)
        self.assertEqual(decl.target_unit_id, own_unit.pk)
        self.assertEqual(decl.target_place_id, place.pk)

    def test_declare_reposition_creates_declaration(self) -> None:
        from decimal import Decimal

        from world.battles.constants import VehicleKind
        from world.battles.services import create_battle_vehicle

        vehicle = create_battle_vehicle(
            battle=self.battle,
            side=self.defender_side,
            place_name="The Gull",
            vehicle_kind=VehicleKind.SHIP,
        )
        vehicle.unit.military_unit.commander = self.player_sheet
        vehicle.unit.military_unit.save(update_fields=["commander"])

        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare reposition The Gull 10 5 with Lance Thrust")

        decl = BattleActionDeclaration.objects.get(
            battle_round=self.battle_round, participant=self.participant
        )
        self.assertEqual(decl.action_kind, BattleActionKind.REPOSITION)
        self.assertEqual(decl.reposition_dx, Decimal(10))
        self.assertEqual(decl.reposition_dy, Decimal(5))

    def test_declare_move_unknown_place_sends_error(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.player_char, "declare move Nowhere with Lance Thrust")

        self.assertFalse(
            BattleActionDeclaration.objects.filter(battle_round=self.battle_round).exists()
        )
        self.player_char.msg.assert_called()
        feedback = self.player_char.msg.call_args[0][0]
        self.assertIn("Nowhere", feedback)


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


class CmdBattleEncounterTests(TestCase):
    """CmdBattle `encounter open`/`join`/`encounters` subverbs (#2008)."""

    def setUp(self) -> None:
        self.room = _make_room("CmdBattleEncounterRoom")
        self.char1 = CharacterFactory(db_key="cmd_encounter_player", location=self.room)
        self.player_sheet = CharacterSheetFactory(character=self.char1)

        self.account = AccountFactory(username="cmd_encounter_gm")
        roster_entry = RosterEntryFactory(character_sheet=self.player_sheet)
        RosterTenureFactory(
            roster_entry=roster_entry,
            player_data__account=self.account,
            end_date=None,
        )
        # JUNIOR GM trust clears MinimumGMLevelPrerequisite on
        # OpenPlaceEncounterAction (mirrors OpenPlaceEncounterActionTests' fixture, Task 4).
        GMProfileFactory(account=self.account, level=GMLevel.JUNIOR)

        self.battle = BattleFactory(name="Encounter Cmd Test Battle")
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])
        # Scene-GM standing so _actor_may_gm_battle recognizes this account as
        # this battle's own GM -- same mechanism as Task 4, applied telnet-level.
        SceneParticipationFactory(scene=self.battle.scene, account=self.account, is_gm=True)

        self.side = BattleSideFactory(battle=self.battle, role="defender")
        self.place = BattlePlaceFactory(battle=self.battle, name="The Main Gates")
        self.participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.side,
            character_sheet=self.player_sheet,
        )

    def test_encounter_open_subverb_opens_place_encounter(self) -> None:
        from world.battles.models import BattlePlace

        cmd = CmdBattle()
        _run(cmd, self.char1, f"encounter open {self.place.name}")

        place = BattlePlace.objects.get(pk=self.place.pk)
        self.assertIsNotNone(place.combat_encounter_id)

    def test_encounter_open_missing_open_token_is_usage_error(self) -> None:
        cmd = CmdBattle()
        _run(cmd, self.char1, f"encounter {self.place.name}")

        self.char1.msg.assert_called()
        feedback = self.char1.msg.call_args[0][0]
        self.assertEqual(feedback, "Usage: battle encounter open <front>")

    def test_join_subverb_joins_open_encounter(self) -> None:
        from world.battles.services import open_place_encounter

        open_place_encounter(battle_place=self.place)
        self.participant.place = self.place
        self.participant.save(update_fields=["place"])

        cmd = CmdBattle()
        _run(cmd, self.char1, f"join {self.place.name}")

        from world.combat.models import CombatParticipant

        self.assertTrue(
            CombatParticipant.objects.filter(
                encounter=self.place.combat_encounter,
                character_sheet=self.participant.character_sheet,
            ).exists()
        )

    def test_encounters_subverb_lists_open_front_fights(self) -> None:
        from world.battles.services import open_place_encounter

        open_place_encounter(battle_place=self.place)

        cmd = CmdBattle()
        _run(cmd, self.char1, "encounters")

        self.char1.msg.assert_called()
        feedback = self.char1.msg.call_args[0][0]
        self.assertIn(self.place.name, feedback)
