"""Tests for the technique unlock target and TechniqueKnownRequirement (#4097).

AbstractUnlockRequirement now supports a fourth polymorphic unlock target,
``technique``, alongside class_level_unlock / thread_crossing_threshold / path.
Exactly one of the four must be set, enforced by a CheckConstraint.

LegendRequirement and ItemRequirement deliberately keep a narrower two-way
target (class_level_unlock XOR thread_crossing_threshold only, never path or
technique) via their own Meta.constraints, not the base's four-way one (fix
round 1: the base constraint never applied to them, since each defines its own
Meta.constraints without subclassing the abstract base's Meta).
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.classes.factories import CharacterClassFactory
from world.items.factories import ItemTemplateFactory
from world.magic.factories import TechniqueFactory
from world.progression.models import (
    ClassLevelUnlock,
    ItemRequirement,
    LegendRequirement,
    TechniqueKnownRequirement,
)


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


class NarrowerTargetRequirementsRejectTechniqueTests(TestCase):
    """LegendRequirement and ItemRequirement never accept path/technique (fix round 1)."""

    @classmethod
    def setUpTestData(cls):
        character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=character_class, target_level=5
        )
        cls.technique = TechniqueFactory()

    def test_legend_requirement_with_technique_and_unlock_is_rejected(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            LegendRequirement.objects.create(
                class_level_unlock=self.unlock,
                technique=self.technique,
                minimum_legend=1,
            )

    def test_item_requirement_with_technique_and_unlock_is_rejected(self):
        template = ItemTemplateFactory()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            ItemRequirement.objects.create(
                class_level_unlock=self.unlock,
                technique=self.technique,
                item_template=template,
            )
