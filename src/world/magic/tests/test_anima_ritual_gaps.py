"""Tests for three backend gaps in the Anima Ritual UI feature.

Gap 1: anima_recovery field in EnhancedSceneActionResultSerializer
Gap 2: author_account_id + scene_action_config in RitualSerializer
Gap 3: PATCH support on RitualViewSet
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.conditions.factories import ConditionTemplateFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    CharacterAnimaFactory,
    RitualFactory,
    RitualSceneActionConfigFactory,
    SoulfrayConfigFactory,
)
from world.magic.serializers import RitualSerializer
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_serializers import EnhancedSceneActionResultSerializer
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory
from world.scenes.types import EnhancedSceneActionResult
from world.traits.factories import CheckOutcomeFactory

_PERFORM_CHECK_PATCH = "world.scenes.action_services.start_action_resolution"
_AWARD_KUDOS_PATCH = "world.scenes.action_services.award_kudos"


def _make_pending_resolution(outcome_row: object) -> PendingActionResolution:
    """Build a PendingActionResolution wrapping a real CheckOutcome row."""
    check_type = CheckTypeFactory()
    check_result = CheckResult(
        check_type=check_type,
        outcome=outcome_row,  # type: ignore[arg-type]
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=15,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


def _make_scene_action_ritual():
    """Create a SCENE_ACTION Ritual + RitualSceneActionConfig sidecar."""
    ritual = RitualFactory(
        execution_kind=RitualExecutionKind.SCENE_ACTION,
        service_function_path="",
        flow=None,
    )
    RitualSceneActionConfigFactory(ritual=ritual)
    return ritual


# =============================================================================
# Gap 1: anima_recovery field in EnhancedSceneActionResultSerializer
# =============================================================================


class AnimaRecoverySerializerFieldTests(TestCase):
    """Gap 1: anima_recovery is populated for initiator only on anima_ritual accept."""

    def setUp(self) -> None:
        from world.magic.services import anima_ritual_action  # noqa: F401

        self.award_kudos_patcher = patch(_AWARD_KUDOS_PATCH)
        self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    def _setup(self, success_level: int = 1) -> tuple:
        """Create a full ritual+scene setup and return (action_request, outcome)."""
        persona = PersonaFactory()
        sheet = persona.character_sheet
        target_persona = PersonaFactory()

        ritual = _make_scene_action_ritual()
        CharacterAnimaFactory(character=sheet.character, current=2, maximum=10)
        ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        SoulfrayConfigFactory(
            ritual_budget_critical_success=10,
            ritual_budget_success=6,
            ritual_budget_partial=3,
            ritual_budget_failure=1,
            ritual_severity_cost_per_point=1,
        )
        scene = SceneFactory(is_active=True)
        outcome = CheckOutcomeFactory(
            name=f"GapOutcome_sl{success_level}_{id(object())}",
            success_level=success_level,
        )
        action_template = ActionTemplateFactory()
        action_request = SceneActionRequestFactory(
            scene=scene,
            initiator_persona=persona,
            target_persona=target_persona,
            action_key="anima_ritual",
            status=ActionRequestStatus.PENDING,
        )
        action_request.action_template = action_template
        action_request.snapshot_ritual = ritual
        action_request.save(update_fields=["action_template", "snapshot_ritual"])
        return action_request, outcome

    def test_resolver_attaches_anima_recovery_payload_to_action_request(self) -> None:
        """After accept, the resolver attaches _anima_recovery_payload to action_request."""
        action_request, outcome = self._setup(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            result = respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        self.assertIsNotNone(result)
        payload = getattr(action_request, "_anima_recovery_payload", None)  # noqa: GETATTR_LITERAL — transient attr set by resolver
        self.assertIsNotNone(payload)
        # success budget=6, anima goes from 2 to 8
        self.assertEqual(payload["recovered"], 6)
        self.assertEqual(payload["soulfray_reduced"], 0)
        self.assertEqual(payload["new_pool"], 8)

    def test_serializer_returns_recovery_when_user_matches_initiator(self) -> None:
        """Serializer returns anima_recovery when request.user is initiator_account."""
        action_request, outcome = self._setup(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            result = respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        self.assertIsNotNone(result)
        # Link a real AccountDB to the initiator character then use it as request.user.
        initiator_account = AccountFactory()
        character = action_request.initiator_persona.character_sheet.character
        character.db_account = initiator_account
        character.save(update_fields=["db_account"])

        mock_request = MagicMock()
        mock_request.user = initiator_account
        data = EnhancedSceneActionResultSerializer(
            result,
            context={"request": mock_request, "action_request": action_request},
        ).data

        self.assertIn("anima_recovery", data)
        recovery = data["anima_recovery"]
        self.assertIsNotNone(recovery)
        self.assertEqual(recovery["recovered"], 6)
        self.assertEqual(recovery["soulfray_reduced"], 0)
        self.assertEqual(recovery["new_pool"], 8)

    def test_target_does_not_see_anima_recovery(self) -> None:
        """Non-initiator account does not see anima_recovery (disguise)."""
        action_request, outcome = self._setup(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            result = respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        self.assertIsNotNone(result)
        # Link a real initiator account, but pass a different account as request.user.
        initiator_account = AccountFactory()
        other_account = AccountFactory()
        character = action_request.initiator_persona.character_sheet.character
        character.db_account = initiator_account
        character.save(update_fields=["db_account"])

        mock_request = MagicMock()
        mock_request.user = other_account  # NOT the initiator
        data = EnhancedSceneActionResultSerializer(
            result,
            context={"request": mock_request, "action_request": action_request},
        ).data

        self.assertIsNone(data["anima_recovery"])

    def test_non_anima_action_key_returns_null_recovery(self) -> None:
        """Non-anima action_key requests return null anima_recovery."""
        action_request, _outcome = self._setup(success_level=1)
        initiator_account = action_request.initiator_persona.character_sheet.character.db_account

        # Build a result with a different action_key
        mock_action_resolution = MagicMock()
        result = EnhancedSceneActionResult(
            action_resolution=mock_action_resolution,
            action_key="persuade",
        )
        mock_request = MagicMock()
        mock_request.user = initiator_account
        data = EnhancedSceneActionResultSerializer(
            result,
            context={"request": mock_request, "action_request": action_request},
        ).data
        self.assertIsNone(data["anima_recovery"])

    def test_anima_recovery_absent_without_context(self) -> None:
        """Without request/action_request context, anima_recovery is None."""
        mock_action_resolution = MagicMock()
        result = EnhancedSceneActionResult(
            action_resolution=mock_action_resolution,
            action_key="anima_ritual",
        )
        data = EnhancedSceneActionResultSerializer(result).data
        self.assertIsNone(data["anima_recovery"])


# =============================================================================
# Gap 2: author_account_id + scene_action_config in RitualSerializer
# =============================================================================


class RitualSerializerFieldTests(TestCase):
    """Gap 2: author_account_id and scene_action_config exposed in RitualSerializer."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.service_ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SERVICE,
            service_function_path="world.magic.services.spend_resonance_for_imbuing",
            author_account=cls.account,
        )
        cls.scene_action_ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=cls.account,
        )
        cls.config = RitualSceneActionConfigFactory(ritual=cls.scene_action_ritual)
        cls.staff_ritual = RitualFactory(
            author_account=None,  # staff-authored
        )

    def test_service_ritual_has_null_scene_action_config(self) -> None:
        """SERVICE rituals return null for scene_action_config."""
        data = RitualSerializer(self.service_ritual).data
        self.assertIsNone(data["scene_action_config"])

    def test_scene_action_ritual_has_nested_config(self) -> None:
        """SCENE_ACTION rituals return a nested scene_action_config object."""
        data = RitualSerializer(self.scene_action_ritual).data
        config = data["scene_action_config"]
        self.assertIsNotNone(config)
        self.assertIn("id", config)
        self.assertIn("stat", config)
        self.assertIn("stat_name", config)
        self.assertIn("skill", config)
        self.assertIn("skill_name", config)
        self.assertIn("target_difficulty", config)

    def test_author_account_id_is_returned(self) -> None:
        """author_account_id is the FK PK of the author account."""
        data = RitualSerializer(self.scene_action_ritual).data
        self.assertEqual(data["author_account_id"], self.account.pk)

    def test_staff_authored_ritual_has_null_author_account_id(self) -> None:
        """Staff-authored rituals return null for author_account_id."""
        data = RitualSerializer(self.staff_ritual).data
        self.assertIsNone(data["author_account_id"])


# =============================================================================
# Gap 3: PATCH support on RitualViewSet
# =============================================================================


class RitualViewSetPatchTests(APITestCase):
    """Gap 3: Author can PATCH their ritual; non-author/non-staff 403."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.author_account = AccountFactory()
        cls.other_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SERVICE,
            service_function_path="world.magic.services.spend_resonance_for_imbuing",
            author_account=cls.author_account,
            name="Authored Ritual",
        )
        cls.staff_ritual = RitualFactory(
            author_account=None,  # staff-authored
            name="Staff Ritual",
        )

        # SCENE_ACTION ritual for nested config patch tests
        cls.scene_ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=cls.author_account,
            name="Scene Ritual",
        )
        cls.scene_config = RitualSceneActionConfigFactory(ritual=cls.scene_ritual)

    def _patch_url(self, pk: int) -> str:
        return reverse("magic:ritual-detail", kwargs={"pk": pk})

    def test_author_can_patch_name(self) -> None:
        """Ritual author can PATCH name."""
        self.client.force_authenticate(user=self.author_account)
        resp = self.client.patch(
            self._patch_url(self.ritual.pk),
            {"name": "Updated Name"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ritual.refresh_from_db()
        self.assertEqual(self.ritual.name, "Updated Name")

    def test_non_author_cannot_patch(self) -> None:
        """Non-author account receives 403 on PATCH."""
        self.client.force_authenticate(user=self.other_account)
        resp = self.client.patch(
            self._patch_url(self.ritual.pk),
            {"name": "Stolen Name"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_patch_any_ritual(self) -> None:
        """Staff account can PATCH any ritual regardless of author."""
        self.client.force_authenticate(user=self.staff_account)
        resp = self.client.patch(
            self._patch_url(self.ritual.pk),
            {"description": "Staff update"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_staff_authored_ritual_non_staff_cannot_patch(self) -> None:
        """Staff-authored (author_account=None) ritual cannot be PATCHed by non-staff."""
        self.client.force_authenticate(user=self.other_account)
        resp = self.client.patch(
            self._patch_url(self.staff_ritual.pk),
            {"name": "Hacked"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_nested_scene_action_config_target_difficulty(self) -> None:
        """Author can PATCH the nested scene_action_config target_difficulty."""
        self.client.force_authenticate(user=self.author_account)
        resp = self.client.patch(
            self._patch_url(self.scene_ritual.pk),
            {"scene_action_config": {"target_difficulty": 5}},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.json())
        self.scene_config.refresh_from_db()
        self.assertEqual(self.scene_config.target_difficulty, 5)

    def test_get_returns_author_account_id_and_config(self) -> None:
        """GET on a SCENE_ACTION ritual includes author_account_id and scene_action_config."""
        self.client.force_authenticate(user=self.author_account)
        resp = self.client.get(self._patch_url(self.scene_ritual.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["author_account_id"], self.author_account.pk)
        self.assertIsNotNone(data["scene_action_config"])

    def test_delete_not_allowed(self) -> None:
        """DELETE is not allowed (http_method_names excludes delete)."""
        self.client.force_authenticate(user=self.author_account)
        resp = self.client.delete(self._patch_url(self.ritual.pk))
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
