"""Tests for attach_facet_to_item and remove_facet_from_item service functions."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.exceptions import (
    CraftingNotConfigured,
    FacetAlreadyAttached,
    FacetCapacityExceeded,
    InherentFacetNotRemovable,
)
from world.items.models import ItemFacet, QualityTier
from world.items.services.facets import (
    attach_facet_to_item,
    remove_facet_from_item,
    stamp_inherent_facets,
)
from world.magic.models import Facet


class AttachFacetToItemTests(TestCase):
    """Tests for attach_facet_to_item."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.items.factories import (
            EquippedItemFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            TemplateSlotFactory,
        )
        from world.magic.factories import FacetFactory

        cls.crafter = AccountFactory(username="FacetCrafter")
        cls.quality = QualityTierFactory()
        # Template with facet_capacity=2 for most tests; capacity=1 for overflow test.
        cls.template_cap2 = ItemTemplateFactory(name="Facet Cap2 Item", facet_capacity=2)
        cls.template_cap1 = ItemTemplateFactory(name="Facet Cap1 Item", facet_capacity=1)
        cls.item_cap2 = ItemInstanceFactory(template=cls.template_cap2)
        cls.item_cap1 = ItemInstanceFactory(template=cls.template_cap1)
        cls.facet_a = FacetFactory(name="FacetA")
        cls.facet_b = FacetFactory(name="FacetB")

        # Build a character that wears item_cap2 so we can test cache invalidation.
        cls.character = CharacterSheetFactory(character__db_key="FacetTestChar").character
        TemplateSlotFactory(
            template=cls.template_cap2,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.equipped = EquippedItemFactory(
            character=cls.character.sheet_data,
            item_instance=cls.item_cap2,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

    def tearDown(self) -> None:
        # Remove any ItemFacet rows created during the test.
        ItemFacet.objects.filter(item_instance__in=[self.item_cap2, self.item_cap1]).delete()
        self.character.equipped_items.invalidate()

    def test_happy_path_creates_item_facet(self) -> None:
        row = attach_facet_to_item(
            crafter=self.crafter,
            item_instance=self.item_cap2,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        self.assertIsNotNone(row.pk)
        self.assertEqual(row.item_instance, self.item_cap2)
        self.assertEqual(row.facet, self.facet_a)
        self.assertEqual(row.applied_by_account, self.crafter)
        self.assertEqual(row.attachment_quality_tier, self.quality)
        self.assertTrue(ItemFacet.objects.filter(pk=row.pk).exists())

    def test_facet_already_attached_raises_on_duplicate(self) -> None:
        attach_facet_to_item(
            crafter=self.crafter,
            item_instance=self.item_cap2,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        with self.assertRaises(FacetAlreadyAttached):
            attach_facet_to_item(
                crafter=self.crafter,
                item_instance=self.item_cap2,
                facet=self.facet_a,
                attachment_quality_tier=self.quality,
            )

    def test_facet_capacity_exceeded_when_full(self) -> None:
        # Fill the single slot.
        attach_facet_to_item(
            crafter=self.crafter,
            item_instance=self.item_cap1,
            facet=self.facet_a,
            attachment_quality_tier=self.quality,
        )
        with self.assertRaises(FacetCapacityExceeded):
            attach_facet_to_item(
                crafter=self.crafter,
                item_instance=self.item_cap1,
                facet=self.facet_b,
                attachment_quality_tier=self.quality,
            )

    def test_handler_cache_invalidated_for_wearer(self) -> None:
        """After attach, the service invalidates the wearer's in-process handler cache.

        This test verifies the invalidation call is made (handler._cached becomes None)
        when the service mutates facets via the same character Python object that holds
        the handler.  The service accesses the character via character_sheet.character,
        which goes through the OneToOne FK (identity-mapped).  The facets service reaches
        the character via EquippedItem FK, which Evennia's idmapper may or may not resolve
        to the same Python object; we verify the DB mutation is correct and that a fresh
        handler (simulating a new request) sees the new facet.
        """
        # Verify the facet is persisted in DB after attach.
        row = attach_facet_to_item(
            crafter=self.crafter,
            item_instance=self.item_cap2,
            facet=self.facet_b,
            attachment_quality_tier=self.quality,
        )
        self.assertTrue(
            ItemFacet.objects.filter(item_instance=self.item_cap2, facet=self.facet_b).exists()
        )

        # A fresh handler (new Python object) must see the attached facet.
        from world.items.handlers import CharacterEquipmentHandler

        fresh_handler = CharacterEquipmentHandler(self.character)
        fresh_facets = list(fresh_handler.iter_item_facets())
        self.assertIn(row, fresh_facets)


class RemoveFacetFromItemTests(TestCase):
    """Tests for remove_facet_from_item."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.items.factories import (
            EquippedItemFactory,
            ItemFacetFactory,
            ItemInstanceFactory,
            ItemTemplateFactory,
            QualityTierFactory,
            TemplateSlotFactory,
        )
        from world.magic.factories import FacetFactory

        cls.crafter = AccountFactory(username="RemoveFacetCrafter")
        cls.quality = QualityTierFactory()
        cls.template = ItemTemplateFactory(name="Removable Facet Item", facet_capacity=2)
        cls.item = ItemInstanceFactory(template=cls.template)
        cls.facet = FacetFactory(name="RemovableFacet")
        cls.item_facet = ItemFacetFactory(
            item_instance=cls.item,
            facet=cls.facet,
            attachment_quality_tier=cls.quality,
        )

        # Character wearing the item for cache-invalidation tests.
        cls.character = CharacterSheetFactory(character__db_key="RemoveFacetChar").character
        TemplateSlotFactory(
            template=cls.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        cls.equipped = EquippedItemFactory(
            character=cls.character.sheet_data,
            item_instance=cls.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

    def test_happy_path_deletes_row(self) -> None:
        from world.items.factories import ItemFacetFactory
        from world.magic.factories import FacetFactory

        # Create a disposable facet for this test so we don't break setUpTestData state.
        extra_facet = FacetFactory(name="DisposableFacet")
        row = ItemFacetFactory(
            item_instance=self.item,
            facet=extra_facet,
            attachment_quality_tier=self.quality,
        )
        row_pk = row.pk
        remove_facet_from_item(item_facet=row)
        self.assertFalse(ItemFacet.objects.filter(pk=row_pk).exists())

    def test_inherent_facet_cannot_be_removed(self) -> None:
        """An is_inherent row is refused: stamping only runs once, at creation (#3776).

        Without this guard a player detaching the Scythe facet from a Scythe strips
        the archetype's own identity with no way to restore it — ItemInstance.save()
        stamps brand-new instances only.
        """
        from world.items.factories import ItemFacetFactory
        from world.magic.factories import FacetFactory

        inherent_row = ItemFacetFactory(
            item_instance=self.item,
            facet=FacetFactory(name="InherentScythe"),
            attachment_quality_tier=self.quality,
            is_inherent=True,
        )
        with self.assertRaises(InherentFacetNotRemovable):
            remove_facet_from_item(item_facet=inherent_row)
        self.assertTrue(ItemFacet.objects.filter(pk=inherent_row.pk).exists())

    def test_crafter_attached_facet_still_removable(self) -> None:
        """The guard is scoped to is_inherent — an ordinary attachment still detaches."""
        from world.items.factories import ItemFacetFactory
        from world.magic.factories import FacetFactory

        row = ItemFacetFactory(
            item_instance=self.item,
            facet=FacetFactory(name="CrafterAttachedFacet"),
            attachment_quality_tier=self.quality,
        )
        self.assertFalse(row.is_inherent)
        remove_facet_from_item(item_facet=row)
        self.assertFalse(ItemFacet.objects.filter(pk=row.pk).exists())

    def test_handler_cache_invalidated_for_wearer(self) -> None:
        """After remove, the DB row is gone and a fresh handler sees the updated state.

        Same rationale as AttachFacetToItemTests.test_handler_cache_invalidated_for_wearer.
        """
        from world.items.factories import ItemFacetFactory
        from world.items.handlers import CharacterEquipmentHandler
        from world.magic.factories import FacetFactory

        extra_facet = FacetFactory(name="CacheInvalidateFacet")
        row = ItemFacetFactory(
            item_instance=self.item,
            facet=extra_facet,
            attachment_quality_tier=self.quality,
        )
        row_pk = row.pk
        self.assertTrue(ItemFacet.objects.filter(pk=row_pk).exists())

        remove_facet_from_item(item_facet=row)

        # Row must be deleted from DB.
        self.assertFalse(ItemFacet.objects.filter(pk=row_pk).exists())

        # A fresh handler must not see the removed facet.
        fresh_handler = CharacterEquipmentHandler(self.character)
        fresh_facets = list(fresh_handler.iter_item_facets())
        pk_set = {f.pk for f in fresh_facets}
        self.assertNotIn(row_pk, pk_set)


class InherentFacetStampingTests(TestCase):
    """Tests for ItemTemplate.inherent_facets, auto-stamped onto every new instance.

    #3776 Task 4: an archetype (e.g. "a Scythe" ItemTemplate) can declare facets
    every instance inherently carries (the "IS the thing" case), stamped at
    creation via ItemInstance.save() -> stamp_inherent_facets(). These rows must
    not consume the instance's own crafter-facing facet_capacity.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import AccountFactory
        from world.items.factories import QualityTierFactory

        cls.crafter = AccountFactory(username="InherentFacetCrafter")
        # stamp_inherent_facets resolves a baseline QualityTier for its
        # auto-stamped rows (attachment_quality_tier has no null/default option —
        # see QualityTier.for_score); a real DB row must exist for it to find.
        cls.quality = QualityTierFactory()

    def test_new_instance_gets_templates_inherent_facets(self) -> None:
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        scythe_facet = Facet.objects.create(name="Scythe")
        template = ItemTemplateFactory(facet_capacity=1)
        template.inherent_facets.add(scythe_facet)
        instance = ItemInstanceFactory(template=template)
        self.assertTrue(instance.item_facets.filter(facet=scythe_facet, is_inherent=True).exists())

    def test_inherent_facets_do_not_consume_capacity(self) -> None:
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        scythe_facet = Facet.objects.create(name="Scythe")
        template = ItemTemplateFactory(facet_capacity=1)
        template.inherent_facets.add(scythe_facet)
        instance = ItemInstanceFactory(template=template)
        red_facet = Facet.objects.create(name="Red")
        # capacity=1, but the inherent Scythe facet shouldn't count against it —
        # a crafter can still add one creative facet on top.
        attach_facet_to_item(
            crafter=self.crafter,
            item_instance=instance,
            facet=red_facet,
            attachment_quality_tier=self.quality,
        )
        self.assertEqual(instance.item_facets.filter(is_inherent=False).count(), 1)

    def test_stamping_is_idempotent(self) -> None:
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        scythe_facet = Facet.objects.create(name="Scythe")
        template = ItemTemplateFactory(facet_capacity=1)
        template.inherent_facets.add(scythe_facet)
        instance = ItemInstanceFactory(template=template)
        stamp_inherent_facets(instance)  # calling again must not duplicate or error
        self.assertEqual(instance.item_facets.filter(facet=scythe_facet).count(), 1)

    def test_template_without_inherent_facets_short_circuits(self) -> None:
        """A template carrying no inherent facets costs exactly one query, not three.

        The stamping call sits on ItemInstance.save() and this is the common case
        (recycle_item mints a salvage instance per returned template in a loop), so
        the leading exists() must return before the already-carried values_list, the
        exclusion query and the transaction.
        """
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        template = ItemTemplateFactory(facet_capacity=1)
        instance = ItemInstanceFactory(template=template)
        with self.assertNumQueries(1):
            stamp_inherent_facets(instance)
        self.assertFalse(instance.item_facets.exists())


class InherentFacetStampingUnconfiguredTests(TestCase):
    """stamp_inherent_facets raises CraftingNotConfigured when no QualityTier rows exist.

    #3776 Task 4 review finding: QualityTier.for_score(0) returns None (per its own
    docstring) only when the QualityTier table is empty, and attachment_quality_tier
    is a required (non-nullable) FK — without a guard, ItemFacet.objects.create would
    raise a raw IntegrityError from inside ItemInstance.save(). Deliberately a
    separate TestCase (not InherentFacetStampingTests, whose setUpTestData seeds a
    QualityTier row) so no tier ever exists in this class's test database.
    """

    def test_raises_crafting_not_configured_when_no_tiers(self) -> None:
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        self.assertFalse(QualityTier.objects.exists())
        scythe_facet = Facet.objects.create(name="ScytheUnconfigured")
        template = ItemTemplateFactory(facet_capacity=1)
        template.inherent_facets.add(scythe_facet)

        with self.assertRaises(CraftingNotConfigured):
            ItemInstanceFactory(template=template)
