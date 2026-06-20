"""Tests for ClassStageHealthRate model."""

from django.db import IntegrityError
from django.test import TestCase

from world.classes.factories import CharacterClassFactory, ClassStageHealthRateFactory
from world.classes.models import ClassStageHealthRate, PathStage


class ClassStageHealthRateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.klass = CharacterClassFactory()
        cls.rate = ClassStageHealthRateFactory(
            character_class=cls.klass, stage=PathStage.PROSPECT, health_per_level=10
        )

    def test_reverse_accessor(self):
        self.assertEqual(list(self.klass.stage_health_rates.all()), [self.rate])

    def test_unique_per_class_stage(self):
        with self.assertRaises(IntegrityError):
            ClassStageHealthRate.objects.create(
                character_class=self.klass, stage=PathStage.PROSPECT, health_per_level=5
            )
