"""Visible equipment resolution under an asserted public persona."""

from dataclasses import replace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from actions.target_menu_types import MenuTargetKind, MenuTargetRequest
from actions.target_resolution import resolve_menu_target
from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import register_detection
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, TemplateSlotFactory
from world.items.models import EquippedItem
from world.items.services.equip import equip_item, unequip_item
from world.roster.factories import RosterEntryFactory
from world.scenes.services import create_mask, set_active_persona


class WornTargetContextTests(TestCase):
    def setUp(self) -> None:
        self.room = RoomProfileFactory().objectdb
        self.other_room = RoomProfileFactory().objectdb
        self.actor_sheet = RosterEntryFactory().character_sheet
        self.actor = self.actor_sheet.character
        self.actor.location = self.room
        self.sheet = RosterEntryFactory().character_sheet
        self.wearer = self.sheet.character
        self.wearer.location = self.room
        self.primary = self.sheet.primary_persona
        self.mask = create_mask(self.sheet, name="A Grey Hood")
        self.shirt = self._item("Covered shirt", EquipmentLayer.BASE)
        self.coat = self._item("Visible coat", EquipmentLayer.OVER)
        self.request = MenuTargetRequest(
            kind=MenuTargetKind.ITEMS,
            target_id=self.coat.pk,
            owner_persona_id=self.mask.pk,
        )

    def _item(self, name, layer, *, physical=True, equipped=True):
        template = ItemTemplateFactory(name=name)
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=layer,
        )
        obj = ObjectDBFactory(location=self.wearer) if physical else None
        item = ItemInstanceFactory(
            template=template,
            game_object=obj,
            holder_character_sheet=self.sheet,
        )
        if equipped:
            equip_item(
                character_sheet=self.sheet,
                item_instance=item,
                body_region=BodyRegion.TORSO,
                equipment_layer=layer,
            )
        return item

    def _conceal(self, target):
        category = ConditionCategoryFactory(conceals_from_perception=True)
        template = ConditionTemplateFactory(category=category)
        return ConditionInstanceFactory(target=target, condition=template)

    def test_active_mask_resolves_exact_visible_item_without_owner_label(self):
        result = resolve_menu_target(self.actor, self.request)
        assert result is not None
        assert result.item == self.coat
        assert result.game_object == self.coat.game_object
        assert result.label == self.coat.display_name
        assert result.request == self.request

    def test_inactive_primary_and_old_mask_are_unavailable(self):
        assert (
            resolve_menu_target(
                self.actor,
                replace(self.request, owner_persona_id=self.primary.pk),
            )
            is None
        )
        set_active_persona(self.sheet, self.primary)
        assert resolve_menu_target(self.actor, self.request) is None

    def test_absent_wrong_and_malformed_owner_are_neutral(self):
        wrong = self.actor_sheet.primary_persona.pk
        for owner_id in (999999999, wrong, 0, -1, True, "1"):
            with self.subTest(owner_id=owner_id):
                assert (
                    resolve_menu_target(
                        self.actor,
                        replace(self.request, owner_persona_id=owner_id),
                    )
                    is None
                )

    def test_hidden_layer_and_private_carried_inventory_are_unavailable(self):
        private = self._item("Private carried", EquipmentLayer.ACCESSORY, equipped=False)
        for item in (self.shirt, private):
            assert (
                resolve_menu_target(
                    self.actor,
                    replace(self.request, target_id=item.pk),
                )
                is None
            )
        assert (
            resolve_menu_target(
                self.actor,
                replace(self.request, owner_persona_id=None),
            )
            is None
        )

    def test_concealed_wearer_stops_before_layer_enumeration_and_detection_restores(self):
        self._conceal(self.wearer)
        with patch("actions.target_resolution.visible_worn_items_for") as layers:
            assert resolve_menu_target(self.actor, self.request) is None
            layers.assert_not_called()
        register_detection(self.actor_sheet, self.wearer)
        assert resolve_menu_target(self.actor, self.request) is not None

    def test_remote_and_unlocated_wearer_are_unavailable(self):
        for location in (self.other_room, None):
            self.wearer.location = location
            assert resolve_menu_target(self.actor, self.request) is None
        self.actor.location = None
        assert resolve_menu_target(self.actor, self.request) is None

    def test_item_concealment_is_not_overridden_by_owner_context(self):
        self._conceal(self.coat.game_object)
        assert resolve_menu_target(self.actor, self.request) is None

    def test_warmed_handler_then_service_equip_sees_physical_and_row_only_items(self):
        assert resolve_menu_target(self.actor, self.request) is not None
        handler = self.wearer.equipped_items
        assert {row.item_instance_id for row in handler} == {self.shirt.pk, self.coat.pk}
        for physical in (True, False):
            with self.subTest(physical=physical):
                item = self._item(
                    f"New covering cloak physical={physical}",
                    EquipmentLayer.OUTER,
                    physical=physical,
                    equipped=False,
                )
                request = replace(self.request, target_id=item.pk)
                assert resolve_menu_target(self.actor, request) is None
                equipped = equip_item(
                    character_sheet=self.sheet,
                    item_instance=item,
                    body_region=BodyRegion.TORSO,
                    equipment_layer=EquipmentLayer.OUTER,
                )
                # No test-side invalidate: mutation must update this reader's handler.
                result = resolve_menu_target(self.actor, request)
                assert result is not None
                assert result.item == item
                assert result.game_object == item.game_object
                if not physical:
                    assert result.game_object is None
                assert resolve_menu_target(self.actor, self.request) is None
                unequip_item(equipped_item=equipped)
                assert resolve_menu_target(self.actor, request) is None
                assert resolve_menu_target(self.actor, self.request) is not None

    def test_service_unequip_exposes_underlying_layer_after_warmed_read(self):
        assert resolve_menu_target(self.actor, self.request) is not None
        shirt_request = replace(self.request, target_id=self.shirt.pk)
        assert resolve_menu_target(self.actor, shirt_request) is None
        equipped = EquippedItem.objects.get(character=self.sheet, item_instance=self.coat)
        unequip_item(equipped_item=equipped)
        assert resolve_menu_target(self.actor, self.request) is None
        result = resolve_menu_target(self.actor, shirt_request)
        assert result is not None
        assert result.item == self.shirt

    def test_direct_deleted_row_cannot_reuse_warmed_equipment_authority(self):
        assert resolve_menu_target(self.actor, self.request) is not None
        EquippedItem.objects.filter(item_instance=self.coat).delete()
        # Deliberately leave the warmed layer handler untouched.
        assert resolve_menu_target(self.actor, self.request) is None

    def test_physical_item_moved_even_with_stale_equipment_is_unavailable(self):
        assert resolve_menu_target(self.actor, self.request) is not None
        self.coat.game_object.location = self.room
        assert resolve_menu_target(self.actor, self.request) is None
        # A matching owner assertion must not fall back to ordinary room scope.
        assert (
            resolve_menu_target(
                self.actor,
                replace(self.request, owner_persona_id=None),
            )
            is not None
        )

    def test_changed_holder_containment_or_destruction_is_unavailable(self):
        self.coat.holder_character_sheet = self.actor_sheet
        self.coat.save(update_fields=["holder_character_sheet"])
        assert resolve_menu_target(self.actor, self.request) is None
        self.coat.holder_character_sheet = self.sheet
        self.coat.contained_in = self.shirt
        self.coat.save(update_fields=["holder_character_sheet", "contained_in"])
        assert resolve_menu_target(self.actor, self.request) is None
        self.coat.contained_in = None
        self.coat.destroyed_at = timezone.now()
        self.coat.save(update_fields=["contained_in", "destroyed_at"])
        assert resolve_menu_target(self.actor, self.request) is None

    def test_row_only_visible_equipment_stays_row_only(self):
        item = self._item("Visible brooch", EquipmentLayer.ACCESSORY, physical=False)
        result = resolve_menu_target(self.actor, replace(self.request, target_id=item.pk))
        assert result is not None
        assert result.item == item
        assert result.game_object is None

    def test_container_and_other_kinds_never_gain_scope(self):
        assert (
            resolve_menu_target(
                self.actor,
                replace(self.request, container_item_id=self.shirt.pk),
            )
            is None
        )
        for kind in (MenuTargetKind.OBJECTS, MenuTargetKind.EXITS, MenuTargetKind.PLACES):
            assert resolve_menu_target(self.actor, replace(self.request, kind=kind)) is None

    def test_self_context_uses_existing_layer_bypass(self):
        result = resolve_menu_target(
            self.wearer,
            replace(self.request, target_id=self.shirt.pk),
        )
        assert result is not None
        assert result.item == self.shirt

    def test_concealed_self_resolves_covered_item_but_keeps_item_authority(self):
        self._conceal(self.wearer)
        request = replace(self.request, target_id=self.shirt.pk)
        result = resolve_menu_target(self.wearer, request)
        assert result is not None
        assert result.item == self.shirt
        assert (
            resolve_menu_target(
                self.wearer,
                replace(request, owner_persona_id=self.primary.pk),
            )
            is None
        )
        self._conceal(self.shirt.game_object)
        assert resolve_menu_target(self.wearer, request) is None
        register_detection(self.sheet, self.shirt.game_object)
        assert resolve_menu_target(self.wearer, request) is not None
        EquippedItem.objects.filter(item_instance=self.shirt).delete()
        assert resolve_menu_target(self.wearer, request) is None

    def test_item_detection_is_independent_of_wearer_detection_and_layers(self):
        self._conceal(self.wearer)
        first = self._conceal(self.coat.game_object)
        second = self._conceal(self.coat.game_object)
        register_detection(self.actor_sheet, self.wearer)
        assert resolve_menu_target(self.actor, self.request) is None
        first.detected_by.add(self.actor_sheet)
        assert resolve_menu_target(self.actor, self.request) is None
        second.detected_by.add(self.sheet)
        assert resolve_menu_target(self.actor, self.request) is None
        second.detected_by.add(self.actor_sheet)
        assert resolve_menu_target(self.actor, self.request) is not None
        second.detected_by.remove(self.actor_sheet)
        assert resolve_menu_target(self.actor, self.request) is None
        second.is_suppressed = True
        second.save(update_fields=["is_suppressed"])
        assert resolve_menu_target(self.actor, self.request) is not None
        shirt_request = replace(self.request, target_id=self.shirt.pk)
        assert resolve_menu_target(self.actor, shirt_request) is None
        self.wearer.location = self.other_room
        assert resolve_menu_target(self.actor, self.request) is None

    def test_detected_item_still_requires_exact_wearer_location_and_live_equipment(self):
        self._conceal(self.coat.game_object)
        register_detection(self.actor_sheet, self.coat.game_object)
        assert resolve_menu_target(self.actor, self.request) is not None
        self.coat.game_object.location = self.room
        assert resolve_menu_target(self.actor, self.request) is None
        self.coat.game_object.location = self.wearer
        assert resolve_menu_target(self.actor, self.request) is not None
        EquippedItem.objects.filter(item_instance=self.coat).delete()
        assert resolve_menu_target(self.actor, self.request) is None
