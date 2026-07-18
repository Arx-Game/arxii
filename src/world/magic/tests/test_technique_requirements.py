"""Tests for TechniqueCapabilityRequirement model and technique_performable service."""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import apply_condition
from world.magic.factories import (
    CharacterTechniqueFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueCapabilityRequirementFactory,
    TechniqueFactory,
)
from world.magic.models.techniques import TechniqueCapabilityRequirement
from world.magic.services.capability_requirements import technique_performable


class TechniqueCapabilityRequirementModelTests(TestCase):
    def test_default_minimum_value_is_one(self) -> None:
        tech = TechniqueFactory()
        cap = CapabilityTypeFactory(name="awareness")
        req = TechniqueCapabilityRequirement.objects.create(technique=tech, capability=cap)
        self.assertEqual(req.minimum_value, 1)


class TechniquePerformableTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        CharacterSheetFactory(character=cls.character)
        cls.awareness = CapabilityTypeFactory(name="awareness", innate_baseline=1)
        cls.movement = CapabilityTypeFactory(name="movement", innate_baseline=1)
        cls.spell = TechniqueFactory(name="Mind Spike")
        TechniqueCapabilityRequirementFactory(technique=cls.spell, capability=cls.awareness)
        cls.charge = TechniqueFactory(name="Charge")
        TechniqueCapabilityRequirementFactory(technique=cls.charge, capability=cls.movement)

    def test_unimpaired_can_perform(self) -> None:
        self.assertTrue(technique_performable(self.character.sheet_data, self.spell))
        self.assertTrue(technique_performable(self.character.sheet_data, self.charge))

    def test_immobilized_keeps_consciousness_technique(self) -> None:
        immob = ConditionTemplateFactory(name="Immobilized")
        ConditionCapabilityEffectFactory(condition=immob, capability=self.movement, value=-100)
        apply_condition(self.character, immob)
        self.assertTrue(technique_performable(self.character.sheet_data, self.spell))
        self.assertFalse(technique_performable(self.character.sheet_data, self.charge))

    def test_unconscious_blocks_awareness_technique(self) -> None:
        ko = ConditionTemplateFactory(name="Unconscious")
        ConditionCapabilityEffectFactory(condition=ko, capability=self.awareness, value=-100)
        apply_condition(self.character, ko)
        self.assertFalse(technique_performable(self.character.sheet_data, self.spell))


class TechniqueGrantSatisfiesRequirementTests(TestCase):
    """#2504: journey A — a technique-granted capability (folded into
    ``get_effective_capability_value`` by the agency oracle) satisfies
    another technique's ``TechniqueCapabilityRequirement``, not only
    condition-driven or innate-baseline capability sources. Mirrors the
    unit-level fixture-building in
    ``world.conditions.tests.test_effective_capability_value
    .TechniqueCapabilityGrantFoldingTests`` but exercises the real consumer
    seam (``technique_performable``) instead of the oracle directly."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory()
        CharacterSheetFactory(character=cls.character)
        cls.granted_cap = CapabilityTypeFactory(name="tf-granted-capability", innate_baseline=0)
        cls.granting_technique = TechniqueFactory(name="Empower", intensity=1)
        cls.grant = TechniqueCapabilityGrantFactory(
            technique=cls.granting_technique,
            capability=cls.granted_cap,
            base_value=5,
            intensity_multiplier=0,
        )
        cls.gated_technique = TechniqueFactory(name="Gated Strike")
        TechniqueCapabilityRequirementFactory(
            technique=cls.gated_technique,
            capability=cls.granted_cap,
            minimum_value=cls.grant.calculate_value(),
        )

    def test_fails_without_granting_technique(self) -> None:
        """Bare character: no known technique grants the capability."""
        self.assertFalse(technique_performable(self.character.sheet_data, self.gated_technique))

    def test_passes_once_granting_technique_is_known(self) -> None:
        """Knowing the granting technique raises the effective capability
        value to the grant's calculated value, meeting the minimum."""
        CharacterTechniqueFactory(
            character=self.character.sheet_data, technique=self.granting_technique
        )
        self.assertTrue(technique_performable(self.character.sheet_data, self.gated_technique))
