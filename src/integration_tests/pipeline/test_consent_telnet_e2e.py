"""Telnet E2E: intimidate -> accept resolves the consent flow (#1337).

Proves a telnet two-party social action reaches the SAME consent services the
web viewset uses (``create_action_request`` / ``respond_to_action_request``) and
drives them through to full resolution.

This test exercises the full fixture shape (scene +
two characters/personas + the "Intimidate" ``ActionTemplate``) and derives the
arguments the telnet way — scene from the caller's room, personas from
``active_persona_for_sheet`` — then drives the real ``CmdIntimidate`` /
``CmdAccept`` commands.

``respond_to_action_request`` does NOT merely flip status to ACCEPTED: on accept
it runs the full standard-action resolution (``_resolve_standard_action`` ->
``start_action_resolution``) to a terminal RESOLVED state and records a result
``Interaction``. We patch ``start_action_resolution`` (exactly as the web test
patches it) so the check-roll infrastructure is stubbed while every other
service step — status transition, result-interaction creation, fatigue/accrual —
runs for real. A plain (no-technique) intimidate is used so resolution never
touches the Postgres-only ``apply_condition`` (DISTINCT ON) path, keeping the
test on the SQLite fast tier.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from commands.consent import CmdAccept, CmdIntimidate
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory


def _make_pending_resolution() -> PendingActionResolution:
    """Minimal PendingActionResolution standing in for start_action_resolution.

    Mirrors ``test_targeted_action_e2e._make_pending_resolution``: a COMPLETE
    resolution with a success check result, enough for ``_create_result_interaction``
    to read ``success_level`` / ``outcome_name`` and record the Interaction.
    """
    check_result = MagicMock()
    check_result.success_level = 1
    check_result.outcome_name = "Success"
    check_result.outcome = None
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=10,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


def _make_character_in_room(room: ObjectDB) -> ObjectDB:
    """Create a Character placed in ``room`` (so caller.search finds peers there)."""
    char = CharacterFactory()
    char.location = room
    char.save()
    return char


class ConsentTelnetE2ETests(TestCase):
    """Telnet ``intimidate`` -> ``accept`` drives the real consent services.

    Uses ``setUp`` (not ``setUpTestData``) for the ObjectDB-bearing fixtures:
    Django's ``setUpTestData`` deepcopy machinery cannot copy DbHolder /
    SharedMemoryModel instances (copy.Error in CI shard runs — see project
    memory + the combat-cast telnet E2E).
    """

    def setUp(self) -> None:
        # Flush the SharedMemoryModel identity map to avoid stale PK-recycled
        # instances leaking from a prior test (see project memory).
        idmapper_models.flush_cache()

        # Patch accrue: the consent service awards good-sport kudos on accept,
        # which would otherwise need the social_engagement KudosSourceCategory +
        # GameWeek seeded. Mirrors the web E2E.
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.mock_accrue = self.accrue_patcher.start()
        self.addCleanup(self.accrue_patcher.stop)

        # Room both characters share; the scene is located here so the telnet
        # command's get_active_scene(location) finds it.
        self.room = ObjectDBFactory(
            db_key="TestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        # The "Intimidate" ActionTemplate: create_action_request resolves the
        # template by the registry intimidate action's template_name ("Intimidate"),
        # and the accept path requires it to run _resolve_standard_action. (The web
        # test attaches a template manually because its create endpoint does not
        # accept one; the telnet create path resolves it automatically by name.)
        self.action_template = ActionTemplateFactory(name="Intimidate")

        # Scene located in the room and active, so it is the room's active scene.
        self.scene = SceneFactory(location=self.room, is_active=True)

        # --- Initiator: character + sheet + primary persona, placed in the room ---
        self.initiator_char = _make_character_in_room(self.room)
        self.initiator_sheet = CharacterSheetFactory(character=self.initiator_char)
        self.initiator_persona = self.initiator_sheet.primary_persona

        # --- Target: character + sheet + primary persona, placed in the room ---
        self.target_char = _make_character_in_room(self.room)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)
        self.target_persona = self.target_sheet.primary_persona
        # Wire a real controlling account so _persona_is_npc reads this as a PC
        # (#2214) — this test's two-step create-then-accept flow requires the
        # request to stay PENDING until CmdAccept runs, not auto-resolve at create.
        self.target_char.db_account = AccountFactory()
        self.target_char.save(update_fields=["db_account"])

    @patch("world.scenes.action_services.start_action_resolution")
    def test_intimidate_then_accept_resolves(self, mock_resolve: MagicMock) -> None:
        """Telnet intimidate creates a PENDING request; accept resolves it end-to-end."""
        mock_resolve.return_value = _make_pending_resolution()

        # Mock only caller.msg — drive the real commands and real services.
        self.initiator_char.msg = MagicMock()
        self.target_char.msg = MagicMock()

        # ----------------------------------------------------------------------
        # 1) Initiator intimidates the target by name (telnet CmdIntimidate).
        # ----------------------------------------------------------------------
        initiate = CmdIntimidate()
        initiate.caller = self.initiator_char
        initiate.args = self.target_char.key
        initiate.raw_string = f"intimidate {self.target_char.key}"
        initiate.func()

        # A real PENDING request exists with the correct initiator/target personas.
        request = SceneActionRequest.objects.get(initiator_persona=self.initiator_persona)
        self.assertEqual(request.status, ActionRequestStatus.PENDING)
        self.assertEqual(request.target_persona, self.target_persona)
        self.assertEqual(request.action_key, "intimidate")
        # create_action_request resolved the template by the registry action's name.
        self.assertEqual(request.action_template, self.action_template)
        self.initiator_char.msg.assert_called()

        # ----------------------------------------------------------------------
        # 2) Target accepts (telnet CmdAccept) — drives full resolution.
        # ----------------------------------------------------------------------
        accept = CmdAccept()
        accept.caller = self.target_char
        accept.args = ""
        accept.func()

        # ----------------------------------------------------------------------
        # 3) The request resolved end-to-end: RESOLVED (no longer PENDING) AND a
        #    real downstream artifact of resolution — the result Interaction —
        #    exists. Mirrors the web E2E's post-accept assertions (sans strain).
        # ----------------------------------------------------------------------
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(request.resolved_at)
        self.assertIsNotNone(
            request.result_interaction,
            "accept must record a result Interaction via the full resolution path",
        )
        self.assertEqual(request.result_interaction.persona, self.initiator_persona)
        self.target_char.msg.assert_called()
