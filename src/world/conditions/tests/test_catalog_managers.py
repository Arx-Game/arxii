"""Tests for the CachedAllMixin managers added to CapabilityType/ConditionStage (#1871)."""

from django.test import TestCase

from world.conditions.factories import CapabilityTypeFactory, ConditionStageFactory
from world.conditions.models import CapabilityType, ConditionStage


class CapabilityTypeCachedAllTests(TestCase):
    def setUp(self) -> None:
        CapabilityType.objects.flush_all_cache()
        CapabilityType.flush_instance_cache()

    def test_second_call_hits_identity_map_zero_queries(self) -> None:
        CapabilityTypeFactory(name="movement")
        CapabilityType.objects.flush_all_cache()
        CapabilityType.flush_instance_cache()
        CapabilityType.objects.cached_all()  # prime
        with self.assertNumQueries(0):
            CapabilityType.objects.cached_all()

    def test_returns_every_row(self) -> None:
        first = CapabilityTypeFactory(name="movement")
        second = CapabilityTypeFactory(name="speed")
        result = CapabilityType.objects.cached_all()
        self.assertCountEqual([r.pk for r in result], [first.pk, second.pk])


class ConditionStageCachedAllTests(TestCase):
    def setUp(self) -> None:
        ConditionStage.objects.flush_all_cache()
        ConditionStage.flush_instance_cache()

    def test_second_call_hits_identity_map_zero_queries(self) -> None:
        ConditionStageFactory()
        ConditionStage.objects.flush_all_cache()
        ConditionStage.flush_instance_cache()
        ConditionStage.objects.cached_all()  # prime
        with self.assertNumQueries(0):
            ConditionStage.objects.cached_all()

    def test_returns_every_row(self) -> None:
        first = ConditionStageFactory()
        second = ConditionStageFactory()
        result = ConditionStage.objects.cached_all()
        self.assertCountEqual([r.pk for r in result], [first.pk, second.pk])
