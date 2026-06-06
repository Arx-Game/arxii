"""Phase F tests — items polish + fashion (#676)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory
from world.buildings.models import BuildingPolish, PolishCategory, RoomPolish
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.items.models import RoomItem
from world.items.polish_services import (
    can_equip_item,
    place_item_in_room,
    recompute_persona_prestige_from_items,
    remove_item_from_room,
)


def _make_primary_persona():
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


def _make_decorative_template(polish_value: int, category: PolishCategory):
    return ItemTemplateFactory(polish_value=polish_value, polish_category=category)


class PlaceItemInRoomTests(TestCase):
    def test_place_adds_room_polish(self) -> None:
        tenant = _make_primary_persona()
        room = RoomProfileFactory()
        room.tenant_persona = tenant
        room.save(update_fields=["tenant_persona"])
        cat = PolishCategory.objects.create(name="Elegance")
        template = _make_decorative_template(polish_value=15, category=cat)
        instance = ItemInstanceFactory(template=template)

        placement = place_item_in_room(instance, room)

        self.assertIsNotNone(placement)
        rp = RoomPolish.objects.get(room=room, category=cat)
        self.assertEqual(rp.value, 15)
        tenant.refresh_from_db()
        self.assertEqual(tenant.prestige_from_dwellings, 15)

    def test_place_zero_polish_template_no_room_polish(self) -> None:
        room = RoomProfileFactory()
        template = ItemTemplateFactory(polish_value=0)
        instance = ItemInstanceFactory(template=template)
        place_item_in_room(instance, room)
        self.assertFalse(RoomPolish.objects.exists())

    def test_place_when_equipped_returns_none(self) -> None:
        tenant = _make_primary_persona()
        room = RoomProfileFactory()
        cat = PolishCategory.objects.create(name="Elegance")
        template = _make_decorative_template(polish_value=5, category=cat)
        instance = ItemInstanceFactory(template=template)
        EquippedItemFactory(
            character=tenant.character_sheet.character,
            item_instance=instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        result = place_item_in_room(instance, room)
        self.assertIsNone(result)
        self.assertFalse(RoomPolish.objects.exists())

    def test_place_again_in_same_room_is_idempotent(self) -> None:
        room = RoomProfileFactory()
        cat = PolishCategory.objects.create(name="Elegance")
        template = _make_decorative_template(polish_value=20, category=cat)
        instance = ItemInstanceFactory(template=template)
        place_item_in_room(instance, room)
        place_item_in_room(instance, room)
        rp = RoomPolish.objects.get(room=room, category=cat)
        # Polish does NOT stack with idempotent re-placement.
        self.assertEqual(rp.value, 20)

    def test_move_between_rooms_subtracts_old_adds_new(self) -> None:
        room_a = RoomProfileFactory()
        room_b = RoomProfileFactory()
        cat = PolishCategory.objects.create(name="Elegance")
        template = _make_decorative_template(polish_value=30, category=cat)
        instance = ItemInstanceFactory(template=template)

        place_item_in_room(instance, room_a)
        place_item_in_room(instance, room_b)

        self.assertFalse(RoomItem.objects.filter(room=room_a).exists())
        self.assertEqual(RoomPolish.objects.get(room=room_a, category=cat).value, 0)
        self.assertEqual(RoomPolish.objects.get(room=room_b, category=cat).value, 30)


class RemoveItemFromRoomTests(TestCase):
    def test_remove_subtracts_polish(self) -> None:
        tenant = _make_primary_persona()
        room = RoomProfileFactory()
        room.tenant_persona = tenant
        room.save(update_fields=["tenant_persona"])
        cat = PolishCategory.objects.create(name="Elegance")
        template = _make_decorative_template(polish_value=12, category=cat)
        instance = ItemInstanceFactory(template=template)
        place_item_in_room(instance, room)

        result = remove_item_from_room(instance)

        self.assertTrue(result)
        self.assertFalse(RoomItem.objects.filter(item_instance=instance).exists())
        rp = RoomPolish.objects.get(room=room, category=cat)
        self.assertEqual(rp.value, 0)
        tenant.refresh_from_db()
        self.assertEqual(tenant.prestige_from_dwellings, 0)

    def test_remove_when_not_placed_returns_false(self) -> None:
        template = ItemTemplateFactory()
        instance = ItemInstanceFactory(template=template)
        self.assertFalse(remove_item_from_room(instance))


class EquipItemPolishTests(TestCase):
    def test_recompute_sums_equipped_polish(self) -> None:
        persona = _make_primary_persona()
        cat = PolishCategory.objects.create(name="Opulence")
        t1 = _make_decorative_template(polish_value=10, category=cat)
        t2 = _make_decorative_template(polish_value=25, category=cat)
        i1 = ItemInstanceFactory(template=t1)
        i2 = ItemInstanceFactory(template=t2)
        EquippedItemFactory(
            character=persona.character_sheet.character,
            item_instance=i1,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        EquippedItemFactory(
            character=persona.character_sheet.character,
            item_instance=i2,
            body_region=BodyRegion.HEAD,
            equipment_layer=EquipmentLayer.BASE,
        )

        result = recompute_persona_prestige_from_items(persona)

        self.assertEqual(result, 35)
        persona.refresh_from_db()
        self.assertEqual(persona.prestige_from_items, 35)
        self.assertEqual(persona.total_prestige, 35)

    def test_recompute_skips_zero_polish_items(self) -> None:
        persona = _make_primary_persona()
        functional_template = ItemTemplateFactory(polish_value=0)
        instance = ItemInstanceFactory(template=functional_template)
        EquippedItemFactory(
            character=persona.character_sheet.character,
            item_instance=instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        result = recompute_persona_prestige_from_items(persona)
        self.assertEqual(result, 0)

    def test_recompute_with_no_equipment(self) -> None:
        persona = _make_primary_persona()
        result = recompute_persona_prestige_from_items(persona)
        self.assertEqual(result, 0)


class PlaceEquipMutualExclusionTests(TestCase):
    def test_can_equip_returns_false_when_placed(self) -> None:
        room = RoomProfileFactory()
        cat = PolishCategory.objects.create(name="Elegance")
        template = _make_decorative_template(polish_value=5, category=cat)
        instance = ItemInstanceFactory(template=template)
        place_item_in_room(instance, room)
        self.assertFalse(can_equip_item(instance))

    def test_can_equip_returns_true_when_not_placed(self) -> None:
        template = ItemTemplateFactory()
        instance = ItemInstanceFactory(template=template)
        self.assertTrue(can_equip_item(instance))


class RoomItemRollUpTests(TestCase):
    def test_placed_item_polish_rolls_up_to_building_owner(self) -> None:
        owner = _make_primary_persona()
        tenant = _make_primary_persona()
        area = AreaFactory(level=10)
        BuildingFactory(area=area, owner_persona=owner)
        room = RoomProfileFactory(area=area)
        room.tenant_persona = tenant
        room.save(update_fields=["tenant_persona"])
        cat = PolishCategory.objects.create(name="Elegance")
        template = _make_decorative_template(polish_value=50, category=cat)
        instance = ItemInstanceFactory(template=template)

        place_item_in_room(instance, room)

        owner.refresh_from_db()
        tenant.refresh_from_db()
        # Both tenant and owner credited via apply_room_polish_delta.
        self.assertEqual(tenant.prestige_from_dwellings, 50)
        self.assertEqual(owner.prestige_from_dwellings, 50)
        # BuildingPolish aggregate NOT touched by item placement directly —
        # item polish is room polish, not building polish.
        self.assertFalse(BuildingPolish.objects.exists())
