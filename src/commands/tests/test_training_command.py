"""Tests for CmdTrain (#2739) — dispatch wiring + bare meter listing.

Mirrors CmdTravel's test shape (commands/tests/test_travel_command.py):
overrides func() directly, so these tests drive func() and assert on
caller.msg / CommandError surfacing rather than going through
dispatch_player_action. The full training-session mechanics (check content,
outcome tiers, etc.) are covered by TrainTechniqueAction's own suite
(actions/tests/test_technique_training_action.py) — these tests cover only
name resolution, argument parsing, and dispatch wiring.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.types import ActionResult
from commands.training import CmdTrain
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import TechniqueFactory
from world.magic.models import TechniqueProgress
from world.roster.factories import RosterTenureFactory


class CmdTrainTestBase(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="TrainingRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.learner_sheet = CharacterSheetFactory()
        self.learner_sheet.character.location = self.room
        self.learner_sheet.character.save()
        self.caller = self.learner_sheet.character

    def _make_cmd(self, args):
        cmd = CmdTrain()
        cmd.caller = self.caller
        cmd.args = args
        cmd.raw_string = f"train {args}"
        return cmd


class CmdTrainBareListingTests(CmdTrainTestBase):
    def test_bare_train_no_meters_shows_hint(self):
        cmd = self._make_cmd("")
        with patch.object(self.caller, "msg") as mock_msg:
            cmd.func()
        mock_msg.assert_called_once()
        msg = mock_msg.call_args[0][0]
        self.assertIn("aren't training", msg.lower())

    def test_bare_train_lists_meter_self_study(self):
        technique = TechniqueFactory(name="Ember Lance")
        TechniqueProgress.objects.create(
            character_sheet=self.learner_sheet,
            technique=technique,
            total_required=50,
            points_accumulated=10,
            source="gift_acquisition",
        )

        cmd = self._make_cmd("")
        with patch.object(self.caller, "msg") as mock_msg:
            cmd.func()

        msg = mock_msg.call_args[0][0]
        self.assertIn("Ember Lance", msg)
        self.assertIn("10/50", msg)
        self.assertIn("teacher: -", msg)

    def test_bare_train_lists_meter_with_teacher_name(self):
        technique = TechniqueFactory(name="Ember Lance")
        teacher_tenure = RosterTenureFactory()
        TechniqueProgress.objects.create(
            character_sheet=self.learner_sheet,
            technique=technique,
            total_required=50,
            points_accumulated=5,
            source="teaching",
            teacher_tenure=teacher_tenure,
        )

        cmd = self._make_cmd("")
        with patch.object(self.caller, "msg") as mock_msg:
            cmd.func()

        msg = mock_msg.call_args[0][0]
        self.assertIn(teacher_tenure.character.key, msg)


class CmdTrainDispatchTests(CmdTrainTestBase):
    def test_unknown_technique_name_raises_message(self):
        cmd = self._make_cmd("Nonexistent Technique")
        with patch.object(self.caller, "msg") as mock_msg:
            cmd.func()
        mock_msg.assert_called_once()
        msg = mock_msg.call_args[0][0]
        self.assertIn("no technique called", msg.lower())

    def test_bare_equals_with_no_name_is_usage_error(self):
        cmd = self._make_cmd("=20")
        with patch.object(self.caller, "msg") as mock_msg:
            cmd.func()
        msg = mock_msg.call_args[0][0]
        self.assertIn("usage", msg.lower())

    def test_invalid_ap_amount_raises_message(self):
        TechniqueFactory(name="Ember Lance")
        cmd = self._make_cmd("Ember Lance=notanumber")
        with patch.object(self.caller, "msg") as mock_msg:
            cmd.func()
        msg = mock_msg.call_args[0][0]
        self.assertIn("not a valid ap amount", msg.lower())

    def test_resolves_technique_id_and_dispatches_with_default_ap(self):
        technique = TechniqueFactory(name="Ember Lance")
        cmd = self._make_cmd("Ember Lance")
        with (
            patch.object(self.caller, "msg"),
            patch(
                "commands.training.TrainTechniqueAction.run",
                return_value=ActionResult(success=True, message="ok"),
            ) as mock_run,
        ):
            cmd.func()
        mock_run.assert_called_once()
        _actor_args, called_kwargs = mock_run.call_args
        self.assertEqual(called_kwargs.get("technique_id"), technique.pk)
        self.assertNotIn("ap_to_invest", called_kwargs)

    def test_resolves_technique_id_and_ap_to_invest(self):
        technique = TechniqueFactory(name="Ember Lance")
        cmd = self._make_cmd("Ember Lance=15")
        with (
            patch.object(self.caller, "msg"),
            patch(
                "commands.training.TrainTechniqueAction.run",
                return_value=ActionResult(success=True, message="ok"),
            ) as mock_run,
        ):
            cmd.func()
        mock_run.assert_called_once()
        _actor_args, called_kwargs = mock_run.call_args
        self.assertEqual(called_kwargs.get("technique_id"), technique.pk)
        self.assertEqual(called_kwargs.get("ap_to_invest"), 15)

    def test_technique_name_matched_case_insensitively(self):
        technique = TechniqueFactory(name="Ember Lance")
        cmd = self._make_cmd("ember lance")
        with (
            patch.object(self.caller, "msg"),
            patch(
                "commands.training.TrainTechniqueAction.run",
                return_value=ActionResult(success=True, message="ok"),
            ) as mock_run,
        ):
            cmd.func()
        mock_run.assert_called_once()
        _actor_args, called_kwargs = mock_run.call_args
        self.assertEqual(called_kwargs.get("technique_id"), technique.pk)
