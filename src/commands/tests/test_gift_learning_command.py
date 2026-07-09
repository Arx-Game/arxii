"""Tests for the ``learn`` telnet command — CmdLearn (#2116).

Mirrors test_progression_commands.py's shape: dispatch tests verify the
ActionRef + kwargs sent to dispatch_player_action; error tests verify bad
input surfaces a CommandError message; the hub test verifies the status
listing renders unlocks + offers.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionResult, DispatchResult
from commands.gift_learning import CmdLearn
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    GiftFactory,
    GiftUnlockFactory,
    TechniqueFactory,
    TechniqueTeachingOfferFactory,
    ThreadWeavingTeachingOfferFactory,
    ThreadWeavingUnlockFactory,
)
from world.roster.factories import RosterTenureFactory


def _make_learn_cmd(caller, args=""):
    cmd = CmdLearn()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"learn {args}".strip()
    cmd.cmdname = "learn"
    return cmd


class CmdLearnDispatchTests(TestCase):
    """learn <subverb> <id> dispatches the correct ActionRef and kwargs."""

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
    def test_gift_dispatches_purchase_gift_unlock(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_learn_cmd(self.character, "gift 5").func()
        _, ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(ref.registry_key, "purchase_gift_unlock")
        self.assertEqual(kwargs["gift_unlock_id"], 5)

    @patch("commands.command.dispatch_player_action")
    def test_technique_dispatches_accept_technique_offer(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_learn_cmd(self.character, "technique 9").func()
        _, ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(ref.registry_key, "accept_technique_offer")
        self.assertEqual(kwargs["offer_id"], 9)

    @patch("commands.command.dispatch_player_action")
    def test_thread_dispatches_accept_thread_weaving_offer(self, mock_dispatch):
        mock_dispatch.return_value = self.success_result
        _make_learn_cmd(self.character, "thread 3").func()
        _, ref, kwargs = mock_dispatch.call_args.args
        self.assertEqual(ref.registry_key, "accept_thread_weaving_offer")
        self.assertEqual(kwargs["offer_id"], 3)

    @patch("commands.command.dispatch_player_action")
    def test_failure_message_surfaces_to_caller(self, mock_dispatch):
        mock_dispatch.return_value = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=False, message="Insufficient XP."),
        )
        _make_learn_cmd(self.character, "gift 1").func()
        self.character.msg.assert_called_with("Insufficient XP.")


class CmdLearnErrorTests(TestCase):
    """learn surfaces a CommandError-driven message for bad input."""

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
        _make_learn_cmd(self.character, "frobnicate 1").func()
        self.assertIn("Unknown learn action", self._all_msg_text())

    def test_gift_missing_id_raises(self):
        _make_learn_cmd(self.character, "gift").func()
        self.assertIn("Usage: learn gift <id>.", self._all_msg_text())

    def test_technique_non_numeric_id_raises(self):
        _make_learn_cmd(self.character, "technique abc").func()
        self.assertIn("Usage: learn technique <id>.", self._all_msg_text())


class CmdLearnHubTests(TestCase):
    """Bare ``learn``/``learn status`` renders unlocks + offers."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.gift = GiftFactory(name="Sight_hub")
        cls.gift_unlock = GiftUnlockFactory(gift=cls.gift, xp_cost=25)
        cls.teacher_tenure = RosterTenureFactory()
        cls.technique = TechniqueFactory(gift=cls.gift, name="Soulsight_hub")
        cls.technique_offer = TechniqueTeachingOfferFactory(
            teacher=cls.teacher_tenure,
            technique=cls.technique,
            pitch="Learn to see souls",
        )
        cls.weaving_unlock = ThreadWeavingUnlockFactory()
        cls.thread_offer = ThreadWeavingTeachingOfferFactory(
            teacher=cls.teacher_tenure,
            unlock=cls.weaving_unlock,
            pitch="Learn to weave",
        )

    def setUp(self):
        self.character.msg = MagicMock()

    def test_bare_learn_shows_hub(self):
        _make_learn_cmd(self.character).func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("Gift unlocks:", sent)
        self.assertIn("Sight_hub", sent)
        self.assertIn("25 XP", sent)
        self.assertIn("not purchased", sent)
        self.assertIn("Technique-teaching offers:", sent)
        self.assertIn("Soulsight_hub", sent)
        self.assertIn("Learn to see souls", sent)
        self.assertIn("Thread-weaving teaching offers:", sent)
        self.assertIn("Learn to weave", sent)

    def test_status_subverb_same_as_bare(self):
        _make_learn_cmd(self.character, "status").func()
        sent = "\n".join(str(c.args[0]) for c in self.character.msg.call_args_list)
        self.assertIn("Gift unlocks:", sent)


class CmdsetRegistrationTests(TestCase):
    """CmdLearn is registered in the character cmdset."""

    def test_learn_registered(self):
        from commands.default_cmdsets import CharacterCmdSet

        cmdset = CharacterCmdSet()
        cmdset.at_cmdset_creation()
        keys = {c.key for c in cmdset.commands}
        self.assertIn("learn", keys)
