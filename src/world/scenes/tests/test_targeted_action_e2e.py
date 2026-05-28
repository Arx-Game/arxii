"""End-to-end integration test for targeted action with consent + strain.

Exercises the full HTTP flow:

  1. Initiator POSTs /api/action-requests/ with target + technique + strain
     → 201, request PENDING.
  2. Target GETs /api/action-requests/?status=pending → sees the request
     with strain_commitment field populated.
  3. Target POSTs /api/action-requests/<id>/respond/ with decision=accept
     → 200, request RESOLVED.
  4. Assertions on the resolved state:
     - SceneActionRequest.status == RESOLVED
     - result_interaction.strain_committed == 3
     - Initiator's CharacterAnima.current decreased by at least 3.

The test should pass without modifying production code — all the plumbing
landed in earlier Phase 1-5 tasks. If it fails, the failure exposes a real
gap in the integration story.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from rest_framework import status
from rest_framework.test import APIClient

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.models import ActionEnhancement
from actions.types import PendingActionResolution, StepResult
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    SoulfrayConfigFactory,
    SoulfrayContentFactory,
    TechniqueFactory,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.factories import SceneFactory


def _make_pending_resolution() -> PendingActionResolution:
    """Build a minimal PendingActionResolution mock for the resolve pipeline."""
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


@tag("postgres")
class TargetedActionE2EWithStrainTests(TestCase):
    """Initiator dispatches a strain-committing targeted action; target accepts.

    Tagged ``postgres`` because the technique resolution path calls
    ``apply_condition`` (Soulfray) which uses ``DISTINCT ON`` — Postgres-only.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # --- Initiator side: account + character + persona ---
        cls.initiator_account = AccountFactory()
        cls.initiator_character = CharacterFactory()
        cls.initiator_sheet = CharacterSheetFactory(character=cls.initiator_character)
        cls.initiator_persona = cls.initiator_sheet.primary_persona
        cls.initiator_roster = RosterEntryFactory(
            character_sheet__character=cls.initiator_character,
        )
        cls.initiator_player_data = PlayerDataFactory(account=cls.initiator_account)
        cls.initiator_tenure = RosterTenureFactory(
            player_data=cls.initiator_player_data,
            roster_entry=cls.initiator_roster,
        )

        # --- Target side: account + character + persona ---
        cls.target_account = AccountFactory()
        cls.target_character = CharacterFactory()
        cls.target_sheet = CharacterSheetFactory(character=cls.target_character)
        cls.target_persona = cls.target_sheet.primary_persona
        cls.target_roster = RosterEntryFactory(
            character_sheet__character=cls.target_character,
        )
        cls.target_player_data = PlayerDataFactory(account=cls.target_account)
        cls.target_tenure = RosterTenureFactory(
            player_data=cls.target_player_data,
            roster_entry=cls.target_roster,
        )

        # --- Magic plumbing: technique + character knowledge + enhancement ---
        cls.technique = TechniqueFactory(
            name="Aetheric Lash",
            anima_cost=2,
            intensity=1,
            control=1,
            damage_profile=False,
        )
        CharacterTechniqueFactory(character=cls.initiator_sheet, technique=cls.technique)
        ActionEnhancement.objects.create(
            base_action_key="intimidate",
            variant_name="Aetheric Lash Intimidate",
            source_type="technique",
            technique=cls.technique,
        )

        # --- Action template + scene + Soulfray content ---
        cls.action_template = ActionTemplateFactory()
        cls.scene = SceneFactory(is_active=True)
        cls.soulfray_content = SoulfrayContentFactory()
        cls.soulfray_config = SoulfrayConfigFactory()

    def setUp(self) -> None:
        # Patch kudos to avoid loading the social_engagement KudosSourceCategory.
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.mock_award_kudos = self.award_kudos_patcher.start()

        # Fresh anima per test: 10 current, strain=3 is well within cap.
        self.anima = CharacterAnimaFactory(
            character=self.initiator_character,
            current=10,
            maximum=10,
        )
        self.client = APIClient()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    def _dispatch_payload(self) -> dict:
        return {
            "scene": self.scene.pk,
            "initiator_persona": self.initiator_persona.pk,
            "target_persona": self.target_persona.pk,
            "action_key": "intimidate",
            "technique_id": self.technique.pk,
            "strain_commitment": 3,
        }

    @patch("world.scenes.action_services.start_action_resolution")
    def test_e2e_targeted_action_strain_consent(self, mock_resolve: MagicMock) -> None:
        """Initiator dispatches → target reads → target accepts → request resolves with strain."""
        mock_resolve.return_value = _make_pending_resolution()

        # ------------------------------------------------------------------
        # 1) Initiator dispatches the targeted action.
        # ------------------------------------------------------------------
        self.client.force_authenticate(user=self.initiator_account)
        # Wire the action_template via a patch on create_action_request so the
        # resolver path has an ActionTemplate (the create endpoint does not
        # accept action_template directly; resolve requires it). The simplest
        # approach is to set it on the freshly-created request before the
        # target accepts.
        dispatch_response = self.client.post(
            "/api/action-requests/",
            self._dispatch_payload(),
            format="json",
        )
        self.assertEqual(
            dispatch_response.status_code,
            status.HTTP_201_CREATED,
            f"Dispatch failed: {dispatch_response.status_code} {dispatch_response.data}",
        )
        request_id = dispatch_response.data["id"]
        self.assertEqual(dispatch_response.data["strain_commitment"], 3)

        # The endpoint does not expose action_template on create — set it
        # directly so respond_to_action_request can drive the pipeline.
        from world.scenes.action_models import SceneActionRequest

        request = SceneActionRequest.objects.get(pk=request_id)
        request.action_template = self.action_template
        request.save(update_fields=["action_template"])

        # ------------------------------------------------------------------
        # 2) Target reads pending list and sees the request with strain.
        # ------------------------------------------------------------------
        self.client.force_authenticate(user=self.target_account)
        pending_response = self.client.get(
            f"/api/action-requests/?status={ActionRequestStatus.PENDING}",
        )
        self.assertEqual(pending_response.status_code, status.HTTP_200_OK)
        pending_records = pending_response.data["results"]
        matching = [r for r in pending_records if r["id"] == request_id]
        self.assertEqual(
            len(matching),
            1,
            f"Target did not see the pending request. Got: {pending_records}",
        )
        self.assertEqual(matching[0]["strain_commitment"], 3)

        # ------------------------------------------------------------------
        # 3) Target accepts.
        # ------------------------------------------------------------------
        anima_before = self.anima.current
        accept_response = self.client.post(
            f"/api/action-requests/{request_id}/respond/",
            {"decision": "accept"},
            format="json",
        )
        self.assertEqual(
            accept_response.status_code,
            status.HTTP_200_OK,
            f"Respond failed: {accept_response.status_code} {accept_response.data}",
        )

        # ------------------------------------------------------------------
        # 4) Resolution assertions.
        # ------------------------------------------------------------------
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(request.result_interaction)
        self.assertEqual(request.result_interaction.strain_committed, 3)

        self.anima.refresh_from_db()
        # The technique base cost (anima_cost=2 floored by control-intensity=0)
        # plus strain=3 means at least 3 anima was deducted.
        decrease = anima_before - self.anima.current
        self.assertGreaterEqual(
            decrease,
            3,
            f"Initiator anima decreased by {decrease}; expected at least 3.",
        )
