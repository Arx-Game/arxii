"""Tests for ConditionTemplate Properties and CapabilityType prerequisites."""

from django.test import TestCase

from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import CapabilityType
from world.mechanics.factories import PropertyFactory


class CapabilityTypePrerequisiteTests(TestCase):
    def test_prerequisite_key_blank_by_default(self) -> None:
        cap = CapabilityType.objects.create(name="test_cap_prereq")
        assert cap.prerequisite_key == ""

    def test_prerequisite_key_set(self) -> None:
        cap = CapabilityType.objects.create(
            name="shadow_control",
            prerequisite_key="shadows_available",
        )
        assert cap.prerequisite_key == "shadows_available"


class ConditionTemplatePropertyTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.condition = ConditionTemplateFactory()
        cls.prop1 = PropertyFactory(name="clawed_test")
        cls.prop2 = PropertyFactory(name="bestial_test")

    def test_add_properties(self) -> None:
        self.condition.properties.add(self.prop1, self.prop2)
        props = self.condition.properties.all()
        assert self.prop1 in props
        assert self.prop2 in props

    def test_reverse_relation(self) -> None:
        self.condition.properties.add(self.prop1)
        assert self.condition in self.prop1.condition_templates.all()
