"""Tests for PersonaLegendMurmurHandler (#2523)."""

from __future__ import annotations

from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    LegendEntryFactory,
    LegendSpreadFactory,
)


class MurmurableDeedsTests(TestCase):
    def test_empty_when_no_deeds(self) -> None:
        persona = PersonaFactory()
        self.assertEqual(persona.legend_murmur.murmurable_deeds, [])

    def test_excludes_non_common_knowledge_deeds(self) -> None:
        persona = PersonaFactory()
        # base_value=10, no spreads -> total=10, threshold=50 -> not common knowledge
        LegendEntryFactory(persona=persona, base_value=10, is_active=True)
        self.assertEqual(persona.legend_murmur.murmurable_deeds, [])

    def test_includes_common_knowledge_deeds(self) -> None:
        persona = PersonaFactory()
        # base_value=10, spread 40 -> total=50, threshold=50 -> common knowledge
        deed = LegendEntryFactory(persona=persona, base_value=10, is_active=True)
        LegendSpreadFactory(legend_entry=deed, value_added=40)
        deeds = persona.legend_murmur.murmurable_deeds
        self.assertEqual(len(deeds), 1)
        self.assertEqual(deeds[0].pk, deed.pk)

    def test_excludes_inactive_deeds(self) -> None:
        persona = PersonaFactory()
        deed = LegendEntryFactory(persona=persona, base_value=10, is_active=False)
        LegendSpreadFactory(legend_entry=deed, value_added=40)
        self.assertEqual(persona.legend_murmur.murmurable_deeds, [])

    def test_excludes_secret_linked_deeds(self) -> None:
        from world.secrets.factories import SecretFactory

        persona = PersonaFactory()
        deed = LegendEntryFactory(persona=persona, base_value=10, is_active=True)
        LegendSpreadFactory(legend_entry=deed, value_added=40)
        SecretFactory(legend_deed=deed)
        self.assertEqual(persona.legend_murmur.murmurable_deeds, [])

    def test_excludes_zero_base_deeds(self) -> None:
        persona = PersonaFactory()
        LegendEntryFactory(persona=persona, base_value=0, is_active=True)
        self.assertEqual(persona.legend_murmur.murmurable_deeds, [])

    def test_ordered_by_spread_desc(self) -> None:
        persona = PersonaFactory()
        deed_low = LegendEntryFactory(
            persona=persona, base_value=10, is_active=True, title="Low Deed"
        )
        LegendSpreadFactory(legend_entry=deed_low, value_added=40)
        deed_high = LegendEntryFactory(
            persona=persona, base_value=10, is_active=True, title="High Deed"
        )
        LegendSpreadFactory(legend_entry=deed_high, value_added=80)
        deeds = persona.legend_murmur.murmurable_deeds
        self.assertEqual(deeds[0].title, "High Deed")
        self.assertEqual(deeds[1].title, "Low Deed")


class HasMurmurableDeedsTests(TestCase):
    def test_false_when_no_deeds(self) -> None:
        persona = PersonaFactory()
        self.assertFalse(persona.legend_murmur.has_murmurable_deeds)

    def test_true_when_common_knowledge_deed_exists(self) -> None:
        persona = PersonaFactory()
        deed = LegendEntryFactory(persona=persona, base_value=10, is_active=True)
        LegendSpreadFactory(legend_entry=deed, value_added=40)
        self.assertTrue(persona.legend_murmur.has_murmurable_deeds)


class DeedTitlesTests(TestCase):
    def test_returns_top_3_titles(self) -> None:
        persona = PersonaFactory()
        for i in range(4):
            deed = LegendEntryFactory(
                persona=persona, base_value=10, is_active=True, title=f"Deed {i}"
            )
            LegendSpreadFactory(legend_entry=deed, value_added=40)
        titles = persona.legend_murmur.deed_titles
        self.assertEqual(len(titles), 3)

    def test_empty_when_no_deeds(self) -> None:
        persona = PersonaFactory()
        self.assertEqual(persona.legend_murmur.deed_titles, [])


class CacheInvalidationTests(TestCase):
    def test_cache_cleared_on_persona_save(self) -> None:
        persona = PersonaFactory()
        # Prime the cache
        _ = persona.legend_murmur.murmurable_deeds
        self.assertIn("legend_murmur", persona.__dict__)
        persona.save()
        self.assertNotIn("legend_murmur", persona.__dict__)
