"""End-to-end web tests for the treat_condition consent flow (#1486 Task 8).

Unlike the sibling ``test_treatment_action_views.py`` unit tests, these run the
REAL consent → resolver → ``perform_treatment`` → ``decay_condition_severity``
chain through to a visible severity change. Only the non-deterministic dice
(``perform_check``) is pinned to a success-level-1 ``CheckResult``; every gate
(scene/engagement/bond/duplicate/cost) and the reduction itself runs un-mocked,
mirroring ``test_treatment_aftermath.py`` / ``test_treatment_mage_scar.py``.

Flows: GET discovery → POST create (PENDING) → POST respond (target accepts)
→ severity reduced + request RESOLVED + result interaction recorded.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import TARGET_EFFECT_CONDITION, TreatmentTargetKind
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckOutcomeFactory


def _make_check_result(success_level: int):
    """Build a mock CheckResult with a real CheckOutcome row.

    Copied from ``test_treatment_aftermath.py`` / ``test_treatment_mage_scar.py``:
    pins only the non-deterministic ``perform_check`` outcome while leaving
    every other gate + the reduction REAL.
    """
    outcome = CheckOutcomeFactory(
        name=f"Outcome_sl_{success_level}_{id(object())}",
        success_level=success_level,
    )
    result = MagicMock()
    result.outcome = outcome
    result.success_level = success_level
    return result


def _give_account_character(account, character) -> None:
    """Wire ``account`` so ``get_account_personas`` returns the character's persona.

    Mirrors the helper in ``test_treatment_views.py`` /
    ``test_treatment_action_views.py``: a PlayerData with a RosterTenure on a
    RosterEntry whose CharacterSheet points at the character, so both the
    account-based ``get_account_personas`` and the ``X-Character-ID``-based
    ``CharacterContextMixin`` ownership checks pass.
    """
    player_data = PlayerDataFactory(account=account)
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)


class TreatConditionWebConsentE2ETests(TestCase):
    """Web E2E: discovery → create → respond runs the real reduction chain."""

    def setUp(self) -> None:
        # Evennia ObjectDB fixtures must be built in setUp, not setUpTestData:
        # the idmapper's DbHolder is un-deepcopyable, so the classmethod
        # snapshot machinery raises copy.Error (the DbHolder setUpTestData trap;
        # see test_treatment_views.py for the same note).
        self.room = ObjectDBFactory(
            db_key="Clinic",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.helper_char = CharacterFactory(location=self.room)
        self.target_char = CharacterFactory(location=self.room)
        self.helper_sheet = CharacterSheetFactory(character=self.helper_char)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)

        # Two accounts wired via the roster: helper (POSTs the request) and
        # target (POSTs the respond). Both need roster wiring so the
        # account-based get_account_personas resolves their personas.
        self.helper_account = AccountFactory()
        _give_account_character(self.helper_account, self.helper_char)
        self.target_account = AccountFactory()
        _give_account_character(self.target_account, self.target_char)

        self.scene = SceneFactory(is_active=True, location=self.room)
        # Bust the per-location active-scene cache.
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache

        self.condition = ConditionTemplateFactory(name="Test Ailment")
        # TreatmentTemplateFactory defaults reduction_on_success=3; a severity-5
        # instance → 2 after a success (reduced but still open — the strongest
        # "it actually treated" signal: both the drop AND "still present").
        self.treatment = TreatmentTemplateFactory(
            target_condition=self.condition,
            target_kind=TreatmentTargetKind.PRIMARY,
            requires_bond=False,
            scene_required=True,
        )
        self.instance = ConditionInstanceFactory(
            target=self.target_char,
            condition=self.condition,
            severity=5,
        )

        self.client = APIClient()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _gate_patches(self):
        """The same scene-participant + engagement patches the sibling tests use.

        Returns a stack of patchers (started) so the real gate suite passes
        without requiring full roster→scene-participation wiring.
        """
        scene_patch = patch("world.conditions.services._scene_participant", return_value=True)
        engagement_patch = patch(
            "world.mechanics.engagement.CharacterEngagement.objects.filter",
            return_value=MagicMock(exists=MagicMock(return_value=False)),
        )
        check_patch = patch(
            "world.checks.services.perform_check",
            return_value=_make_check_result(success_level=1),
        )
        scene_patch.start()
        engagement_patch.start()
        check_patch.start()
        self.addCleanup(scene_patch.stop)
        self.addCleanup(engagement_patch.stop)
        self.addCleanup(check_patch.stop)

    def _discovery_url(self) -> str:
        return "/api/conditions/treatments/"

    def _create_url(self) -> str:
        return reverse("sceneactionrequest-list")

    def _respond_url(self, pk: int) -> str:
        return reverse("sceneactionrequest-respond", kwargs={"pk": pk})

    # ------------------------------------------------------------------
    # E2E test
    # ------------------------------------------------------------------

    def test_discovery_create_respond_reduces_severity_and_resolves(self) -> None:
        """Full web consent chain runs perform_treatment REAL and reduces severity.

        GET discovery → 200 with candidates; POST create → 201 PENDING with
        treatment FKs; target POSTs respond (accept) → custom resolver fires →
        perform_treatment → decay_condition_severity (REAL). Asserts: severity
        dropped by reduction_on_success (3) and instance still open, request
        RESOLVED, result interaction recorded on the scene.
        """
        self._gate_patches()

        # 1. Discovery: helper account + X-Character-ID header → candidates.
        self.client.force_authenticate(user=self.helper_account)
        discovery_response = self.client.get(
            self._discovery_url(),
            {"target_persona_id": self.target_sheet.primary_persona.pk},
            HTTP_X_CHARACTER_ID=str(self.helper_char.id),
        )
        assert discovery_response.status_code == status.HTTP_200_OK, discovery_response.data
        candidates = discovery_response.data["candidates"]
        assert len(candidates) == 1, candidates
        candidate = candidates[0]
        assert candidate["target_effect_type"] == TARGET_EFFECT_CONDITION
        assert candidate["treatment"]["name"] == self.treatment.name
        assert candidate["target_effect"]["id"] == self.instance.id

        # 2. Create: helper POSTs the treat_condition request → 201 PENDING.
        create_payload = {
            "scene": self.scene.pk,
            "initiator_persona": self.helper_sheet.primary_persona.pk,
            "target_persona": self.target_sheet.primary_persona.pk,
            "action_key": "treat_condition",
            "treatment_id": self.treatment.pk,
            "target_condition_instance_id": self.instance.pk,
        }
        create_response = self.client.post(self._create_url(), create_payload, format="json")
        assert create_response.status_code == status.HTTP_201_CREATED, create_response.data
        request_pk = create_response.data["id"]
        request = SceneActionRequest.objects.get(pk=request_pk)
        assert request.status == ActionRequestStatus.PENDING
        assert request.treatment_id == self.treatment.pk
        assert request.target_condition_instance_id == self.instance.pk
        assert request.target_persona_id == self.target_sheet.primary_persona.pk

        # 3. Respond: target account authenticates and accepts → resolver fires.
        self.client.force_authenticate(user=self.target_account)
        respond_response = self.client.post(
            self._respond_url(request_pk),
            {"decision": ConsentDecision.ACCEPT},
            format="json",
        )
        assert respond_response.status_code == status.HTTP_200_OK, respond_response.data

        # Severity dropped by reduction_on_success (3): 5 → 2, still open.
        self.instance.refresh_from_db()
        assert self.instance.severity == 2, self.instance.severity
        assert self.instance.resolved_at is None, "partial reduction must leave the condition OPEN"

        # Request flipped to RESOLVED; a result interaction was recorded.
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED
        assert request.result_interaction_id is not None
        from world.scenes.models import Interaction

        interaction = Interaction.objects.get(pk=request.result_interaction_id)
        assert interaction.scene_id == self.scene.pk
        assert interaction.persona_id == self.helper_sheet.primary_persona.pk

        # The recorded pose names the helper and target, not generic placeholders.
        assert self.helper_sheet.primary_persona.name in interaction.content
        assert self.target_sheet.primary_persona.name in interaction.content
        assert "someone" not in interaction.content
        assert "the target" not in interaction.content

        # Sanity: no stray second instance was created on the target.
        assert (
            ConditionInstance.objects.filter(
                target=self.target_char,
                condition=self.condition,
            ).count()
            == 1
        )
