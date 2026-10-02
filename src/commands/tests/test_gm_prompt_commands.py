"""Telnet GMs see prompts and narrate with emit/pemit linked to the event (#4101)."""

from unittest import mock

from django.test import TestCase

from commands.evennia_overrides.communication import CmdEmit, CmdPemit
from commands.gm_ops import CmdGMDashboard
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.constants import GMPromptKind, GMPromptStatus
from world.gm.factories import GMProfileFactory, GMPromptFactory
from world.gm.models import GMPromptNarration
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.scenes.models import Interaction


class GMPromptTelnetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gm = AccountFactory()
        GMProfileFactory(account=cls.gm)
        cls.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        cls.scene = SceneFactory(location=cls.room)
        SceneGMParticipationFactory(scene=cls.scene, account=cls.gm)
        cls.crosser = CharacterSheetFactory()
        # Fix round 1, finding 1: the private leg checks the subject is
        # physically present -- place them in the scene's own room so the
        # happy-path "both defaults sent" tests actually exercise that check
        # rather than vacuously skipping it.
        cls.crosser.character.location = cls.room
        cls.crosser.character.save()
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

    def test_gm_prompts_labels_rows_with_the_verbs_that_resolve_them(self):
        """#4101 final review, B7: a dramatic-moment row names the ``moment``
        verbs (``gm prompt dismiss`` does not resolve that kind); a narration
        row keeps its ``gm prompt`` verbs."""
        moment = GMPromptFactory(scene=self.scene)
        cmd = self._run(CmdGMDashboard, "prompts")
        text = " ".join(str(c.args[0]) for c in cmd.msg.call_args_list)
        self.assertIn(f"moment confirm {moment.pk} | moment dismiss {moment.pk}", text)
        self.assertIn(f"gm prompt send {self.prompt.pk}", text)
        self.assertNotIn(f"gm prompt dismiss {moment.pk}", text)

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
        every line it sent is already covered, so no default is released twice.

        Fix round 1: wrapped in ``captureOnCommitCallbacks`` so the close's own
        deferred release actually runs here -- without it, ``release_prompt_
        defaults`` never fires inside a plain ``TestCase``, and the "exactly
        once" assertion below would pass whether or not the dedup logic is
        correct at all.
        """
        with mock.patch("world.gm.prompt_services.narrate_privately") as narrate:
            with self.captureOnCommitCallbacks(execute=True):
                self._run(CmdGMDashboard, f"prompt send {self.prompt.pk}")
        self.assertEqual(GMPromptNarration.objects.filter(prompt=self.prompt).count(), 2)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.DISMISSED)
        # Each authored default line went out exactly once in total -- closing
        # released nothing extra on top of the two linked narrations above.
        self.assertEqual(Interaction.objects.filter(content="vision").count(), 1)
        self.assertEqual(Interaction.objects.filter(content="room line").count(), 1)
        narrate.assert_not_called()  # the close found both legs already covered

    def test_gm_prompt_send_retries_only_the_missing_leg(self):
        """R12-3: a re-run after a prior partial send narrates only the leg
        that isn't covered yet, read from the real coverage computation
        (``prompt_narration_coverage``), never re-derived."""
        from world.gm.prompt_services import link_prompt_narration
        from world.scenes.factories import InteractionFactory

        room_interaction = InteractionFactory(
            mode=InteractionMode.EMIT, content="room line", scene=self.scene
        )
        link_prompt_narration(self.prompt, room_interaction)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.NARRATED)

        with mock.patch("world.gm.prompt_services.narrate_privately") as narrate:
            with self.captureOnCommitCallbacks(execute=True):
                self._run(CmdGMDashboard, f"prompt send {self.prompt.pk}")

        # Only ONE additional narration (the private pemit) -- the already-
        # covered room leg must not be re-sent.
        self.assertEqual(GMPromptNarration.objects.filter(prompt=self.prompt).count(), 2)
        self.assertEqual(Interaction.objects.filter(content="room line").count(), 1)
        self.assertEqual(Interaction.objects.filter(content="vision").count(), 1)
        narrate.assert_not_called()  # nothing released on close -- both legs covered
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.DISMISSED)

    def test_gm_prompt_send_skips_blank_default(self):
        """A blank leg is skipped outright, never sent as an empty line."""
        prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
            private_text="only private",
            room_text="",
        )
        with mock.patch("world.gm.prompt_services.narrate_privately") as narrate:
            with self.captureOnCommitCallbacks(execute=True):
                self._run(CmdGMDashboard, f"prompt send {prompt.pk}")
        self.assertEqual(GMPromptNarration.objects.filter(prompt=prompt).count(), 1)
        self.assertTrue(
            GMPromptNarration.objects.filter(
                prompt=prompt, interaction__content="only private"
            ).exists()
        )
        narrate.assert_not_called()
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)

    def test_gm_prompt_send_skips_private_when_subject_absent(self):
        """Fix round 1, finding 1: an absent subject skips the private line and
        tells the GM; the room line still goes out regardless."""
        absent_sheet = CharacterSheetFactory()  # never placed in `self.room`
        prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=self.scene,
            character_sheet=absent_sheet,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
            private_text="vision",
            room_text="room line",
        )
        with mock.patch("world.gm.prompt_services.narrate_privately") as narrate:
            with self.captureOnCommitCallbacks(execute=True):
                cmd = self._run(CmdGMDashboard, f"prompt send {prompt.pk}")
        # Only the room leg narrated through the command -- the private leg
        # was skipped, not silently dropped.
        self.assertEqual(GMPromptNarration.objects.filter(prompt=prompt).count(), 1)
        self.assertTrue(
            GMPromptNarration.objects.filter(
                prompt=prompt, interaction__mode=InteractionMode.EMIT
            ).exists()
        )
        text = " ".join(str(c.args[0]) for c in cmd.msg.call_args_list)
        self.assertIn("isn't here", text)
        prompt.refresh_from_db()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)
        # The skip is not coverage -- closing still releases the uncovered
        # private default for real.
        narrate.assert_called_once_with(absent_sheet.character, "vision", scene=self.scene)

    def test_gm_prompt_send_addressed_to_another_gm_refuses(self):
        other_gm = AccountFactory()
        other_prompt = GMPromptFactory(
            kind=GMPromptKind.CROSSING,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=other_gm,
            moment_type=None,
            success_level=None,
            private_text="vision",
            room_text="room line",
        )
        cmd = self._run(CmdGMDashboard, f"prompt send {other_prompt.pk}")
        self.assertEqual(GMPromptNarration.objects.filter(prompt=other_prompt).count(), 0)
        text = " ".join(str(c.args[0]) for c in cmd.msg.call_args_list)
        # Fix round 1, minor 6: one neutral reply, same as an id that doesn't
        # exist at all -- never names "that prompt is addressed to someone else".
        self.assertIn("no such gm prompt", text.lower())

    def test_gm_prompt_send_no_active_scene_refuses(self):
        with mock.patch("world.gm.prompt_services.get_active_scene", return_value=None):
            cmd = self._run(CmdGMDashboard, f"prompt send {self.prompt.pk}")
        self.assertEqual(GMPromptNarration.objects.filter(prompt=self.prompt).count(), 0)
        text = " ".join(str(c.args[0]) for c in cmd.msg.call_args_list)
        self.assertIn("scene it happened in", text.lower())

    def test_gm_prompt_send_on_closed_prompt_refuses_nothing_sent(self):
        closed_prompt = GMPromptFactory(
            kind=GMPromptKind.MIRACLE,
            scene=self.scene,
            character_sheet=self.crosser,
            addressed_to=self.gm,
            moment_type=None,
            success_level=None,
            room_text="a wonder occurs",
        )
        with mock.patch("world.gm.prompt_services.narrate_privately"):
            with self.captureOnCommitCallbacks(execute=True):
                self._run(CmdGMDashboard, f"prompt dismiss {closed_prompt.pk}")
        closed_prompt.refresh_from_db()
        self.assertEqual(closed_prompt.status, GMPromptStatus.DISMISSED)
        interactions_before = Interaction.objects.count()

        cmd = self._run(CmdGMDashboard, f"prompt send {closed_prompt.pk}")

        self.assertEqual(GMPromptNarration.objects.filter(prompt=closed_prompt).count(), 0)
        self.assertEqual(Interaction.objects.count(), interactions_before)
        text = " ".join(str(c.args[0]) for c in cmd.msg.call_args_list)
        self.assertIn("already been dealt with", text)

    def test_gm_prompt_dismiss(self):
        with mock.patch("world.gm.prompt_services.narrate_privately") as narrate:
            with self.captureOnCommitCallbacks(execute=True):
                self._run(CmdGMDashboard, f"prompt dismiss {self.prompt.pk}")
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.DISMISSED)
        narrate.assert_called_once_with(self.crosser.character, "vision", scene=self.scene)
        self.assertTrue(Interaction.objects.filter(content="room line").exists())

    def test_gm_prompt_done_closes_a_narrated_prompt(self):
        """R6-2: `gm prompt done <id>` is the same close action as dismiss."""
        self.prompt.status = GMPromptStatus.NARRATED
        self.prompt.save(update_fields=["status"])
        with mock.patch("world.gm.prompt_services.narrate_privately") as narrate:
            with self.captureOnCommitCallbacks(execute=True):
                self._run(CmdGMDashboard, f"prompt done {self.prompt.pk}")
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.DISMISSED)
        narrate.assert_called_once_with(self.crosser.character, "vision", scene=self.scene)

    def test_dashboard_count_includes_narrated(self):
        """R6-2: the dashboard's waiting count includes NARRATED prompts."""
        self.prompt.status = GMPromptStatus.NARRATED
        self.prompt.save(update_fields=["status"])
        cmd = self._run(CmdGMDashboard, "")
        text = " ".join(str(c.args[0]) for c in cmd.msg.call_args_list)
        self.assertIn("Narration prompts waiting: 1", text)
