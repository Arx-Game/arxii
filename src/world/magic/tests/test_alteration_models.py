"""Tests for MagicalAlterationTemplate, PendingAlteration, and MagicalAlterationEvent models."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.magic.constants import AlterationTier, PendingAlterationStatus
from world.magic.factories import AffinityFactory, ResonanceFactory, TechniqueFactory
from world.magic.models import MagicalAlterationEvent, MagicalAlterationTemplate, PendingAlteration


class MagicalAlterationTemplateTests(TestCase):
    """Tests for MagicalAlterationTemplate model."""

    def setUp(self) -> None:
        self.affinity = AffinityFactory()
        self.resonance = ResonanceFactory(affinity=self.affinity)
        self.condition_template = ConditionTemplateFactory()

    def test_create_minimal(self) -> None:
        """Can create a template with required fields only."""
        template = MagicalAlterationTemplate.objects.create(
            condition_template=self.condition_template,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        self.assertIsNotNone(template.pk)

    def test_create_with_all_fields(self) -> None:
        """Can create a template with all optional fields populated."""
        template = MagicalAlterationTemplate.objects.create(
            condition_template=self.condition_template,
            tier=AlterationTier.MARKED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            weakness_magnitude=5,
            resonance_bonus_magnitude=3,
            social_reactivity_magnitude=2,
            is_visible_at_rest=True,
            is_library_entry=True,
        )
        self.assertEqual(template.tier, AlterationTier.MARKED)
        self.assertEqual(template.weakness_magnitude, 5)
        self.assertEqual(template.resonance_bonus_magnitude, 3)
        self.assertEqual(template.social_reactivity_magnitude, 2)
        self.assertTrue(template.is_visible_at_rest)
        self.assertTrue(template.is_library_entry)

    def test_str_uses_condition_name(self) -> None:
        """__str__ returns the condition template name and tier."""
        template = MagicalAlterationTemplate.objects.create(
            condition_template=self.condition_template,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        result = str(template)
        self.assertIn(self.condition_template.name, result)
        self.assertIn("Tier 1", result)

    def test_default_values(self) -> None:
        """Check default field values are set correctly."""
        template = MagicalAlterationTemplate.objects.create(
            condition_template=self.condition_template,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        self.assertEqual(template.weakness_magnitude, 0)
        self.assertEqual(template.resonance_bonus_magnitude, 0)
        self.assertEqual(template.social_reactivity_magnitude, 0)
        self.assertFalse(template.is_visible_at_rest)
        self.assertFalse(template.is_library_entry)
        self.assertIsNone(template.authored_by)
        self.assertIsNone(template.parent_template)
        self.assertIsNone(template.weakness_damage_type)
        self.assertIsNotNone(template.created_at)

    def test_parent_template_self_fk(self) -> None:
        """Can set parent_template to another MagicalAlterationTemplate."""
        parent_condition = ConditionTemplateFactory()
        parent = MagicalAlterationTemplate.objects.create(
            condition_template=parent_condition,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            is_library_entry=True,
        )
        variant = MagicalAlterationTemplate.objects.create(
            condition_template=self.condition_template,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            parent_template=parent,
        )
        self.assertEqual(variant.parent_template, parent)
        self.assertIn(variant, parent.variants.all())

    def test_cascade_delete_with_condition_template(self) -> None:
        """Deleting the condition_template also deletes the alteration template."""
        template = MagicalAlterationTemplate.objects.create(
            condition_template=self.condition_template,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        pk = template.pk
        self.condition_template.delete()
        self.assertFalse(MagicalAlterationTemplate.objects.filter(pk=pk).exists())


class PendingAlterationTests(TestCase):
    """Tests for PendingAlteration model."""

    def setUp(self) -> None:
        self.character = CharacterSheetFactory()
        self.affinity = AffinityFactory()
        self.resonance = ResonanceFactory(affinity=self.affinity)

    def test_create_with_open_status_default(self) -> None:
        """PendingAlteration defaults to OPEN status."""
        pending = PendingAlteration.objects.create(
            character=self.character,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        self.assertEqual(pending.status, PendingAlterationStatus.OPEN)

    def test_create_with_all_provenance_fields(self) -> None:
        """Can create with all triggering context fields populated."""
        technique = TechniqueFactory()
        pending = PendingAlteration.objects.create(
            character=self.character,
            tier=AlterationTier.TOUCHED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            triggering_technique=technique,
            triggering_intensity=12,
            triggering_control=5,
            triggering_anima_cost=20,
            triggering_anima_deficit=8,
            triggering_soulfray_stage=2,
            audere_active=True,
        )
        self.assertEqual(pending.triggering_intensity, 12)
        self.assertEqual(pending.triggering_control, 5)
        self.assertEqual(pending.triggering_anima_cost, 20)
        self.assertEqual(pending.triggering_anima_deficit, 8)
        self.assertEqual(pending.triggering_soulfray_stage, 2)
        self.assertTrue(pending.audere_active)

    def test_character_cascade_delete(self) -> None:
        """Deleting the character cascades to PendingAlteration."""
        pending = PendingAlteration.objects.create(
            character=self.character,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        pk = pending.pk
        self.character.delete()
        self.assertFalse(PendingAlteration.objects.filter(pk=pk).exists())

    def test_str_contains_tier_and_status(self) -> None:
        """__str__ shows tier and status."""
        pending = PendingAlteration.objects.create(
            character=self.character,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        result = str(pending)
        self.assertIn("Tier 1", result)
        self.assertIn(PendingAlterationStatus.OPEN, result)

    def test_resolved_alteration_nullable(self) -> None:
        """resolved_alteration is null initially and can be set after creation."""
        pending = PendingAlteration.objects.create(
            character=self.character,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        self.assertIsNone(pending.resolved_alteration)


class MagicalAlterationEventTests(TestCase):
    """Tests for MagicalAlterationEvent model."""

    def setUp(self) -> None:
        self.character = CharacterSheetFactory()
        self.affinity = AffinityFactory()
        self.resonance = ResonanceFactory(affinity=self.affinity)
        self.condition_template = ConditionTemplateFactory()
        self.alteration_template = MagicalAlterationTemplate.objects.create(
            condition_template=self.condition_template,
            tier=AlterationTier.COSMETIC_TOUCH,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )

    def test_create_with_provenance_fields(self) -> None:
        """Can create an event with triggering context."""
        technique = TechniqueFactory()
        event = MagicalAlterationEvent.objects.create(
            character=self.character,
            alteration_template=self.alteration_template,
            triggering_technique=technique,
            triggering_intensity=10,
            triggering_control=3,
            triggering_anima_cost=15,
            triggering_anima_deficit=5,
            triggering_soulfray_stage=1,
            audere_active=False,
        )
        self.assertIsNotNone(event.pk)
        self.assertEqual(event.triggering_intensity, 10)
        self.assertIsNotNone(event.applied_at)

    def test_str_includes_condition_name_and_character(self) -> None:
        """__str__ includes the condition template name and character."""
        event = MagicalAlterationEvent.objects.create(
            character=self.character,
            alteration_template=self.alteration_template,
        )
        result = str(event)
        self.assertIn(self.condition_template.name, result)

    def test_alteration_template_protect_on_delete(self) -> None:
        """Deleting alteration_template is blocked when events reference it (PROTECT)."""
        from django.db import IntegrityError

        MagicalAlterationEvent.objects.create(
            character=self.character,
            alteration_template=self.alteration_template,
        )
        with self.assertRaises((IntegrityError, Exception)):
            self.alteration_template.delete()

    def test_character_cascade_delete(self) -> None:
        """Deleting character cascades to events."""
        event = MagicalAlterationEvent.objects.create(
            character=self.character,
            alteration_template=self.alteration_template,
        )
        pk = event.pk
        self.character.delete()
        self.assertFalse(MagicalAlterationEvent.objects.filter(pk=pk).exists())

    def test_optional_fields_default_null(self) -> None:
        """All optional FK and integer fields default to null."""
        event = MagicalAlterationEvent.objects.create(
            character=self.character,
            alteration_template=self.alteration_template,
        )
        self.assertIsNone(event.active_condition)
        self.assertIsNone(event.triggering_scene)
        self.assertIsNone(event.triggering_technique)
        self.assertIsNone(event.triggering_intensity)
        self.assertIsNone(event.triggering_control)
        self.assertIsNone(event.triggering_anima_cost)
        self.assertIsNone(event.triggering_anima_deficit)
        self.assertIsNone(event.triggering_soulfray_stage)
        self.assertFalse(event.audere_active)
        self.assertEqual(event.notes, "")
