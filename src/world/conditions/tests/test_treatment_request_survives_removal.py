"""A treat request keeps its record when play deletes the condition it aimed at (#4475)."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.conditions.services import clear_all_conditions, process_round_end
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.factories import SceneActionRequestFactory
from world.scenes.models import SceneActionRequest


class TreatRequestSurvivesRemovalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.target = ObjectDBFactory(db_key="Ysmay")
        CharacterSheetFactory(character=cls.target)
        cls.fever = ConditionTemplateFactory(
            name="Marsh Fever", default_duration_type=DurationType.ROUNDS, default_duration_value=1
        )
        cls.treatment = TreatmentTemplateFactory(target_condition=cls.fever)

    def _request(self, instance, status):
        return SceneActionRequestFactory(
            action_key="treat_condition",
            treatment=self.treatment,
            target_condition_instance=instance,
            status=status,
        )

    def test_saving_snapshots_the_condition(self):
        instance = ConditionInstanceFactory(target=self.target, condition=self.fever)
        request = self._request(instance, ActionRequestStatus.PENDING)
        assert request.target_condition_name == "Marsh Fever"
        assert request.target_condition_template == self.fever

    def test_bulk_clear_expires_open_requests_and_keeps_resolved_ones(self):
        instance = ConditionInstanceFactory(target=self.target, condition=self.fever)
        open_one = self._request(instance, ActionRequestStatus.PENDING)
        done = self._request(instance, ActionRequestStatus.RESOLVED)

        clear_all_conditions(self.target)

        open_one = SceneActionRequest.objects.get(pk=open_one.pk)
        done = SceneActionRequest.objects.get(pk=done.pk)
        assert open_one.status == ActionRequestStatus.EXPIRED
        assert done.status == ActionRequestStatus.RESOLVED
        for kept in (open_one, done):
            assert kept.target_condition_instance_id is None
            assert kept.target_condition_name == "Marsh Fever"

    def test_expiry_at_round_end_does_not_raise(self):
        instance = ConditionInstanceFactory(
            target=self.target, condition=self.fever, rounds_remaining=1
        )
        request = self._request(instance, ActionRequestStatus.PENDING)

        process_round_end(self.target)

        request = SceneActionRequest.objects.get(pk=request.pk)
        assert request.status == ActionRequestStatus.EXPIRED
        assert request.target_condition_name == "Marsh Fever"

    def test_a_row_without_a_snapshot_gets_one_when_its_condition_goes(self):
        instance = ConditionInstanceFactory(target=self.target, condition=self.fever)
        request = self._request(instance, ActionRequestStatus.RESOLVED)
        # A row the previous release wrote: no snapshot in the database or the cache.
        request.target_condition_name = ""
        request.target_condition_template = None
        SceneActionRequest.objects.filter(pk=request.pk).update_with_reason(
            reason="test: simulate a row written before the snapshot columns existed",
            target_condition_name="",
            target_condition_template=None,
        )

        instance.delete()

        request = SceneActionRequest.objects.get(pk=request.pk)
        assert request.target_condition_name == "Marsh Fever"
        assert request.target_condition_template_id == self.fever.pk
