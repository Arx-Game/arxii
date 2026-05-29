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
from world.magic.factories import TechniqueCapabilityRequirementFactory, TechniqueFactory
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
        self.assertTrue(technique_performable(self.character, self.spell))
        self.assertTrue(technique_performable(self.character, self.charge))

    def test_immobilized_keeps_consciousness_technique(self) -> None:
        immob = ConditionTemplateFactory(name="Immobilized")
        ConditionCapabilityEffectFactory(condition=immob, capability=self.movement, value=-100)
        apply_condition(self.character, immob)
        self.assertTrue(technique_performable(self.character, self.spell))
        self.assertFalse(technique_performable(self.character, self.charge))

    def test_unconscious_blocks_awareness_technique(self) -> None:
        ko = ConditionTemplateFactory(name="Unconscious")
        ConditionCapabilityEffectFactory(condition=ko, capability=self.awareness, value=-100)
        apply_condition(self.character, ko)
        self.assertFalse(technique_performable(self.character, self.spell))
