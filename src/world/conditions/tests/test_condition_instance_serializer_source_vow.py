"""ConditionInstanceSerializer exposes source_vow_name (#2643) — armed team-damage-
percent buffs on allies are visible before casting."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.serializers import ConditionInstanceSerializer
from world.covenants.factories import CovenantRoleFactory


class ConditionInstanceSerializerSourceVowTests(TestCase):
    def test_source_vow_name_present_when_stamped(self):
        role = CovenantRoleFactory(name="Vanguard-serializer-test")
        target = CharacterFactory()
        condition = ConditionTemplateFactory(name="serializer-vow-test")
        instance = ConditionInstanceFactory(target=target, condition=condition, source_vow=role)

        data = ConditionInstanceSerializer(instance).data

        self.assertEqual(data["source_vow_name"], "Vanguard-serializer-test")

    def test_source_vow_name_null_when_unstamped(self):
        target = CharacterFactory()
        condition = ConditionTemplateFactory(name="serializer-novow-test")
        instance = ConditionInstanceFactory(target=target, condition=condition)

        data = ConditionInstanceSerializer(instance).data

        self.assertIsNone(data["source_vow_name"])
