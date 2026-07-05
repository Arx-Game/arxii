"""Telnet E2E: signature technique motif journey (#1582).

Drives ``CmdSignature`` end-to-end through the three signature verbs
(list / set / clear) over the shared ``dispatch_player_action`` seam,
asserting DB state after each step and telnet feedback via ``caller.msg``.

Journey layout:
  1. ``signature list``                        — shows available bonuses + technique threads.
  2. ``signature set technique=<name> bonus=<name>`` — attaches a bonus to a thread.
  3. ``signature clear technique=<name>``     — removes the bonus.

Mirrors ``world/magic/tests/test_signature_viewset.py``'s setup (same Motif +
Facet + Resonance + Thread chain) but drives the telnet command rather than the
ViewSet — proving both surfaces converge on the same Actions.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.utils import idmapper

from commands.signature import CmdSignature
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterTechniqueFactory,
    FacetFactory,
    GiftFactory,
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import SignatureMotifBonus, Thread
from world.magic.services.signature import signature_bonus_for

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(caller: object, args: str = "") -> CmdSignature:
    """Wire CmdSignature to *caller* and call func(). Returns the cmd instance."""
    cmd = CmdSignature()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"signature {args}".strip()
    cmd.cmdname = "signature"
    caller.msg = MagicMock()
    cmd.func()
    return cmd


# ---------------------------------------------------------------------------
# Journey
# ---------------------------------------------------------------------------


class SignatureTelnetE2EJourneyTest(TestCase):
    """list → set → clear through telnet CmdSignature."""

    def setUp(self) -> None:
        idmapper.models.flush_cache()

        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

        # Motif + Resonance + Facet — the gating chain for a SignatureMotifBonus.
        self.motif = MotifFactory(character=self.sheet)
        self.resonance = ResonanceFactory()
        self.facet = FacetFactory(name="E2E Signature Facet")
        self.motif_res = MotifResonanceFactory(motif=self.motif, resonance=self.resonance)
        MotifResonanceAssociationFactory(motif_resonance=self.motif_res, facet=self.facet)

        # A technique the character knows + a TECHNIQUE-anchored thread.
        self.gift = GiftFactory()
        self.technique = TechniqueFactory(gift=self.gift, level=1, damage_profile=False)
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)

        # A qualifying signature bonus (gated on the motif's facet).
        self.bonus = SignatureMotifBonus.objects.create(
            name="E2E Bonus",
            required_facet=self.facet,
        )

        self.thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            name=self.technique.name,
        )
        self.character.threads.invalidate()

    def tearDown(self) -> None:
        self.thread.delete()
        self.character.threads.invalidate()

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    def test_list_shows_available_bonus_and_technique_thread(self) -> None:
        """signature list → available bonuses + technique threads with current bonus."""
        _run(self.character, "list")

        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn("E2E Bonus", msg, "list should show the available bonus")
        self.assertIn(self.technique.name, msg, "list should show the technique thread")
        self.assertIn("none", msg.lower(), "thread should show no bonus set yet")

    # ------------------------------------------------------------------
    # set
    # ------------------------------------------------------------------

    def test_set_attaches_bonus_to_thread(self) -> None:
        """signature set technique=<name> bonus=<name> → bonus attached to the thread."""
        _run(self.character, f"set technique={self.technique.name} bonus=E2E Bonus")

        self.thread.refresh_from_db()
        self.assertEqual(
            self.thread.signature_bonus, self.bonus, "bonus should be set on the thread"
        )

        # The service-level read confirms it too.
        self.assertEqual(signature_bonus_for(self.character, self.technique), self.bonus)

        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn("E2E Bonus", msg)
        self.assertIn("set", msg.lower())

    def test_set_unknown_technique_is_rejected(self) -> None:
        """signature set with an unknown technique → error message."""
        _run(self.character, "set technique=Nonexistent bonus=E2E Bonus")

        self.character.msg.assert_called()
        # CommandError path calls msg(str) then msg(command_error=...); the
        # user-facing text is the first positional call.
        msg = self.character.msg.call_args_list[0][0][0]
        self.assertIn("don't know a technique", msg.lower())

    def test_set_unknown_bonus_is_rejected(self) -> None:
        """signature set with an unknown bonus → error message."""
        _run(self.character, f"set technique={self.technique.name} bonus=Nonexistent")

        self.character.msg.assert_called()
        msg = self.character.msg.call_args_list[0][0][0]
        self.assertIn("no signature bonus", msg.lower())

    # ------------------------------------------------------------------
    # clear
    # ------------------------------------------------------------------

    def test_clear_removes_bonus_from_thread(self) -> None:
        """signature clear technique=<name> → bonus removed (null)."""
        # Pre-set the bonus.
        self.thread.signature_bonus = self.bonus
        self.thread.save(update_fields=["signature_bonus"])

        _run(self.character, f"clear technique={self.technique.name}")

        self.thread.refresh_from_db()
        self.assertIsNone(self.thread.signature_bonus, "clear should null the bonus")

        self.character.msg.assert_called()
        msg = self.character.msg.call_args[0][0]
        self.assertIn("cleared", msg.lower())
