"""Tests for items handlers."""

from django.test import TestCase


class CharacterEquipmentHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.items.factories import (
            EquippedItemFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
        )
        from world.magic.factories import FacetFactory

        cls.character = CharacterFactory(db_key="HandlerTestChar")
        tpl = ItemTemplateFactory(facet_capacity=2)
        cls.q = QualityTierFactory()
        cls.instance = ItemInstanceFactory(template=tpl, quality_tier=cls.q)
        cls.facet_a = FacetFactory(name="Spider")
        cls.facet_b = FacetFactory(name="Silver")
        cls.if_a = ItemFacetFactory(
            item_instance=cls.instance,
            facet=cls.facet_a,
            attachment_quality_tier=cls.q,
        )
        cls.if_b = ItemFacetFactory(
            item_instance=cls.instance,
            facet=cls.facet_b,
            attachment_quality_tier=cls.q,
        )
        cls.equipped = EquippedItemFactory(
            character=cls.character,
            item_instance=cls.instance,
        )

    def test_iter_item_facets_yields_all(self) -> None:
        facets = list(self.character.equipped_items.iter_item_facets())
        self.assertEqual(len(facets), 2)
        self.assertIn(self.if_a, facets)
        self.assertIn(self.if_b, facets)

    def test_item_facets_for_filters_by_facet(self) -> None:
        result = self.character.equipped_items.item_facets_for(self.facet_a)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], self.if_a)

    def test_invalidate_clears_cache(self) -> None:
        first = list(self.character.equipped_items.iter_item_facets())
        self.character.equipped_items.invalidate()
        second = list(self.character.equipped_items.iter_item_facets())
        self.assertEqual(len(second), len(first))

    def test_no_query_after_first_load(self) -> None:
        list(self.character.equipped_items.iter_item_facets())  # Warm
        with self.assertNumQueries(0):
            list(self.character.equipped_items.iter_item_facets())
            list(self.character.equipped_items.item_facets_for(self.facet_a))
