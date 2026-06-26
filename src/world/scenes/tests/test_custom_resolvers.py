"""Tests for the custom action resolver registry."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.conditions.factories import ConditionInstanceFactory, TreatmentTemplateFactory
from world.conditions.types import TreatmentOutcome
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_services import (
    CUSTOM_ACTION_RESOLVERS,
    _resolve_treatment_request,
    register_custom_action_resolver,
)
from world.scenes.factories import SceneActionRequestFactory


class CustomResolverRegistryTests(TestCase):
    def test_register_and_lookup(self):
        def dummy_resolver(request):
            return None

        register_custom_action_resolver("test_action", dummy_resolver)
        self.addCleanup(lambda: CUSTOM_ACTION_RESOLVERS.pop("test_action", None))
        self.assertEqual(CUSTOM_ACTION_RESOLVERS["test_action"], dummy_resolver)


class ResolveTreatmentRequestTests(TestCase):
    def setUp(self):
        self.request = SceneActionRequestFactory(
            action_key="treat_condition",
            status=ActionRequestStatus.PENDING,
        )
        self.request.treatment = TreatmentTemplateFactory()
        self.request.target_condition_instance = ConditionInstanceFactory()
        self.request.save()

    @patch("world.conditions.services.perform_treatment")
    def test_resolve_treatment_records_result(self, mock_perform_treatment):
        mock_perform_treatment.return_value = TreatmentOutcome(
            attempt=MagicMock(),
            outcome=MagicMock(),
            effect_applied=False,
            severity_reduced=0,
            tiers_reduced=0,
            helper_backlash_applied=0,
            target_resolved=True,
        )

        result = _resolve_treatment_request(self.request)

        self.assertIsNone(result)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(self.request.result_interaction)
        self.assertEqual(self.request.resolved_difficulty, 0)
        mock_perform_treatment.assert_called_once()
        mock_perform_treatment.assert_called_once_with(
            helper_sheet=self.request.initiator_persona.character_sheet,
            target_sheet=self.request.target_persona.character_sheet,
            scene=self.request.scene,
            treatment=self.request.treatment,
            target_effect=self.request.target_condition_instance,
            bond_thread=None,
        )

    @patch("world.conditions.services.perform_treatment")
    def test_resolve_treatment_forwards_thread_used(self, mock_perform_treatment):
        from world.magic.factories import ThreadFactory

        thread = ThreadFactory()
        self.request.thread_used = thread
        self.request.save()
        mock_perform_treatment.return_value = TreatmentOutcome(
            attempt=MagicMock(),
            outcome=MagicMock(),
            effect_applied=False,
            severity_reduced=0,
            tiers_reduced=0,
            helper_backlash_applied=0,
            target_resolved=True,
        )

        _resolve_treatment_request(self.request)

        mock_perform_treatment.assert_called_once_with(
            helper_sheet=self.request.initiator_persona.character_sheet,
            target_sheet=self.request.target_persona.character_sheet,
            scene=self.request.scene,
            treatment=self.request.treatment,
            target_effect=self.request.target_condition_instance,
            bond_thread=thread,
        )

    @patch("world.conditions.services.perform_treatment")
    def test_resolve_treatment_no_target_raises(self, mock_perform_treatment):
        self.request.target_condition_instance = None
        self.request.save()

        with self.assertRaises(ValueError):
            _resolve_treatment_request(self.request)

        mock_perform_treatment.assert_not_called()
