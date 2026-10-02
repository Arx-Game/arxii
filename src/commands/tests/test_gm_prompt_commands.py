"""Telnet GMs see prompts and narrate with emit/pemit linked to the event (#4101)."""

from unittest import mock

from django.test import TestCase

from commands.evennia_overrides.communication import CmdEmit, CmdPemit
from commands.gm_ops import CmdGMDashboard
from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptKind, GMPromptStatus
from world.gm.factories import GMProfileFactory, GMPromptFactory
from world.gm.models import GMPromptNarration
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.scenes.models import Interaction


class GMPromptTelnetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gm = AccountFactory()
        GMProfileFactory(account=cls.gm)
        cls.scene = SceneFactory()
        SceneGMParticipationFactory(scene=cls.scene, account=cls.gm)
        cls.crosser = CharacterSheetFactory()
        cls.gm_sheet = CharacterSheetFactory()
        cls.gm_char = cls.gm_sheet.character
        # PemitAction's MinimumGMLevelPrerequisite reads actor.active_account, which
        # resolves through a live roster tenure -- NOT the plain .account attribute
        # set in setUp() below (that idiom only covers code reading actor.account
        # directly, e.g. narration_prompt_for). Mirrors
        # world/gm/tests/test_prompt_narration.py's PromptNarrationTest.
        entry = RosterEntryFactory(character_sheet=cls.gm_sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=cls.gm),
            end_date=None,
        )

    def setUp(self):
        self.gm_char.account = self.gm
        self.prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
            private_text="vision",
            room_text="room line",
        )
        patcher = mock.patch("world.gm.prompt_services.get_active_scene", return_value=self.scene)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, cmd_cls, args, switches=()):
        cmd = cmd_cls()
        cmd.caller = self.gm_char
        cmd.account = self.gm
        cmd.args = args
        cmd.switches = list(switches)
        cmd.cmdname = cmd_cls.key
        cmd.msg = mock.Mock()
        cmd.func()
        return cmd

    def test_emit_prompt_links(self):
        self._run(CmdEmit, f"{self.prompt.pk} The floor groans.", switches=["prompt"])
        link = GMPromptNarration.objects.get(prompt=self.prompt)
        self.assertEqual(link.interaction.content, "The floor groans.")

    def test_pemit_prompt_links(self):
        with mock.patch.object(self.gm_char, "search", return_value=self.crosser.character):
            self._run(CmdPemit, f"{self.prompt.pk} Rowan=vision", switches=["prompt"])
        self.assertTrue(GMPromptNarration.objects.filter(prompt=self.prompt).exists())

    def test_gm_prompts_lists_mine(self):
        cmd = self._run(CmdGMDashboard, "prompts")
        text = " ".join(str(c.args[0]) for c in cmd.msg.call_args_list)
        self.assertIn(f"[{self.prompt.pk}]", text)
        self.assertIn("Crossing", text)
        self.assertIn("vision", text)

    def test_gm_prompts_marks_narrated(self):
        """R6-2: a NARRATED prompt still lists, marked as such."""
        self.prompt.status = GMPromptStatus.NARRATED
        self.prompt.save(update_fields=["status"])
        cmd = self._run(CmdGMDashboard, "prompts")
        text = " ".join(str(c.args[0]) for c in cmd.msg.call_args_list)
        self.assertIn(f"[{self.prompt.pk}]", text)
        self.assertIn("narrated", text.lower())

    def test_gm_prompt_send_sends_both_defaults_and_closes(self):
        """R12-1: send narrates both defaults, then closes the prompt itself --
        every line it sent is already covered, so no default is released twice."""
        self._run(CmdGMDashboard, f"prompt send {self.prompt.pk}")
        self.assertEqual(GMPromptNarration.objects.filter(prompt=self.prompt).count(), 2)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.DISMISSED)
        # Each authored default line went out exactly once in total -- closing
        # released nothing extra on top of the two linked narrations above.
        self.assertEqual(Interaction.objects.filter(content="vision").count(), 1)
        self.assertEqual(Interaction.objects.filter(content="room line").count(), 1)

    def test_gm_prompt_dismiss(self):
        with mock.patch("world.gm.prompt_services.narrate_privately"):
            self._run(CmdGMDashboard, f"prompt dismiss {self.prompt.pk}")
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.DISMISSED)

    def test_gm_prompt_done_closes_a_narrated_prompt(self):
        """R6-2: `gm prompt done <id>` is the same close action as dismiss."""
        self.prompt.status = GMPromptStatus.NARRATED
        self.prompt.save(update_fields=["status"])
        with mock.patch("world.gm.prompt_services.narrate_privately"):
            self._run(CmdGMDashboard, f"prompt done {self.prompt.pk}")
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.DISMISSED)

    def test_dashboard_count_includes_narrated(self):
        """R6-2: the dashboard's waiting count includes NARRATED prompts."""
        self.prompt.status = GMPromptStatus.NARRATED
        self.prompt.save(update_fields=["status"])
        cmd = self._run(CmdGMDashboard, "")
        text = " ".join(str(c.args[0]) for c in cmd.msg.call_args_list)
        self.assertIn("Narration prompts waiting: 1", text)
