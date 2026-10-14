"""Telnet journey: calling on a being's favor (#4333 slice 1, walkthrough B).

Drives the real commands: ``invoke`` (what a character can call on and how hard),
``mission resolve <id> <n>/invoke <being>=<line>``, ``check <name> at <band>
/invoke <being>`` and ``persuade <character> /invoke <being>``. Rolls are pinned at
``world.checks.services.perform_check`` / the mission option's own check; the
rest is the service path the web uses. An onlooker's telnet session is checked
for exactly the room lines.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from actions.factories import ActionTemplateFactory
from commands.consent import CmdPersuade
from commands.missions import CmdMission
from commands.scene_checks import CmdCheck
from commands.tests.message_capture import message_text
from commands.worship import CmdInvoke
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.types import CheckResult
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionTemplateFactory,
)
from world.missions.services.run import staff_assign_mission
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.services import active_persona_for_sheet
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import FavorAwardKind
from world.worship.factories import (
    DevotionConfigFactory,
    DevotionStandingFactory,
    FavorOutcomeAwardFactory,
    WorshippedBeingFactory,
)
from world.worship.favor_services import ensure_being_modifier_targets
from world.worship.models import FavorInvocation, PatronageValence


def _run(command_class, caller, args: str):
    cmd = command_class()
    cmd.caller = caller
    cmd.args = args
    cmd.switches = []
    cmd.raw_string = f"{command_class.key} {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return cmd


def _said(caller) -> str:
    chunks: list[str] = []
    for call in caller.msg.call_args_list:
        chunks.extend(message_text(arg) for arg in call.args if isinstance(arg, (str, tuple)))
    return "\n".join(chunks)


def _result(check_type, outcome, total_points=0):
    return CheckResult(
        check_type=check_type,
        outcome=outcome,
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=total_points,
        aspect_bonus=0,
        total_points=total_points,
    )


class FavorInvocationTelnetTests(TestCase):
    def setUp(self) -> None:
        self.crit = CheckOutcomeFactory(name="Critical Success", success_level=2)
        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        self.partial = CheckOutcomeFactory(name="Partial Success", success_level=0)
        self.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        self.invocation_type = CheckTypeFactory(name="Invocation")
        config = DevotionConfigFactory(invocation_check_type=self.invocation_type)
        for outcome, amount in (
            (self.crit, 15),
            (self.success, 10),
            (self.partial, 5),
            (self.failure, 0),
        ):
            FavorOutcomeAwardFactory(
                config=config, kind=FavorAwardKind.INVOCATION, outcome_tier=outcome, amount=amount
            )
        self.ombrin = WorshippedBeingFactory(name="Ombrin")
        ensure_being_modifier_targets(self.ombrin)

        self.room = ObjectDBFactory(db_key="Shrine", db_typeclass_path="typeclasses.rooms.Room")
        self.scene = SceneFactory(location=self.room, is_active=True)
        self.ysmay = self._pc("Ysmay")
        self.hobb = self._pc("Hobb")
        DevotionStandingFactory(
            character_sheet=self.ysmay.sheet_data,
            being=self.ombrin,
            favor=44,
            valence=PatronageValence.DEVOTIONAL,
            established_at=timezone.now(),
        )

    def _pc(self, name):
        character = CharacterFactory(db_key=name, location=self.room)
        CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet__character=character)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        SceneParticipationFactory(scene=self.scene, account=tenure.player_data.account)
        return character

    def test_invoke_lists_difficulty_uses_and_bonuses(self) -> None:
        _run(CmdInvoke, self.ysmay, "")
        out = _said(self.ysmay)
        self.assertIn("Ombrin (favor 44): 30, Easy; 3 of 3 left this week", out)
        self.assertIn("Critical Success +15", out)
        self.assertIn("Failure: none", out)

        _run(CmdInvoke, self.ysmay, "omb")
        out = _said(self.ysmay)
        self.assertIn("Base: 75, Daunting", out)
        self.assertIn("You are Ombrin's Chosen: -30", out)
        self.assertIn("Favor 44 (30 or more): -15", out)

    def test_invoke_with_no_favor(self) -> None:
        _run(CmdInvoke, self.hobb, "")
        self.assertIn("no favor with any being", _said(self.hobb))

    def test_mission_resolve_with_invoke(self) -> None:
        template = MissionTemplateFactory(name="invoke-telnet")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        dest = MissionNodeFactory(template=template, key="dest")
        investigation = CheckTypeFactory(name="Investigation")
        option = MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=investigation,
            authored_ic_framing="[option label]",
        )
        MissionOptionRouteFactory(
            option=option,
            outcome_tier=self.success,
            target_node=dest,
            consequence=ConsequenceFactory(outcome_tier=self.success),
        )
        instance = staff_assign_mission(template, self.ysmay)

        _run(CmdMission, self.ysmay, f"beat {instance.pk}")
        self.assertIn("/invoke <being>[=<line>]", _said(self.ysmay))

        with (
            patch(
                "world.checks.services.perform_check_with_modifiers",
                return_value=_result(self.invocation_type, self.success),
            ),
            patch(
                "world.missions.services.resolution.perform_check",
                return_value=_result(investigation, self.success, total_points=58),
            ),
        ):
            _run(CmdMission, self.ysmay, f"resolve {instance.pk} 1/invoke Ombrin=[player line]")

        out = _said(self.ysmay)
        self.assertIn("Investigation: 48 + 10 Ombrin's favor (invocation: Success) = 58.", out)
        row = FavorInvocation.objects.get()
        self.assertEqual((row.mission_instance, row.player_line), (instance, "[player line]"))

    def test_mission_resolve_refusal(self) -> None:
        template = MissionTemplateFactory(name="refused")
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        MissionOptionFactory(
            node=entry,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=CheckTypeFactory(name="Search"),
        )
        instance = staff_assign_mission(template, self.hobb)
        _run(CmdMission, self.hobb, f"resolve {instance.pk} 1/invoke Ombrin")
        self.assertIn("You have no favor with Ombrin to call on.", _said(self.hobb))
        self.assertFalse(FavorInvocation.objects.exists())

    def test_check_with_invoke_reaches_onlooker_telnet(self) -> None:
        CheckTypeFactory(name="Perception")
        outcomes = iter([self.success, self.success])

        def _roll(_character, check_type, *_args, **_kwargs):
            return _result(check_type, next(outcomes))

        self.hobb.msg = MagicMock()
        with (
            patch("world.checks.services.perform_check", side_effect=_roll),
            patch(
                "world.scenes.interaction_services.non_web_sessions",
                side_effect=lambda obj: ["telnet"] if obj.pk == self.hobb.pk else [],
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            cmd = CmdCheck()
            cmd.caller = self.ysmay
            cmd.args = "Perception at hard /invoke Ombrin=[player line]"
            cmd.switches = []
            cmd.raw_string = f"check {cmd.args}"
            self.ysmay.msg = MagicMock()
            cmd.func()

        name = active_persona_for_sheet(self.ysmay.sheet_data).name
        heard = [str(call.args[0]) for call in self.hobb.msg.call_args_list if call.args]
        self.assertIn(f"{name} calls on Ombrin: [player line]", heard)
        self.assertIn(f"{name}'s invocation: Success.", heard)
        self.assertTrue(any("Perception" in line for line in heard))
        self.assertFalse(any("favor (invocation" in line or "+10" in line for line in heard))
        self.assertIn("Ombrin's favor (invocation: Success): +10", _said(self.ysmay))

    def test_persuade_declares_the_invocation(self) -> None:
        ActionTemplateFactory(name="Persuade", check_type=CheckTypeFactory(name="Persuasion"))
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache
        _run(CmdPersuade, self.ysmay, "Hobb /invoke Ombrin=[player line]")

        request = SceneActionRequest.objects.get()
        self.assertEqual(
            (request.invoke_being, request.invoke_line), (self.ombrin, "[player line]")
        )
        self.assertFalse(FavorInvocation.objects.exists())
