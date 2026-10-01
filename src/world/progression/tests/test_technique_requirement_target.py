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

from django.core.exceptions import ValidationError
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


class TechniqueKnownRequirementSelfReferenceTests(TestCase):
    """A technique cannot require itself, directly or through a cycle (#4097 fix round 2)."""

    @classmethod
    def setUpTestData(cls):
        cls.target = TechniqueFactory()

    def test_db_constraint_rejects_direct_self_reference(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TechniqueKnownRequirement.objects.create(
                technique=self.target, required_technique=self.target
            )

    def test_clean_rejects_direct_self_reference(self):
        req = TechniqueKnownRequirement(technique=self.target, required_technique=self.target)
        with self.assertRaises(ValidationError):
            req.full_clean()

    def test_clean_rejects_transitive_cycle(self):
        """A requires B already; a row making B require A would close a cycle."""
        technique_a = self.target
        technique_b = TechniqueFactory()
        TechniqueKnownRequirement.objects.create(
            technique=technique_a, required_technique=technique_b
        )

        cyclical = TechniqueKnownRequirement(technique=technique_b, required_technique=technique_a)
        with self.assertRaises(ValidationError):
            cyclical.full_clean()

    def test_clean_allows_a_genuine_non_cyclical_chain(self):
        """A requires B, B requires C — no cycle, clean() does not object."""
        technique_a = self.target
        technique_b = TechniqueFactory()
        technique_c = TechniqueFactory()
        TechniqueKnownRequirement.objects.create(
            technique=technique_a, required_technique=technique_b
        )

        chained = TechniqueKnownRequirement(technique=technique_b, required_technique=technique_c)
        chained.full_clean()  # does not raise
