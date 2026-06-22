"""Tests for CmdPull — thin telnet shell over PullThreadAction (#1342)."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.exceptions import CommandError
from commands.pull import CmdPull
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    ThreadFactory,
)
from world.magic.types import PullActionContext
from world.traits.factories import TraitFactory


class CmdPullResolveTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.cr = CharacterResonanceFactory(balance=50)
        cls.sheet = cls.cr.character_sheet
        cls.resonance = cls.cr.resonance
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(owner=cls.sheet, resonance=cls.resonance, name="Ember Thread")

    def setUp(self) -> None:
        self.character = self.sheet.character
        self.character.msg = MagicMock()
        CharacterAnimaFactory(character=self.character)

    def _make_cmd(self, args: str) -> CmdPull:
        cmd = CmdPull()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"pull {args}"
        return cmd

    def test_resolve_action_args_with_trait_name(self) -> None:
        """resolve_action_args returns correct kwargs including PullActionContext with trait."""
        cmd = self._make_cmd(
            f"resonance={self.resonance.name} tier=1 "
            f"thread={self.thread.name} trait={self.trait.name}"
        )
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["resonance"], self.resonance)
        self.assertEqual(kwargs["tier"], 1)
        self.assertEqual(kwargs["threads"], [self.thread])
        ctx = kwargs["pull_action_context"]
        self.assertIsInstance(ctx, PullActionContext)
        self.assertIn(self.trait.pk, ctx.involved_traits)

    def test_resolve_action_args_without_trait(self) -> None:
        """resolve_action_args builds an empty-traits PullActionContext when no trait given."""
        cmd = self._make_cmd(f"resonance={self.resonance.name} tier=2 thread={self.thread.name}")
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["tier"], 2)
        ctx = kwargs["pull_action_context"]
        self.assertIsInstance(ctx, PullActionContext)
        self.assertEqual(ctx.involved_traits, ())

    def test_resolve_thread_by_pk(self) -> None:
        """Thread can be resolved by primary key."""
        cmd = self._make_cmd(f"resonance={self.resonance.name} tier=1 thread={self.thread.pk}")
        kwargs = cmd.resolve_action_args()
        self.assertEqual(kwargs["threads"], [self.thread])

    def test_preview_mode_detected(self) -> None:
        """_is_preview_mode returns True when args start with 'preview'."""
        cmd = self._make_cmd(
            f"preview resonance={self.resonance.name} tier=1 thread={self.thread.name}"
        )
        self.assertTrue(cmd._is_preview_mode())

    def test_commit_mode_detected(self) -> None:
        """_is_preview_mode returns False for normal pull args."""
        cmd = self._make_cmd(f"resonance={self.resonance.name} tier=1 thread={self.thread.name}")
        self.assertFalse(cmd._is_preview_mode())

    def test_pull_args_strips_preview_prefix(self) -> None:
        """_pull_args strips the 'preview' token from args."""
        cmd = self._make_cmd(
            f"preview resonance={self.resonance.name} tier=1 thread={self.thread.name}"
        )
        args = cmd._pull_args()
        first_token = args.split()[0] if args.split() else ""
        self.assertNotEqual(first_token.lower(), "preview")

    def test_invalid_tier_raises(self) -> None:
        """Tier outside 1-3 raises CommandError."""
        cmd = self._make_cmd(f"resonance={self.resonance.name} tier=5 thread={self.thread.name}")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_missing_thread_raises(self) -> None:
        """Missing thread= kwarg raises CommandError."""
        cmd = self._make_cmd(f"resonance={self.resonance.name} tier=1")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_missing_resonance_raises(self) -> None:
        """Missing resonance= kwarg raises CommandError."""
        cmd = self._make_cmd(f"tier=1 thread={self.thread.name}")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_missing_args_raises(self) -> None:
        """Blank args raises CommandError."""
        cmd = self._make_cmd("")
        with self.assertRaises(CommandError):
            cmd.resolve_action_args()

    def test_unknown_thread_reports_error(self) -> None:
        """An unknown thread sends an error message to the caller."""
        cmd = self._make_cmd(f"resonance={self.resonance.name} tier=1 thread=99999")
        cmd.func()
        self.character.msg.assert_called()

    def test_parse_kwargs_multiple_threads(self) -> None:
        """_parse_kwargs handles comma-separated thread list correctly."""
        parsed = CmdPull._parse_kwargs("resonance=Embers tier=1 thread=Thread A,Thread B")
        self.assertEqual(parsed["thread"], "Thread A,Thread B")
        self.assertEqual(parsed["resonance"], "Embers")
        self.assertEqual(parsed["tier"], "1")
