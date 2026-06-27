"""Unit tests: CmdRitual draft/join kwarg parsing for soul-tether sessions (#1449).

Covers the fiddly parse/error paths the journey E2E samples but doesn't
exhaust. Cheap branch coverage; the E2E (test_soul_tether_telnet_journey_e2e)
proves the happy path end-to-end.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.ritual import CmdRitual
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    AcceptSoulTetherRitualFactory,
    AffinityFactory,
    ResonanceFactory,
    wire_soul_tether_content,
)
from world.magic.models.sessions import RitualSession


def _run(cmd_cls: type, caller: object, args: str = "") -> object:
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    return cmd


class RitualDraftKwargsParseTests(TestCase):
    def setUp(self) -> None:
        wire_soul_tether_content()
        self.ritual = AcceptSoulTetherRitualFactory()
        self.abyssal = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=self.abyssal)
        self.initiator = CharacterFactory(db_key="DraftInit")
        self.initiator_sheet = CharacterSheetFactory(character=self.initiator)
        self.partner = CharacterFactory(db_key="DraftPartner")
        self.partner_sheet = CharacterSheetFactory(character=self.partner)

    def _draft(self, args: str) -> str:
        cmd = _run(CmdRitual, self.initiator, f"draft {args}")
        cmd.caller.search = MagicMock(return_value=self.partner)
        cmd.func()
        return self.initiator.msg.call_args[0][0] if self.initiator.msg.called else ""

    def test_unknown_role_sends_error(self) -> None:
        out = self._draft(
            f"accept_soul_tether invite=DraftPartner role=wizard resonance={self.resonance.name}"
        )
        self.assertIn("Unknown role", out)

    def test_unknown_resonance_name_sends_error(self) -> None:
        out = self._draft(
            "accept_soul_tether invite=DraftPartner role=sinner resonance=NopeNoSuchResonance"
        )
        self.assertIn("No resonance named", out)

    def test_role_without_resonance_still_drafts(self) -> None:
        # role without resonance: role is stored, resonance_id absent from session_kwargs.
        # (The fire handler raises RequiredReferenceMissingError at fire time — that's the
        # service's job, not the command's. The command should still draft successfully.)
        out = self._draft("accept_soul_tether invite=DraftPartner role=sinner")
        self.assertIn("drafted", out.lower())
        session = RitualSession.objects.get(ritual=self.ritual)
        self.assertEqual(
            session.participants.get(character_sheet=self.initiator_sheet).participant_kwargs[
                "soul_tether_role"
            ],
            "SINNER",
        )
        self.assertNotIn("resonance_id", session.session_kwargs)


class RitualJoinKwargsParseTests(TestCase):
    def setUp(self) -> None:
        wire_soul_tether_content()
        self.ritual = AcceptSoulTetherRitualFactory()
        self.abyssal = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=self.abyssal)
        self.initiator = CharacterFactory(db_key="JoinInit")
        self.initiator_sheet = CharacterSheetFactory(character=self.initiator)
        self.partner = CharacterFactory(db_key="JoinPartner")
        self.partner_sheet = CharacterSheetFactory(character=self.partner)
        # Draft a session the partner is invited to.
        cmd = _run(
            CmdRitual,
            self.initiator,
            f"draft accept_soul_tether invite=JoinPartner role=sinner "
            f"resonance={self.resonance.name} writeup=test",
        )
        cmd.caller.search = MagicMock(return_value=self.partner)
        cmd.func()
        self.session = RitualSession.objects.get(ritual=self.ritual)

    def test_join_with_unknown_role_sends_error(self) -> None:
        cmd = _run(CmdRitual, self.partner, f"join {self.session.pk} role=wizard")
        cmd.func()
        out = self.partner.msg.call_args[0][0]
        self.assertIn("Unknown role", out)

    def test_join_without_role_still_accepts(self) -> None:
        cmd = _run(CmdRitual, self.partner, f"join {self.session.pk}")
        cmd.func()
        out = self.partner.msg.call_args[0][0]
        self.assertIn("joined", out.lower())
