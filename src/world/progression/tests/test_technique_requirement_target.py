"""Tests for the technique unlock target and TechniqueKnownRequirement (#4097).

AbstractUnlockRequirement now supports a fourth polymorphic unlock target —
``technique`` — alongside class_level_unlock / thread_crossing_threshold / path.
Exactly one of the four must be set, enforced by a CheckConstraint.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.magic.factories import TechniqueFactory
from world.progression.models import TechniqueKnownRequirement


class TechniqueTargetConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.target = TechniqueFactory()
        cls.prereq = TechniqueFactory(gift=cls.target.gift)

    def test_technique_target_alone_is_valid(self):
        req = TechniqueKnownRequirement.objects.create(
            technique=self.target, required_technique=self.prereq
        )
        assert req.pk is not None

    def test_no_target_is_rejected(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TechniqueKnownRequirement.objects.create(required_technique=self.prereq)
