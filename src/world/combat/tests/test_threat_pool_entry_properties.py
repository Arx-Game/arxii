"""Tests for ThreatPoolEntry.effect_properties M2M."""

from __future__ import annotations

from django.test import TestCase

from world.combat.factories import ThreatPoolEntryFactory
from world.combat.models import ThreatPoolEntry
from world.mechanics.factories import PropertyFactory


class ThreatPoolEntryEffectPropertiesTests(TestCase):
    """Verify the M2M wiring between ThreatPoolEntry and mechanics.Property."""

    def test_default_empty(self) -> None:
        entry = ThreatPoolEntryFactory()
        self.assertEqual(list(entry.effect_properties.all()), [])

    def test_attach_properties(self) -> None:
        entry = ThreatPoolEntryFactory()
        prop_fire = PropertyFactory(name="threat-fire")
        prop_loud = PropertyFactory(name="threat-loud")

        entry.effect_properties.add(prop_fire, prop_loud)

        attached = set(entry.effect_properties.values_list("name", flat=True))
        self.assertEqual(attached, {"threat-fire", "threat-loud"})

    def test_remove_property(self) -> None:
        entry = ThreatPoolEntryFactory()
        prop = PropertyFactory(name="threat-cold")
        entry.effect_properties.add(prop)
        entry.effect_properties.remove(prop)

        self.assertEqual(list(entry.effect_properties.all()), [])

    def test_related_name_reverse(self) -> None:
        prop = PropertyFactory(name="threat-shared")
        entry_a = ThreatPoolEntryFactory()
        entry_b = ThreatPoolEntryFactory()
        entry_a.effect_properties.add(prop)
        entry_b.effect_properties.add(prop)

        related = set(prop.threat_pool_entries.values_list("pk", flat=True))
        self.assertEqual(related, {entry_a.pk, entry_b.pk})

    def test_field_definition(self) -> None:
        field = ThreatPoolEntry._meta.get_field("effect_properties")
        self.assertEqual(field.related_model.__name__, "Property")
        self.assertTrue(field.many_to_many)
        self.assertTrue(field.blank)
