"""Telnet: a GM decides standoff proposals and moves morale; onlookers read the summary.

#4354. ``gm prompt confirm|hold|override``, ``gm standoff shake|steady`` and ``standoff``
outside the encounter, against rows the test seeds itself.
"""

from unittest import mock

from django.test import TestCase

from commands.gm_ops import CmdGMDashboard
from commands.standoff import CmdStandoff
from evennia_extensions.factories import AccountFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import CauseKind, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.combat.morale import OpponentMoraleState, morale_state_for
from world.gm.constants import GMPromptStatus
from world.gm.models import GMPrompt
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.standoffs.constants import StandoffGroupState
from world.standoffs.factories import StandoffApproachFactory
from world.standoffs.models import StandoffConfig
from world.standoffs.services.state import open_standoff
from world.standoffs.services.verbs import standoff_press
from world.standoffs.tests.test_proposals import CHECK, LEVEL, forced

GROUP = "Gate Wardens"


class GMStandoffTelnetTests(TestCase):
    def setUp(self) -> None:
        seed_scaling_defaults()
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.gm = AccountFactory()
        self.scene = SceneFactory(location=RoomProfileFactory(objectdb=self.room))
        SceneParticipationFactory(scene=self.scene, account=self.gm, is_gm=True)
        self.gm_char = CharacterSheetFactory().character
        self.gm_char.location = self.room
        self.gm_char.account = self.gm
        self.encounter = CombatEncounterFactory(scene=self.scene, room=self.room)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.template = CreatureTemplateFactory(
            name=GROUP, tier=OpponentTier.MOOK, cause=CauseKind.ORDERS
        )
        self.members = [
            CombatOpponentFactory(
                encounter=self.encounter, creature_template=self.template, morale=80
            )
            for _ in range(2)
        ]
        config = StandoffConfig.load()
        config.read_check_type = CheckTypeFactory()
        config.save()
        level = mock.patch(LEVEL, return_value=100)
        level.start()
        self.addCleanup(level.stop)
        self.group = open_standoff(self.encounter)[0]

    def _run(self, cmd_cls, args: str, caller=None) -> str:
        cmd = cmd_cls()
        cmd.caller = caller or self.gm_char
        cmd.account = self.gm
        cmd.args = args
        cmd.switches = []
        cmd.cmdname = cmd_cls.key
        cmd.raw_string = f"{cmd_cls.key} {args}"
        cmd.msg = mock.Mock()
        cmd.func()
        return "\n".join(str(c.args[0]) for c in cmd.msg.call_args_list)

    def _propose(self) -> GMPrompt:
        with mock.patch(CHECK, return_value=forced(-2)):
            standoff_press(self.participant, self.group, StandoffApproachFactory())
        return GMPrompt.objects.get(standoff_group=self.group)

    def test_gm_prompts_lists_the_proposal_with_its_verbs(self) -> None:
        prompt = self._propose()
        with mock.patch("world.gm.prompt_services.get_active_scene", return_value=self.scene):
            text = self._run(CmdGMDashboard, "prompts")
        self.assertIn(f"[{prompt.pk}] Standoff: {GROUP}", text)
        self.assertIn(f"{GROUP}: cause fires. Cause: Orders.", text)
        self.assertIn(f"gm prompt hold {prompt.pk}", text)

    def test_hold_override_and_confirm(self) -> None:
        prompt = self._propose()
        text = self._run(CmdGMDashboard, f"prompt hold {prompt.pk}")
        self.assertIn("Held for one action.", text)
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)

        prompt = self._second_proposal()
        text = self._run(CmdGMDashboard, f"prompt override {prompt.pk}")
        self.assertIn("Give a reason", text)
        self._run(CmdGMDashboard, f"prompt override {prompt.pk} PLACEHOLDER reason")
        prompt.refresh_from_db()
        self.assertEqual(prompt.resolution_note, "Overridden: PLACEHOLDER reason")

        prompt = self._second_proposal()
        self._run(CmdGMDashboard, f"prompt confirm {prompt.pk}")
        prompt.refresh_from_db()
        self.group.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.CONFIRMED)
        self.assertEqual(self.group.state, StandoffGroupState.FIGHTING)

    def _second_proposal(self) -> GMPrompt:
        with mock.patch(CHECK, return_value=forced(-2)):
            standoff_press(self.participant, self.group, StandoffApproachFactory())
        return GMPrompt.objects.get(standoff_group=self.group, status=GMPromptStatus.PENDING)

    def test_gm_standoff_shake_by_name(self) -> None:
        with mock.patch("actions.definitions.gm_standoff._announce"):
            text = self._run(CmdGMDashboard, f"standoff shake {GROUP} PLACEHOLDER reason")
        self.assertEqual(text, f"{GROUP} falters.")
        for member in self.members:
            member.refresh_from_db()
            self.assertEqual(morale_state_for(member), OpponentMoraleState.FALTER)

    def test_gm_standoff_needs_a_reason(self) -> None:
        text = self._run(CmdGMDashboard, "standoff shake")
        self.assertIn("Usage: gm standoff", text)

    def test_standoff_shows_the_gm_view_to_the_gm(self) -> None:
        text = self._run(CmdStandoff, "")
        self.assertIn("(GM)", text)
        self.assertIn("Cause: Orders (holds)", text)
        # "|" starts a telnet colour code, so the GM hint carries none.
        self.assertIn("gm standoff shake <group id> <reason> (or steady)", text)

    def test_standoff_shows_the_public_summary_to_an_onlooker(self) -> None:
        onlooker = CharacterSheetFactory().character
        onlooker.location = self.room
        onlooker.account = AccountFactory()
        text = self._run(CmdStandoff, "", caller=onlooker)
        self.assertIn(f"{GROUP} (2) - Open", text)
        self.assertNotIn("Orders", text)
