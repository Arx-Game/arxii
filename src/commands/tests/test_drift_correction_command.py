"""Argument parsing for the telnet ``drift`` command (#4733).

The typed-line journey (handler, real rite) is Task 8; here the command's own parsing is
checked: how ``convert`` turns text into the action's kwargs, and what it refuses.
"""

from __future__ import annotations

from unittest.mock import patch

from actions.definitions.drift_correction import PerformDriftCorrectionAction
from commands.drift_correction import CmdDrift
from commands.exceptions import CommandError
from world.items.services.materialize import materialize_item_game_object
from world.magic.tests.test_drift_correction_rite import DriftRiteTestBase, _tied_item


class DriftCommandTestBase(DriftRiteTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.caller = self.sheet.character

    def command(self, args: str) -> CmdDrift:
        cmd = CmdDrift()
        cmd.caller = self.caller
        cmd.args = f" {args}" if args else ""
        cmd.raw_string = f"drift {args}".strip()
        return cmd

    def lines(self, args: str) -> str:
        cmd = self.command(args)
        with patch.object(cmd, "msg") as msg:
            cmd.func()
        sent = [call.args[0] for call in msg.call_args_list if call.args]
        # Typed lines go out as (text, options).
        return "\n".join(line[0] if isinstance(line, tuple) else line for line in sent)


class ResolveActionArgsTests(DriftCommandTestBase):
    def test_convert_with_amount_resolves_to_action_kwargs(self) -> None:
        kwargs = self.command("convert Drift Dread=Drift Dawnlight 5").resolve_action_args()
        self.assertEqual(kwargs["offer"], self.offer)
        self.assertEqual(kwargs["source_resonance"], self.dread)
        self.assertEqual(kwargs["target_resonance"], self.dawnlight)
        self.assertEqual(kwargs["amount"], 5)
        self.assertEqual(kwargs["components_provided"], [])

    def test_names_are_case_insensitive(self) -> None:
        kwargs = self.command("convert drift dread = drift dawnlight 5").resolve_action_args()
        self.assertEqual(kwargs["source_resonance"], self.dread)
        self.assertEqual(kwargs["target_resonance"], self.dawnlight)

    def test_amount_defaults_to_the_most_shown(self) -> None:
        kwargs = self.command("convert Drift Dread=Drift Dawnlight").resolve_action_args()
        self.assertEqual(kwargs["amount"], 12)

    def test_carried_items_are_gathered_from_the_callers_contents(self) -> None:
        item = _tied_item(self.dawnlight)
        item.holder_character_sheet = self.sheet
        item.save(update_fields=["holder_character_sheet"])
        materialize_item_game_object(item, self.sheet)
        kwargs = self.command("convert Drift Dread=Drift Dawnlight").resolve_action_args()
        self.assertEqual(kwargs["components_provided"], [item])

    def test_unknown_resonance_is_a_command_error_naming_what_you_hold(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self.command("convert Nonsense=Drift Dawnlight 3").resolve_action_args()
        self.assertIn("You hold no resonance called 'Nonsense'", ctx.exception.msg)
        self.assertIn("Drift Dread", ctx.exception.msg)

    def test_someone_elses_resonance_is_unknown_to_you(self) -> None:
        with self.assertRaises(CommandError):
            self.command("convert Drift Dread=Drift Wild 3").resolve_action_args()

    def test_missing_equals_is_a_usage_error(self) -> None:
        with self.assertRaises(CommandError) as ctx:
            self.command("convert Drift Dread").resolve_action_args()
        self.assertIn("Usage:", ctx.exception.msg)

    def test_no_offer_in_this_scene_is_a_command_error(self) -> None:
        self.offer.delete()
        with self.assertRaises(CommandError) as ctx:
            self.command("convert Drift Dread=Drift Dawnlight 3").resolve_action_args()
        self.assertEqual(ctx.exception.msg, "You have no open chance to correct drift.")

    def test_default_amount_with_nothing_convertible_is_a_command_error(self) -> None:
        with self.assertRaises(CommandError):
            self.command("convert Drift Dawnlight=Drift Dread").resolve_action_args()


class CommandWiringTests(DriftCommandTestBase):
    def test_drift_is_a_player_command_over_the_rite_action(self) -> None:
        self.assertEqual(CmdDrift.key, "drift")
        self.assertEqual(CmdDrift.locks, "cmd:all()")
        self.assertIsInstance(CmdDrift.action, PerformDriftCorrectionAction)

    def test_unknown_subverb_prints_the_usage(self) -> None:
        self.assertIn("Usage:", self.lines("frobnicate"))

    def test_bare_drift_shows_target_cap_sources_and_rate(self) -> None:
        text = self.lines("")
        self.assertIn("Toward Drift Dawnlight: up to 12.", text)
        self.assertIn("From Drift Dread: you hold 30", text)
        self.assertIn("would give 6", text)

    def test_bare_drift_lists_carried_qualifying_items_with_their_route(self) -> None:
        item = _tied_item(self.dawnlight)
        item.holder_character_sheet = self.sheet
        item.save(update_fields=["holder_character_sheet"])
        materialize_item_game_object(item, self.sheet)
        self.assertIn("(material)", self.lines(""))

    def test_decline_removes_the_offer(self) -> None:
        from world.magic.models import DriftConversionOffer

        self.lines("decline")
        self.assertFalse(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())

    def test_bare_drift_with_no_offer_says_so(self) -> None:
        self.offer.delete()
        self.assertEqual(self.lines(""), "You have no open chance to correct drift.")
