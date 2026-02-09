"""Tests for attempt system models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.attempts.factories import (
    AttemptCategoryFactory,
    AttemptConsequenceFactory,
    AttemptTemplateFactory,
)
from world.attempts.models import AttemptCategory, AttemptConsequence, AttemptTemplate
from world.checks.factories import CheckTypeFactory
from world.traits.factories import CheckOutcomeFactory


class AttemptCategoryTests(TestCase):
    """Test AttemptCategory model."""

    def test_str_returns_name(self):
        category = AttemptCategoryFactory(name="Infiltration")
        assert str(category) == "Infiltration"

    def test_unique_name(self):
        AttemptCategoryFactory(name="Infiltration")
        with self.assertRaises(IntegrityError):
            AttemptCategory.objects.create(name="Infiltration", display_order=99)


class AttemptTemplateTests(TestCase):
    """Test AttemptTemplate model."""

    @classmethod
    def setUpTestData(cls):
        cls.category = AttemptCategoryFactory(name="TestCategory")
        cls.check_type = CheckTypeFactory(name="TestStealth")

    def test_str_returns_name(self):
        template = AttemptTemplateFactory(
            name="Sneak Past Guard",
            category=self.category,
            check_type=self.check_type,
        )
        assert str(template) == "Sneak Past Guard"

    def test_unique_name_within_category(self):
        AttemptTemplateFactory(
            name="Sneak Past Guard",
            category=self.category,
            check_type=self.check_type,
        )
        with self.assertRaises(IntegrityError):
            AttemptTemplate.objects.create(
                name="Sneak Past Guard",
                category=self.category,
                check_type=self.check_type,
            )

    def test_inactive_templates_filtered(self):
        AttemptTemplateFactory(
            name="Active",
            category=self.category,
            check_type=self.check_type,
            is_active=True,
        )
        AttemptTemplateFactory(
            name="Inactive",
            category=self.category,
            check_type=self.check_type,
            is_active=False,
        )
        active = AttemptTemplate.objects.filter(is_active=True)
        assert active.count() == 1
        assert active.first().name == "Active"


class AttemptConsequenceTests(TestCase):
    """Test AttemptConsequence model."""

    @classmethod
    def setUpTestData(cls):
        cls.check_type = CheckTypeFactory(name="TestConseqCheck")
        cls.template = AttemptTemplateFactory(
            name="TestConseqTemplate",
            check_type=cls.check_type,
        )
        cls.outcome = CheckOutcomeFactory(name="TestCatastrophic", success_level=-5)

    def test_str_representation(self):
        consequence = AttemptConsequenceFactory(
            attempt_template=self.template,
            outcome_tier=self.outcome,
            label="Guard raises alarm",
        )
        assert "TestConseqTemplate" in str(consequence)
        assert "Guard raises alarm" in str(consequence)

    def test_default_weight_is_one(self):
        consequence = AttemptConsequence.objects.create(
            attempt_template=self.template,
            outcome_tier=self.outcome,
            label="Default weight test",
        )
        assert consequence.weight == 1

    def test_default_character_loss_is_false(self):
        consequence = AttemptConsequence.objects.create(
            attempt_template=self.template,
            outcome_tier=self.outcome,
            label="Default loss test",
        )
        assert consequence.character_loss is False

    def test_unique_together_template_and_label(self):
        AttemptConsequence.objects.create(
            attempt_template=self.template,
            outcome_tier=self.outcome,
            label="Same label",
        )
        with self.assertRaises(IntegrityError):
            AttemptConsequence.objects.create(
                attempt_template=self.template,
                outcome_tier=self.outcome,
                label="Same label",
            )

    def test_multiple_consequences_per_tier(self):
        AttemptConsequenceFactory(
            attempt_template=self.template,
            outcome_tier=self.outcome,
            label="Consequence A",
        )
        AttemptConsequenceFactory(
            attempt_template=self.template,
            outcome_tier=self.outcome,
            label="Consequence B",
        )
        assert self.template.consequences.filter(outcome_tier=self.outcome).count() == 2

    def test_character_loss_consequence(self):
        consequence = AttemptConsequenceFactory(
            attempt_template=self.template,
            outcome_tier=self.outcome,
            label="Killed by guard",
            character_loss=True,
        )
        assert consequence.character_loss is True

    def test_weight_zero_fails_validation(self):
        """Weight=0 would crash random.choices, so MinValueValidator(1) rejects it."""
        consequence = AttemptConsequence(
            attempt_template=self.template,
            outcome_tier=self.outcome,
            label="Zero weight",
            weight=0,
        )
        with self.assertRaises(ValidationError):
            consequence.full_clean()
