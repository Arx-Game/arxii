"""Unit tests for CmdResonance — spendable resonance balances + grant history (#2032).

Covers:
  (a) bare ``resonance`` lists claimed resonances with balance + lifetime earned.
  (b) bare ``resonance`` with no claimed resonances shows a sane empty-state message.
  (c) ``resonance history`` shows recent grants newest-first with their source label.
  (d) ``resonance history <name>`` narrows to one claimed resonance.
  (e) ``resonance history`` with no grants shows a sane empty-state message.
  (f) an unknown resonance name in ``resonance history`` surfaces an error.
  (g) unknown subverbs are handled gracefully.

Uses the _run() harness pattern, matching test_durance_command.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.resonance import CmdResonance
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.magic.models import ResonanceGrant


def _run(cmd_cls, caller, args=""):
    """Build a command instance and call func(); return the list of msg strings."""
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class ResonanceBalancesTests(TestCase):
    """Bare ``resonance`` renders claimed-resonance balances."""

    def setUp(self) -> None:
        self.char = CharacterFactory(db_key="ResonanceBalanceChar")
        self.sheet = CharacterSheetFactory(character=self.char)

    def test_no_character_sheet_shows_error(self) -> None:
        bare_char = CharacterFactory(db_key="NoSheetChar")
        msgs = _run(CmdResonance, bare_char)
        combined = "\n".join(msgs)
        self.assertIn("no active character", combined.lower())

    def test_empty_state_when_no_claimed_resonances(self) -> None:
        msgs = _run(CmdResonance, self.char)
        combined = "\n".join(msgs)
        self.assertIn("not claimed any resonance", combined.lower())

    def test_lists_balance_and_lifetime_earned(self) -> None:
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=ResonanceFactory(name="Ember"),
            balance=15,
            lifetime_earned=40,
        )

        msgs = _run(CmdResonance, self.char)
        combined = "\n".join(msgs)

        self.assertIn("Ember", combined)
        self.assertIn("15", combined)
        self.assertIn("40", combined)

    def test_status_subverb_not_required(self) -> None:
        """Bare and no-arg both hit the same balances path (no separate subverb needed)."""
        msgs = _run(CmdResonance, self.char, "")
        combined = "\n".join(msgs)
        self.assertIn("resonance", combined.lower())


class ResonanceHistoryTests(TestCase):
    """``resonance history [<name>]`` shows recent ResonanceGrant rows."""

    def setUp(self) -> None:
        self.char = CharacterFactory(db_key="ResonanceHistoryChar")
        self.sheet = CharacterSheetFactory(character=self.char)
        self.ember = ResonanceFactory(name="Ember")
        self.frost = ResonanceFactory(name="Frost")
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.ember, balance=5)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.frost, balance=3)

    def test_empty_state_when_no_grants(self) -> None:
        msgs = _run(CmdResonance, self.char, "history")
        combined = "\n".join(msgs)
        self.assertIn("no resonance grants", combined.lower())

    def test_shows_grant_with_source_label(self) -> None:
        ResonanceGrant.objects.create(
            character_sheet=self.sheet,
            resonance=self.ember,
            amount=25,
            source=GainSource.STAFF_GRANT,
        )

        msgs = _run(CmdResonance, self.char, "history")
        combined = "\n".join(msgs)

        self.assertIn("Ember", combined)
        self.assertIn("25", combined)
        self.assertIn(GainSource.STAFF_GRANT.label, combined)

    def test_history_narrowed_to_named_resonance(self) -> None:
        ResonanceGrant.objects.create(
            character_sheet=self.sheet,
            resonance=self.ember,
            amount=25,
            source=GainSource.STAFF_GRANT,
        )
        ResonanceGrant.objects.create(
            character_sheet=self.sheet,
            resonance=self.frost,
            amount=7,
            source=GainSource.STAFF_GRANT,
        )

        msgs = _run(CmdResonance, self.char, "history Frost")
        combined = "\n".join(msgs)

        self.assertIn("Frost", combined)
        self.assertIn("7", combined)
        self.assertNotIn("Ember", combined)

    def test_unknown_resonance_name_surfaces_error(self) -> None:
        msgs = _run(CmdResonance, self.char, "history Nonexistent")
        combined = "\n".join(msgs)
        self.assertIn("No such resonance", combined)

    def test_multiple_grants_all_render(self) -> None:
        """Strict newest-first ordering is exercised at the service level
        (resonance_grant_history_for_sheet, world/magic/tests/test_gain_services.py) —
        this just confirms the command renders every returned row."""
        ResonanceGrant.objects.create(
            character_sheet=self.sheet,
            resonance=self.ember,
            amount=1,
            source=GainSource.STAFF_GRANT,
        )
        ResonanceGrant.objects.create(
            character_sheet=self.sheet,
            resonance=self.ember,
            amount=2,
            source=GainSource.STAFF_GRANT,
        )

        msgs = _run(CmdResonance, self.char, "history")
        combined = "\n".join(msgs)
        self.assertIn("+1", combined)
        self.assertIn("+2", combined)


class ResonanceUnknownSubverbTests(TestCase):
    """Unknown subverbs surface a helpful error, not an exception."""

    def setUp(self) -> None:
        self.char = CharacterFactory(db_key="ResonanceUnknownSubChar")
        CharacterSheetFactory(character=self.char)

    def test_unknown_subverb_shows_error_message(self) -> None:
        msgs = _run(CmdResonance, self.char, "frobnicate")
        combined = "\n".join(msgs)
        self.assertIn("frobnicate", combined)
        self.assertIn("Unknown", combined)
