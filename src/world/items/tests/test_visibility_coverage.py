"""The layer walk + show/conceal (#2985, superseding #2965).

Plain cuts conceal beneath by default; exposure is authored (cut/material) or
performed (worn open via show). Accents multiply per visible slot; prestige is
per-piece; legend pierces concealment.
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


def _equip_multi(sheet, instance, regions, layer):
    """Equip one instance across several regions (one EquippedItem row each)."""
    rows = []
    for region in regions:
        TemplateSlotFactory(
            template=instance.template,
            body_region=region,
            equipment_layer=layer,
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

    def test_plain_layer_conceals_lower_piece_by_default(self):
        shirt = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, shirt, [BodyRegion.TORSO], EquipmentLayer.BASE)
        coat = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, coat, [BodyRegion.TORSO], EquipmentLayer.OUTER)
        visibility = compute_worn_visibility(_fresh_rows(self.sheet))
        assert not visibility.is_visible(shirt.pk)
        assert visibility.is_visible(coat.pk)

    def test_worn_open_layer_shows_the_piece_beneath(self):
        shirt = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, shirt, [BodyRegion.TORSO], EquipmentLayer.BASE)
        coat = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, coat, [BodyRegion.TORSO], EquipmentLayer.OUTER)
        from django.utils import timezone

        # save() through instances, not .update() — idmapper-cached rows would
        # otherwise keep a stale opened_at=None (SharedMemoryModel).
        for row in EquippedItem.objects.filter(item_instance=coat):
            row.opened_at = timezone.now()
            row.save(update_fields=["opened_at"])
        visibility = compute_worn_visibility(_fresh_rows(self.sheet))
        assert visibility.is_visible(shirt.pk)
        assert visibility.visible_slot_counts[shirt.pk] == 1
        assert visibility.is_visible(coat.pk)

    def test_exposing_cut_higher_layer_does_not_conceal(self):
        from world.items.models import Silhouette, WearFamily

        shirt = ItemInstanceFactory(template=ItemTemplateFactory())
        _equip_multi(self.sheet, shirt, [BodyRegion.TORSO], EquipmentLayer.BASE)
        open_cut = Silhouette.objects.create(
            name="open-front vest",
            wear_family=WearFamily.TORSO_GARMENT,
            exposes_beneath=True,
        )
        open_vest = ItemInstanceFactory(template=ItemTemplateFactory(), silhouette=open_cut)
        _equip_multi(self.sheet, open_vest, [BodyRegion.TORSO], EquipmentLayer.OVER)
        visibility = compute_worn_visibility(_fresh_rows(self.sheet))
        assert visibility.is_visible(shirt.pk)
        assert visibility.is_visible(open_vest.pk)


class ShowConcealActionTests(TestCase):
    """Show opens the covering layers; conceal closes them (#2985)."""

    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterSheetFactory().character
        cls.sheet = cls.character.sheet_data
        cls.shirt = ItemInstanceFactory(
            template=ItemTemplateFactory(), holder_character_sheet=cls.sheet
        )
        _equip_multi(cls.sheet, cls.shirt, [BodyRegion.TORSO], EquipmentLayer.BASE)
        coat = ItemInstanceFactory(template=ItemTemplateFactory(), holder_character_sheet=cls.sheet)
        _equip_multi(cls.sheet, coat, [BodyRegion.TORSO], EquipmentLayer.OUTER)
        cls.coat = coat

    def test_show_piece_opens_the_layers_above_it(self):
        from actions.definitions.fashion import RevealAction

        result = RevealAction().run(actor=self.character, item_id=self.shirt.pk)
        assert result.success, result.message
        # The state lives on the covering coat, never on the shirt.
        assert EquippedItem.objects.filter(
            item_instance=self.coat, opened_at__isnull=False
        ).exists()
        visibility = compute_worn_visibility(_fresh_rows(self.sheet))
        assert visibility.is_visible(self.shirt.pk)

    def test_show_body_part_bares_down_to_skin(self):
        from actions.definitions.fashion import RevealAction

        result = RevealAction().run(actor=self.character, body_region=BodyRegion.TORSO)
        assert result.success, result.message
        # Both layers opened: the walk reaches skin.
        assert (
            EquippedItem.objects.filter(
                character=self.sheet, body_region=BodyRegion.TORSO, opened_at__isnull=False
            ).count()
            == 2
        )

    def test_show_rejects_already_visible(self):
        from actions.definitions.fashion import RevealAction

        result = RevealAction().run(actor=self.character, item_id=self.coat.pk)
        assert not result.success

    def test_show_rejects_unworn(self):
        from actions.definitions.fashion import RevealAction

        loose = ItemInstanceFactory(template=ItemTemplateFactory())
        result = RevealAction().run(actor=self.character, item_id=loose.pk)
        assert not result.success

    def test_conceal_closes_what_show_opened(self):
        from actions.definitions.fashion import CoverUpAction, RevealAction

        RevealAction().run(actor=self.character, item_id=self.shirt.pk)
        result = CoverUpAction().run(actor=self.character, item_id=self.shirt.pk)
        assert result.success, result.message
        assert not EquippedItem.objects.filter(
            character=self.sheet, opened_at__isnull=False
        ).exists()
        visibility = compute_worn_visibility(_fresh_rows(self.sheet))
        assert not visibility.is_visible(self.shirt.pk)

    def test_conceal_honest_when_nothing_covers(self):
        from actions.definitions.fashion import CoverUpAction

        result = CoverUpAction().run(actor=self.character, item_id=self.coat.pk)
        assert not result.success

    def test_dressing_recloses_opened_layers(self):
        from actions.definitions.fashion import RevealAction
        from world.items.services.equip import equip_item

        RevealAction().run(actor=self.character, body_region=BodyRegion.TORSO)
        scarf_template = ItemTemplateFactory()
        TemplateSlotFactory(
            template=scarf_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.ACCESSORY,
        )
        scarf = ItemInstanceFactory(template=scarf_template, holder_character_sheet=self.sheet)
        equip_item(
            character_sheet=self.sheet,
            item_instance=scarf,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.ACCESSORY,
        )
        assert not EquippedItem.objects.filter(
            character=self.sheet, opened_at__isnull=False
        ).exists()
