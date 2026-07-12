"""Telnet consent-flow journey E2E (#1338).

Drives the full social-action consent story via telnet commands — no HTTP client.
Proves the command layer converges on the same service seam as the web viewset:

  1. Initiator runs ``CmdIntimidate <target>`` → SceneActionRequest lands PENDING.
  2. Target runs ``CmdAccept`` → respond_to_action_request is called → RESOLVED.
  3. Target runs ``CmdDeny`` → DENIED without calling start_action_resolution.

``start_action_resolution`` is patched (same boundary as
``test_restore_sense_consent_e2e.py``) so the test is SQLite-compatible.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from commands.consent import CmdAccept, CmdDeny, CmdIntimidate
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory


def _make_pending_resolution() -> PendingActionResolution:
    """Minimal PendingActionResolution mock for the resolve pipeline."""
    check_result = MagicMock()
    check_result.success_level = 1
    check_result.outcome_name = "Success"
    check_result.outcome = None
    main_result = StepResult(step_label="main", check_result=check_result, consequence_id=None)
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=10,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


class TelnetConsentJourneyTests(TestCase):
    """Initiator dispatches via telnet; target accepts or denies via telnet."""

    def setUp(self) -> None:
        # DbHolder trap: Evennia ObjectDB fixtures must be built in setUp,
        # not setUpTestData (idmapper contamination in CI shard runs).
        self.room = ObjectDBFactory(
            db_key="Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.initiator_char = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.target_char = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        # #2214: create_action_request now auto-resolves a single-target NPC-primary
        # request at creation time. Bob is the human respondent of this two-step
        # intimidate-then-accept/deny journey, so he needs a real db_account —
        # otherwise _persona_is_npc treats him as an NPC and the request resolves
        # immediately instead of staying PENDING for CmdAccept/CmdDeny to act on.
        self.target_char.db_account = AccountFactory()
        self.target_char.save(update_fields=["db_account"])
        self.initiator_sheet = CharacterSheetFactory(character=self.initiator_char)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)
        self.scene = SceneFactory(is_active=True, location=self.room)
        # Bust the per-location active-scene cache (SharedMemory identity map).
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache

        # Seed the Intimidate ActionTemplate so create_action_request can resolve it.
        ActionTemplateFactory(name="Intimidate", category="social", consequence_pool=None)

        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()
        self.addCleanup(self.accrue_patcher.stop)

    def _run(self, cmd_cls: type, caller: object, args: str = "") -> object:
        cmd = cmd_cls()
        cmd.caller = caller
        cmd.args = args
        cmd.raw_string = f"{cmd_cls.key} {args}".strip()
        caller.msg = MagicMock()
        cmd.func()
        return cmd

    @patch("world.scenes.action_services.start_action_resolution")
    def test_intimidate_then_accept_resolves_request(self, mock_resolve: MagicMock) -> None:
        """Full telnet journey: intimidate → PENDING → accept → RESOLVED."""
        mock_resolve.return_value = _make_pending_resolution()

        # 1. Initiator dispatches via telnet.
        self._run(CmdIntimidate, self.initiator_char, self.target_char.key)

        req = SceneActionRequest.objects.get(
            initiator_persona=self.initiator_sheet.primary_persona,
        )
        self.assertEqual(req.status, ActionRequestStatus.PENDING)
        self.assertEqual(req.target_persona, self.target_sheet.primary_persona)
        self.assertEqual(req.action_key, "intimidate")
        self.initiator_char.msg.assert_called()

        # 2. Target accepts via telnet.
        self._run(CmdAccept, self.target_char)

        req.refresh_from_db()
        self.assertEqual(req.status, ActionRequestStatus.RESOLVED)
        self.target_char.msg.assert_called()

    @patch("world.scenes.action_services.start_action_resolution")
    def test_intimidate_then_deny_marks_denied(self, mock_resolve: MagicMock) -> None:
        """Target denies via telnet → DENIED; start_action_resolution never called."""
        self._run(CmdIntimidate, self.initiator_char, self.target_char.key)

        req = SceneActionRequest.objects.get(
            initiator_persona=self.initiator_sheet.primary_persona,
        )
        self._run(CmdDeny, self.target_char)

        req.refresh_from_db()
        self.assertEqual(req.status, ActionRequestStatus.DENIED)
        mock_resolve.assert_not_called()
