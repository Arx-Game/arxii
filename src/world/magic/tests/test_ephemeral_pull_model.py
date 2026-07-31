"""Tests for the EphemeralPullCapabilityGrant sidecar model (#2840)."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import CapabilityType
from world.conditions.services import apply_condition
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
    ThreadFactory,
)
from world.magic.models import EphemeralPullCapabilityGrant


class EphemeralPullCapabilityGrantModelTest(TestCase):
    """Model field and constraint tests."""

    def _setup(self):
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet,
            resonance=resonance,
            balance=10,
            lifetime_earned=10,
        )
        thread = ThreadFactory(owner=sheet, resonance=resonance)
        return sheet, thread

    def test_can_create_sidecar_row(self):
        """A sidecar row can be created FK'd to a ConditionInstance."""
        sheet, thread = self._setup()
        template = ConditionTemplateFactory(name="Test Surge")
        result = apply_condition(sheet.character, template)
        cap = CapabilityType.objects.create(name="Test Cap", innate_baseline=0)

        grant = EphemeralPullCapabilityGrant.objects.create(
            condition_instance=result.instance,
            character_sheet=sheet,
            capability=cap,
            grant_value=5,
            source_thread=thread,
            source_thread_level=10,
            source_tier=2,
        )
        self.assertEqual(grant.grant_value, 5)
        self.assertEqual(grant.capability, cap)
        self.assertEqual(grant.source_thread, thread)
        self.assertEqual(grant.source_thread_level, 10)
        self.assertEqual(grant.source_tier, 2)

    def test_unique_constraint_condition_instance_capability(self):
        """Duplicate (condition_instance, capability) raises IntegrityError."""
        sheet, thread = self._setup()
        template = ConditionTemplateFactory(name="Test Surge 2")
        result = apply_condition(sheet.character, template)
        cap = CapabilityType.objects.create(name="Test Cap 2", innate_baseline=0)

        EphemeralPullCapabilityGrant.objects.create(
            condition_instance=result.instance,
            character_sheet=sheet,
            capability=cap,
            grant_value=5,
            source_thread=thread,
            source_thread_level=10,
            source_tier=2,
        )
        with self.assertRaises(IntegrityError):
            EphemeralPullCapabilityGrant.objects.create(
                condition_instance=result.instance,
                character_sheet=sheet,
                capability=cap,
                grant_value=3,
                source_thread=thread,
                source_thread_level=10,
                source_tier=1,
            )

    def test_cascade_delete_with_condition_instance(self):
        """When the ConditionInstance is deleted, the sidecar goes with it."""
        sheet, thread = self._setup()
        template = ConditionTemplateFactory(name="Test Surge 3")
        result = apply_condition(sheet.character, template)
        cap = CapabilityType.objects.create(name="Test Cap 3", innate_baseline=0)

        grant = EphemeralPullCapabilityGrant.objects.create(
            condition_instance=result.instance,
            character_sheet=sheet,
            capability=cap,
            grant_value=5,
            source_thread=thread,
            source_thread_level=10,
            source_tier=2,
        )
        result.instance.delete()
        self.assertFalse(EphemeralPullCapabilityGrant.objects.filter(pk=grant.pk).exists())
