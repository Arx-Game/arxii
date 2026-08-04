"""Coverage/concealment ruling + Reveal (#2965).

Accents multiply per visible slot; prestige is per-piece; legend pierces
concealment; a Reveal flips a concealed piece into the visible set.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    EquippedItemFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.items.services.visibility import compute_worn_visibility

_GOWN_REGIONS = (BodyRegion.TORSO, BodyRegion.LEFT_LEG, BodyRegion.RIGHT_LEG)


def _equip_multi(sheet, instance, regions, layer, *, covers=False):
    """Equip one instance across several regions (one EquippedItem row each)."""
    rows = []
    for region in regions:
        TemplateSlotFactory(
            template=instance.template,
            body_region=region,
            equipment_layer=layer,
            covers_lower_layers=covers,
        )
        rows.append(
            EquippedItemFactory(
                character=sheet,
                item_instance=instance,
                body_region=region,
                equipment_layer=layer,
            )
        )
    return rows


def _fresh_rows(sheet):
    from django.db.models import Prefetch

    from world.items.models import TemplateSlot

    return list(
        EquippedItem.objects.filter(character=sheet)
        .select_related("item_instance__template")
        .prefetch_related(
            Prefetch(
                "item_instance__template__slots",
                queryset=TemplateSlot.objects.all(),
                to_attr="cached_slots",
            )
        )
    )


class WornVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_multi_slot_piece_counts_all_slots(self):
        gown = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, gown, _GOWN_REGIONS, EquipmentLayer.BASE)
        visibility = compute_worn_visibility(_fresh_rows(self.sheet))
        assert visibility.occupied_slot_counts[gown.pk] == 3
        assert visibility.visible_slot_counts[gown.pk] == 3

    def test_covering_layer_conceals_lower_piece(self):
        shirt = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, shirt, [BodyRegion.TORSO], EquipmentLayer.BASE)
        coat = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, coat, [BodyRegion.TORSO], EquipmentLayer.OUTER, covers=True)
        visibility = compute_worn_visibility(_fresh_rows(self.sheet))
        assert not visibility.is_visible(shirt.pk)
        assert visibility.is_visible(coat.pk)

    def test_reveal_counts_all_occupied_slots(self):
        shirt = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, shirt, [BodyRegion.TORSO], EquipmentLayer.BASE)
        coat = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, coat, [BodyRegion.TORSO], EquipmentLayer.OUTER, covers=True)
        from django.utils import timezone

        # save() through instances, not .update() — idmapper-cached rows would
        # otherwise keep a stale revealed_at=None (SharedMemoryModel).
        for row in EquippedItem.objects.filter(item_instance=shirt):
            row.revealed_at = timezone.now()
            row.save(update_fields=["revealed_at"])
        visibility = compute_worn_visibility(_fresh_rows(self.sheet))
        assert visibility.is_visible(shirt.pk)
        assert visibility.visible_slot_counts[shirt.pk] == 1

    def test_non_covering_higher_layer_does_not_conceal(self):
        shirt = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, shirt, [BodyRegion.TORSO], EquipmentLayer.BASE)
        open_vest = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, open_vest, [BodyRegion.TORSO], EquipmentLayer.OVER, covers=False)
        visibility = compute_worn_visibility(_fresh_rows(self.sheet))
        assert visibility.is_visible(shirt.pk)


class RevealActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory().character
        cls.sheet = cls.character.sheet_data
        cls.shirt = ItemInstanceFactory(
            template=ItemTemplateFactory(), holder_character_sheet=cls.sheet
        )
        _equip_multi(cls.sheet, cls.shirt, [BodyRegion.TORSO], EquipmentLayer.BASE)
        coat = ItemInstanceFactory(template=ItemTemplateFactory(), holder_character_sheet=cls.sheet)
        _equip_multi(cls.sheet, coat, [BodyRegion.TORSO], EquipmentLayer.OUTER, covers=True)
        cls.coat = coat

    def test_reveal_flips_concealed_piece(self):
        from actions.definitions.fashion import RevealAction

        result = RevealAction().run(actor=self.character, item_id=self.shirt.pk)
        assert result.success, result.message
        assert (
            EquippedItem.objects.filter(item_instance=self.shirt, revealed_at__isnull=False).count()
            == 1
        )

    def test_reveal_rejects_already_visible(self):
        from actions.definitions.fashion import RevealAction

        result = RevealAction().run(actor=self.character, item_id=self.coat.pk)
        assert not result.success

    def test_reveal_rejects_unworn(self):
        from actions.definitions.fashion import RevealAction

        loose = ItemInstanceFactory(template=ItemTemplateFactory())
        result = RevealAction().run(actor=self.character, item_id=loose.pk)
        assert not result.success
