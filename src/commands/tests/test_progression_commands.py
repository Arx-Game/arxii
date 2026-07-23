"""Tests for the ``training`` and ``progression`` telnet commands (Task 5)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.progression import CmdProgressionUnlock, CmdTraining
from world.action_points.models import ActionPointConfig
from world.character_sheets.factories import CharacterSheetFactory
from world.progression.factories import ExperiencePointsDataFactory, XPTransactionFactory
from world.progression.models import ExperiencePointsData, XPTransaction
from world.progression.types import ProgressionReason
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.skills.factories import SkillFactory, SpecializationFactory
from world.skills.models import TrainingAllocation


def _make_training_cmd(caller, args=""):
    cmd = CmdTraining()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"training {args}".strip()
    cmd.cmdname = "training"
    return cmd


def _make_progression_cmd(caller, args=""):
    cmd = CmdProgressionUnlock()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"progression {args}".strip()
    cmd.cmdname = "progression"
    return cmd


class CmdTrainingListTests(TestCase):
    """Training listing renders allocations and weekly budget."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.skill = SkillFactory()
        cls.specialization = SpecializationFactory()
        cls.mentor = PersonaFactory()
        cls.weekly_regen = 80
        ActionPointConfig.objects.update_or_create(
            name="Default",
            defaults={"is_active": True, "weekly_regen": cls.weekly_regen},
        )

    def setUp(self):
        self.character.msg = MagicMock()

    def test_bare_list_shows_empty_budget(self):
        _make_training_cmd(self.character).func()
        sent = "".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("0/80 AP used", sent)
        self.assertIn("No training allocations", sent)

    def test_list_shows_allocations_and_remaining_budget(self):
        TrainingAllocation.objects.create(
            character=self.character.sheet_data,
            skill=self.skill,
            ap_amount=20,
            mentor=self.mentor,
        )
        TrainingAllocation.objects.create(
            character=self.character.sheet_data,
            specialization=self.specialization,
            ap_amount=15,
        )
        _make_training_cmd(self.character).func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("35/80 AP used", sent)
        self.assertIn("45 left", sent)
        self.assertIn(self.skill.name, sent)
        self.assertIn(self.specialization.name, sent)
        self.assertIn(self.mentor.name, sent)


class CmdTrainingDispatchTests(TestCase):
    """Training subverbs dispatch the correct ActionRef and kwargs."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def setUp(self):
        self.character.msg = MagicMock()
        self.success_result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="ok"),
        )

    @patch("commands.command.dispatch_player_action")
    def test_add_skill_dispatches_add_kwargs(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_training_cmd(self.character, "add skill=5 ap=10").func()
        _, ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(ref.registry_key, "manage_training")
        self.assertEqual(kwargs["operation"], "add")
        self.assertEqual(kwargs["skill_id"], 5)
        self.assertEqual(kwargs["ap_amount"], 10)
        self.assertNotIn("specialization_id", kwargs)

    @patch("commands.command.dispatch_player_action")
    def test_add_spec_alias_dispatches_spec_kwargs(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_training_cmd(self.character, "add spec=7 ap=8 mentor=3").func()
        _, _ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(kwargs["operation"], "add")
        self.assertEqual(kwargs["specialization_id"], 7)
        self.assertEqual(kwargs["ap_amount"], 8)
        self.assertEqual(kwargs["mentor_persona_id"], 3)

    @patch("commands.command.dispatch_player_action")
    def test_add_with_full_specialization_key(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_training_cmd(self.character, "add specialization=9 ap=5").func()
        _, _ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(kwargs["specialization_id"], 9)

    @patch("commands.command.dispatch_player_action")
    def test_update_dispatches_id_and_ap(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_training_cmd(self.character, "update id=4 ap=12").func()
        _, _ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(kwargs["operation"], "update")
        self.assertEqual(kwargs["allocation_id"], 4)
        self.assertEqual(kwargs["ap_amount"], 12)
        self.assertNotIn("mentor_persona_id", kwargs)

    @patch("commands.command.dispatch_player_action")
    def test_update_with_mentor_passes_mentor_persona_id(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_training_cmd(self.character, "update id=4 mentor=6").func()
        _, _ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(kwargs["mentor_persona_id"], 6)

    @patch("commands.command.dispatch_player_action")
    def test_update_clearing_mentor_passes_none(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_training_cmd(self.character, "update id=4 mentor=").func()
        _, _ref, kwargs = mock_dispatch.call_args.args
        self.assertIsNone(kwargs["mentor_persona_id"])

    @patch("commands.command.dispatch_player_action")
    def test_remove_dispatches_remove_kwargs(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_training_cmd(self.character, "remove id=4").func()
        _, _ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(kwargs["operation"], "remove")
        self.assertEqual(kwargs["allocation_id"], 4)

    @patch("commands.command.dispatch_player_action")
    def test_failure_message_surfaces_to_caller(self, mock_dispatch):
        mock_dispatch.return_value = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=False, message="Not enough budget."),
        )
        _make_training_cmd(self.character, "add skill=1 ap=999").func()
        self.character.msg.assert_called_with("Not enough budget.")


class CmdTrainingErrorTests(TestCase):
    """Training command surfaces CommandError for bad input."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def setUp(self):
        self.character.msg = MagicMock()

    def _all_msg_text(self):
        return "\n".join(
            str(c.args[0]) if c.args else str(c.kwargs) for c in self.character.msg.call_args_list
        )

    def test_unknown_subverb_messages(self):
        _make_training_cmd(self.character, "frobnicate").func()
        self.assertIn("Unknown training command", self._all_msg_text())

    def test_add_missing_skill_and_spec_raises(self):
        _make_training_cmd(self.character, "add ap=10").func()
        self.assertIn("Provide either skill", self._all_msg_text())

    def test_add_both_skill_and_spec_raises(self):
        _make_training_cmd(self.character, "add skill=1 spec=2 ap=10").func()
        self.assertIn("not both", self._all_msg_text())

    def test_add_invalid_ap_raises(self):
        _make_training_cmd(self.character, "add skill=1 ap=abc").func()
        self.assertIn("ap must be a positive integer", self._all_msg_text())

    def test_add_zero_ap_raises(self):
        _make_training_cmd(self.character, "add skill=1 ap=0").func()
        self.assertIn("ap must be a positive integer", self._all_msg_text())

    def test_update_missing_id_raises(self):
        _make_training_cmd(self.character, "update ap=10").func()
        self.assertIn("id must be a positive integer", self._all_msg_text())

    def test_malformed_token_raises(self):
        _make_training_cmd(self.character, "add skill=1 ap").func()
        self.assertIn("Expected key=value", self._all_msg_text())


class CmdProgressionUnlockListTests(TestCase):
    """Progression unlock listing renders class-level and thread items."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def setUp(self):
        self.character.msg = MagicMock()

    def test_bare_unlocks_lists_class_and_thread_items(self):
        class_unlock = SimpleNamespace(
            character_class=SimpleNamespace(name="Warrior"),
            target_level=4,
        )
        thread = SimpleNamespace(
            name="Thread of Flame",
            level=0,
        )
        prospect = SimpleNamespace(
            thread=thread,
            boundary_level=10,
            xp_cost=100,
        )

        with patch(
            "world.progression.services.spends.get_available_unlocks_for_character",
            return_value={
                "available": [
                    {"unlock": class_unlock, "xp_cost": 50, "requirements_met": True},
                ],
                "locked": [],
            },
        ):
            with patch(
                "world.magic.services.threads.near_xp_lock_threads",
                return_value=[prospect],
            ):
                _make_progression_cmd(self.character).func()

        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("Available progression unlocks:", sent)
        self.assertIn("[class] Warrior level 4: 50 XP", sent)
        self.assertIn("Thread XP-lock boundaries:", sent)
        self.assertIn("[thread] Thread of Flame level 10: 100 XP", sent)

    def test_unlocks_alias_lists(self):
        with patch(
            "world.progression.services.spends.get_available_unlocks_for_character",
            return_value={"available": [], "locked": []},
        ):
            with patch(
                "world.magic.services.threads.near_xp_lock_threads",
                return_value=[],
            ):
                _make_progression_cmd(self.character, "unlocks").func()
        self.character.msg.assert_called_once()


class CmdProgressionUnlockXPBalanceTests(TestCase):
    """``progression unlocks`` shows the caller's XP balance + recent transactions (#2122)."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.tenure = RosterTenureFactory(roster_entry=entry)
        cls.account = cls.tenure.player_data.account

    def setUp(self):
        ExperiencePointsData.flush_instance_cache()
        XPTransaction.flush_instance_cache()
        self.character.msg = MagicMock()

    def _listing_text(self) -> str:
        with (
            patch(
                "world.progression.services.spends.get_available_unlocks_for_character",
                return_value={"available": [], "locked": []},
            ),
            patch("world.magic.services.threads.near_xp_lock_threads", return_value=[]),
        ):
            _make_progression_cmd(self.character).func()
        return "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)

    def test_no_active_character_reports_zero(self):
        stray_sheet = CharacterSheetFactory()
        cmd_text = ""
        with (
            patch(
                "world.progression.services.spends.get_available_unlocks_for_character",
                return_value={"available": [], "locked": []},
            ),
            patch("world.magic.services.threads.near_xp_lock_threads", return_value=[]),
        ):
            stray_sheet.character.msg = MagicMock()
            _make_progression_cmd(stray_sheet.character, cmd_text).func()
        sent = "\n".join(str(c.args[0]) for c in stray_sheet.character.msg.call_args_list)
        self.assertIn("XP available: 0", sent)

    def test_balance_shown_with_no_transactions(self):
        ExperiencePointsDataFactory(account=self.account, total_earned=40, total_spent=15)
        sent = self._listing_text()
        self.assertIn("XP available: 25", sent)

    def test_recent_transactions_rendered(self):
        ExperiencePointsDataFactory(account=self.account, total_earned=100, total_spent=10)
        XPTransactionFactory(
            account=self.account,
            amount=20,
            reason=ProgressionReason.KUDOS_CLAIM,
            description="Kudos claim",
        )
        XPTransactionFactory(
            account=self.account,
            amount=-10,
            reason=ProgressionReason.XP_PURCHASE,
            description="Unlock purchase",
        )
        sent = self._listing_text()
        self.assertIn("XP available: 90", sent)
        self.assertIn("Recent XP transactions:", sent)
        self.assertIn("+20 XP", sent)
        self.assertIn("-10 XP", sent)

    def test_only_last_five_transactions_rendered(self):
        # Rendering is "{sign}{amount} XP — {reason display} (...)" — no description field
        # (per spec), so use uniquely-identifiable amounts (1001..1007) to tell rows apart.
        ExperiencePointsDataFactory(account=self.account, total_earned=100, total_spent=0)
        for index in range(7):
            XPTransactionFactory(
                account=self.account,
                amount=1001 + index,
                reason=ProgressionReason.KUDOS_CLAIM,
            )
        sent = self._listing_text()
        # Most recently created 5 of 7 (highest amounts, since XPTransaction orders
        # -transaction_date and the loop created them in ascending amount order).
        rendered_count = sum(f"+{1001 + index} XP" in sent for index in range(7))
        self.assertEqual(rendered_count, 5)
        self.assertNotIn("+1001 XP", sent)
        self.assertNotIn("+1002 XP", sent)


class CmdProgressionUnlockDispatchTests(TestCase):
    """Progression unlock purchase dispatches the correct ActionRef and kwargs."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def setUp(self):
        self.character.msg = MagicMock()
        self.success_result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="Unlock purchased."),
        )

    @patch("commands.command.dispatch_player_action")
    def test_unlock_class_dispatches_class_level_kwargs(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_progression_cmd(self.character, "unlock class=5").func()
        _, ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(ref.registry_key, "purchase_unlock")
        self.assertEqual(kwargs["unlock_type"], "class_level")
        self.assertEqual(kwargs["class_level_unlock_id"], 5)

    @patch("commands.command.dispatch_player_action")
    def test_unlock_thread_dispatches_thread_xp_lock_kwargs(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_progression_cmd(self.character, "unlock thread=7 level=10").func()
        _, ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(ref.registry_key, "purchase_unlock")
        self.assertEqual(kwargs["unlock_type"], "thread_xp_lock")
        self.assertEqual(kwargs["thread_id"], 7)
        self.assertEqual(kwargs["boundary_level"], 10)

    @patch("commands.command.dispatch_player_action")
    def test_unlock_skill_dispatches_skill_breakthrough_kwargs(self, mock_dispatch):
        """``progression unlock skill=<id>`` dispatches skill_breakthrough kwargs (#2115)."""
        mock_dispatch.return_value = self.success_result
        _make_progression_cmd(self.character, "unlock skill=9").func()
        _, ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(ref.registry_key, "purchase_unlock")
        self.assertEqual(kwargs["unlock_type"], "skill_breakthrough")
        self.assertEqual(kwargs["skill_id"], 9)

    @patch("commands.command.dispatch_player_action")
    def test_failure_message_surfaces_to_caller(self, mock_dispatch):
        mock_dispatch.return_value = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=False, message="Insufficient XP."),
        )
        _make_progression_cmd(self.character, "unlock class=1").func()
        self.character.msg.assert_called_with("Insufficient XP.")


class CmdProgressionUnlockErrorTests(TestCase):
    """Progression unlock command surfaces CommandError for bad input."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character

    def setUp(self):
        self.character.msg = MagicMock()

    def _all_msg_text(self):
        return "\n".join(
            str(c.args[0]) if c.args else str(c.kwargs) for c in self.character.msg.call_args_list
        )

    def test_unknown_subverb_messages(self):
        _make_progression_cmd(self.character, "frobnicate").func()
        self.assertIn("Unknown progression command", self._all_msg_text())

    def test_unlock_missing_identifier_raises(self):
        _make_progression_cmd(self.character, "unlock").func()
        self.assertIn("Provide class=", self._all_msg_text())

    def test_unlock_both_class_and_thread_raises(self):
        _make_progression_cmd(self.character, "unlock class=1 thread=2 level=10").func()
        self.assertIn("exactly one", self._all_msg_text())

    def test_unlock_thread_missing_level_raises(self):
        _make_progression_cmd(self.character, "unlock thread=2").func()
        self.assertIn("level must be a positive integer", self._all_msg_text())

    def test_unlock_invalid_id_raises(self):
        _make_progression_cmd(self.character, "unlock class=abc").func()
        self.assertIn("class must be a positive integer", self._all_msg_text())


class CmdsetRegistrationTests(TestCase):
    """Both commands are registered in the character cmdset."""

    def test_training_registered(self):
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("training", keys)

    def test_progression_unlock_registered(self):
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("progression", keys)
