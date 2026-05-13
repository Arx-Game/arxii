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


class CharacterCarriedItemsHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
        from world.items.factories import (
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
        )

        cls.character = CharacterFactory(db_key="CarriedHandlerChar")
        cls.other_character = CharacterFactory(db_key="OtherCarriedChar")
        cls.template = ItemTemplateFactory(name="CarriedHandlerTpl")
        cls.quality = QualityTierFactory(name="CarriedHandlerQ", color_hex="#abcdef")

        def _item_on(owner_obj, key: str):
            obj = ObjectDBFactory(
                db_key=key,
                db_typeclass_path="typeclasses.objects.Object",
            )
            obj.location = owner_obj
            obj.save()
            return ItemInstanceFactory(
                template=cls.template,
                quality_tier=cls.quality,
                game_object=obj,
            )

        cls.mine_a = _item_on(cls.character, "MineA")
        cls.mine_b = _item_on(cls.character, "MineB")
        cls.theirs = _item_on(cls.other_character, "Theirs")

    def setUp(self) -> None:
        # Cross-app test pollution guard. The ``flush_instance_cache()``
        # is the one doing the real work — when other apps' tests have
        # populated the SharedMemoryModel identity map with ItemInstance
        # rows whose pks may collide with ours, a fresh handler read
        # would otherwise pull in those stale Python instances. Flushing
        # the model cache forces the next queryset to materialize new
        # instances from fresh rows. The handler ``invalidate()`` calls
        # are belt-and-suspenders: they reset ``_cached`` so even if
        # something repopulated the handler between flush and read,
        # it'd still re-fetch.
        from world.items.models import ItemInstance

        ItemInstance.flush_instance_cache()
        self.character.carried_items.invalidate()
        self.other_character.carried_items.invalidate()

    def test_returns_only_items_carried_by_character(self) -> None:
        items = list(self.character.carried_items)
        pks = {it.pk for it in items}
        self.assertEqual(pks, {self.mine_a.pk, self.mine_b.pk})

    def test_get_returns_item_by_pk(self) -> None:
        self.assertEqual(self.character.carried_items.get(self.mine_a.pk), self.mine_a)
        self.assertIsNone(self.character.carried_items.get(self.theirs.pk))

    def test_invalidate_clears_cache(self) -> None:
        first = list(self.character.carried_items)
        self.character.carried_items.invalidate()
        second = list(self.character.carried_items)
        self.assertEqual({i.pk for i in first}, {i.pk for i in second})

    def test_no_query_after_first_load(self) -> None:
        list(self.character.carried_items)  # warm
        with self.assertNumQueries(0):
            for item in self.character.carried_items:
                # Walking the prefetched chain costs no queries.
                _ = item.template_id
                _ = item.quality_tier_id
                list(item.cached_item_facets)


class CharacterSheetOutfitsHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.factories import (
            ItemInstanceFactory,
            ItemTemplateFactory,
            OutfitFactory,
            QualityTierFactory,
        )

        cls.character = CharacterFactory(db_key="OutfitsHandlerChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        # Wardrobe item required by Outfit.clean()
        wardrobe_tpl = ItemTemplateFactory(name="WardrobeTpl", is_wardrobe=True)
        cls.quality = QualityTierFactory(name="OutfitHandlerQ", color_hex="#123456")
        wardrobe_obj = ObjectDBFactory(
            db_key="WardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        cls.wardrobe = ItemInstanceFactory(
            template=wardrobe_tpl,
            quality_tier=cls.quality,
            game_object=wardrobe_obj,
        )

        cls.outfit_a = OutfitFactory(
            character_sheet=cls.sheet,
            wardrobe=cls.wardrobe,
            name="Court",
        )
        cls.outfit_b = OutfitFactory(
            character_sheet=cls.sheet,
            wardrobe=cls.wardrobe,
            name="Battle",
        )

        # Outfit on another sheet — must not appear.
        other_character = CharacterFactory(db_key="OutfitsOtherChar")
        cls.other_sheet = CharacterSheetFactory(character=other_character)
        cls.other_outfit = OutfitFactory(
            character_sheet=cls.other_sheet,
            wardrobe=cls.wardrobe,
            name="Theirs",
        )

    def setUp(self) -> None:
        # Cross-app pollution guard — see CharacterCarriedItemsHandlerTests.setUp
        # for what each line does. The ``flush_instance_cache()`` is the
        # real fix; the ``invalidate()`` calls are defense-in-depth.
        from world.items.models import Outfit

        Outfit.flush_instance_cache()
        self.sheet.saved_outfits.invalidate()
        self.other_sheet.saved_outfits.invalidate()

    def test_returns_only_outfits_for_sheet(self) -> None:
        outfits = list(self.sheet.saved_outfits)
        pks = {o.pk for o in outfits}
        self.assertEqual(pks, {self.outfit_a.pk, self.outfit_b.pk})

    def test_get_returns_outfit_by_pk(self) -> None:
        self.assertEqual(self.sheet.saved_outfits.get(self.outfit_a.pk), self.outfit_a)
        self.assertIsNone(self.sheet.saved_outfits.get(self.other_outfit.pk))

    def test_invalidate_clears_cache(self) -> None:
        first = list(self.sheet.saved_outfits)
        self.sheet.saved_outfits.invalidate()
        second = list(self.sheet.saved_outfits)
        self.assertEqual({o.pk for o in first}, {o.pk for o in second})

    def test_no_query_after_first_load(self) -> None:
        list(self.sheet.saved_outfits)  # warm
        with self.assertNumQueries(0):
            for outfit in self.sheet.saved_outfits:
                _ = outfit.wardrobe_id
                list(outfit.cached_outfit_slots)
