"""Telnet E2E: multi-participant ritual session lifecycle via CmdRitual (#1345).

Drives the full draft → join → fire journey through CmdRitual subcommands,
proving that the telnet surface wires correctly to the existing session
service functions (draft_session / accept_session / fire_session).

Uses RenewTheOathRitualFactory (FORMATION, ≥2 participants) with
perform_covenant_rite patched — the covenant service is tested separately;
here we prove the command plumbing.

Error-path coverage:
  - fire before all participants have joined → ThresholdNotMetError → caller message
  - decline when only 2 total participants → session dissolved
  - join a session where caller is not a participant → error message
  - ritual sessions listing shows pending sessions
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.ritual import CmdRitual
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import ParticipantState
from world.magic.factories import RenewTheOathRitualFactory
from world.magic.models.sessions import RitualSession

_PERFORM_COVENANT_RITE_PATH = "world.covenants.services.perform_covenant_rite"


def _run(cmd_cls: type, caller: object, args: str = "") -> object:
    """Helper: build and run a command instance."""
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    return cmd


class RitualSessionTelnetE2ETests(TestCase):
    """Full session lifecycle driven by CmdRitual subcommands."""

    def setUp(self) -> None:
        # Use setUp (not setUpTestData) to avoid DbHolder deepcopy issues in CI shards.
        self.initiator = CharacterFactory(db_key="SessionInitiator")
        self.participant = CharacterFactory(db_key="SessionParticipant")
        self.uninvited = CharacterFactory(db_key="SessionUninvited")
        self.initiator_sheet = CharacterSheetFactory(character=self.initiator)
        self.participant_sheet = CharacterSheetFactory(character=self.participant)
        self.uninvited_sheet = CharacterSheetFactory(character=self.uninvited)

        self.ritual = RenewTheOathRitualFactory()

    def _draft(self) -> int:
        """Run 'ritual draft Renew the Oath invite=Participant'; return session pk."""
        cmd = _run(CmdRitual, self.initiator, f"draft {self.ritual.name} invite=Participant")
        cmd.caller.search = MagicMock(return_value=self.participant)
        cmd.func()
        return RitualSession.objects.get(ritual=self.ritual).pk

    # ------------------------------------------------------------------
    # Happy-path lifecycle
    # ------------------------------------------------------------------

    def test_full_lifecycle(self) -> None:
        """draft → join → fire → session deleted, service called once."""
        with patch(_PERFORM_COVENANT_RITE_PATH) as mock_rite:
            mock_rite.return_value = MagicMock()

            # 1. Initiator drafts.
            session_pk = self._draft()
            session = RitualSession.objects.get(pk=session_pk)
            self.assertEqual(session.ritual, self.ritual)
            self.assertEqual(session.initiator, self.initiator_sheet)
            self.assertEqual(session.participants.count(), 2)

            initiator_part = session.participants.get(character_sheet=self.initiator_sheet)
            participant_part = session.participants.get(character_sheet=self.participant_sheet)
            self.assertEqual(initiator_part.state, ParticipantState.ACCEPTED)
            self.assertEqual(participant_part.state, ParticipantState.INVITED)
            self.initiator.msg.assert_called()
            self.assertIn(str(session_pk), self.initiator.msg.call_args[0][0])

            # 2. Participant joins.
            cmd = _run(CmdRitual, self.participant, f"join {session_pk}")
            cmd.func()
            participant_part.refresh_from_db()
            self.assertEqual(participant_part.state, ParticipantState.ACCEPTED)
            self.participant.msg.assert_called()
            self.assertIn("joined", self.participant.msg.call_args[0][0])

            # 3. Initiator fires.
            cmd = _run(CmdRitual, self.initiator, f"fire {session_pk}")
            cmd.func()
            mock_rite.assert_called_once()
            self.assertFalse(RitualSession.objects.filter(pk=session_pk).exists())
            self.initiator.msg.assert_called()
            self.assertIn("complete", self.initiator.msg.call_args[0][0])

    # ------------------------------------------------------------------
    # sessions listing
    # ------------------------------------------------------------------

    def test_sessions_listing_shows_pending_session(self) -> None:
        """'ritual sessions' shows the session with its ID and participant states."""
        session_pk = self._draft()

        cmd = _run(CmdRitual, self.initiator, "sessions")
        cmd.func()
        output = self.initiator.msg.call_args[0][0]
        self.assertIn(str(session_pk), output)
        self.assertIn(self.ritual.name, output)
        self.assertIn("Participant", output)

    def test_sessions_listing_empty_when_none(self) -> None:
        """'ritual sessions' with no pending sessions says so."""
        cmd = _run(CmdRitual, self.initiator, "sessions")
        cmd.func()
        output = self.initiator.msg.call_args[0][0]
        self.assertIn("no pending", output.lower())

    # ------------------------------------------------------------------
    # Error paths
    # ------------------------------------------------------------------

    def test_fire_before_participant_joins_sends_error(self) -> None:
        """Firing before participant accepts → ThresholdNotMetError → error message."""
        with patch(_PERFORM_COVENANT_RITE_PATH):
            session_pk = self._draft()

            # participant has NOT joined — try to fire immediately.
            cmd = _run(CmdRitual, self.initiator, f"fire {session_pk}")
            cmd.func()
            output = self.initiator.msg.call_args[0][0]
            self.assertIn("cannot fire", output.lower())
            # Session still exists (fire was blocked).
            self.assertTrue(RitualSession.objects.filter(pk=session_pk).exists())

    def test_decline_dissolves_session_when_threshold_unachievable(self) -> None:
        """Declining in a 2-participant FORMATION session dissolves the session."""
        session_pk = self._draft()

        cmd = _run(CmdRitual, self.participant, f"decline {session_pk}")
        cmd.func()
        output = self.participant.msg.call_args[0][0]
        # Session dissolved — threshold impossible after 1 decline in FORMATION.
        self.assertFalse(RitualSession.objects.filter(pk=session_pk).exists())
        self.assertIn("dissolved", output.lower())

    def test_join_nonexistent_session_sends_error(self) -> None:
        """Joining a session ID with no matching participant row → error."""
        cmd = _run(CmdRitual, self.uninvited, "join 99999")
        cmd.func()
        output = self.uninvited.msg.call_args[0][0]
        self.assertIn("not an invited participant", output.lower())

    def test_fire_by_non_initiator_sends_error(self) -> None:
        """Attempting to fire a session the caller didn't initiate → error."""
        session_pk = self._draft()

        cmd = _run(CmdRitual, self.participant, f"fire {session_pk}")
        cmd.func()
        output = self.participant.msg.call_args[0][0]
        self.assertIn("not found or you are not its initiator", output.lower())

    def test_draft_unknown_ritual_sends_error(self) -> None:
        """Drafting a non-existent ritual → error."""
        cmd = _run(CmdRitual, self.initiator, "draft Rite of Nonexistent invite=Participant")
        cmd.caller.search = MagicMock(return_value=self.participant)
        cmd.func()
        output = self.initiator.msg.call_args[0][0]
        self.assertIn("No multi-participant ritual named", output)

    def test_single_actor_path_unchanged(self) -> None:
        """'ritual <name>' without a session subcommand still hits PerformRitualAction."""
        from world.magic.factories import ImbuingRitualFactory

        ImbuingRitualFactory()
        cmd = _run(CmdRitual, self.initiator, "Rite of Imbuing")
        with patch("actions.definitions.ritual.PerformRitualAction.run") as mock_run:
            mock_run.return_value = MagicMock()
            cmd.func()
        mock_run.assert_called_once()
