"""A soft-deleted item is held by nobody (#4099 re-review ruling).

Soft-deleting an item used to leave its ``holder_character_sheet`` and
``contained_in`` pointing where they were. Every service that checks ownership by
"fetch by pk, then compare the holder" (trade, wares, decor, boons, vaults, bequests,
ritual components, crafting permissions) and every container-chain walk (possession,
reach) then still treated the destroyed row as the holder's. The structural fix: the
soft-delete branch of ``destroy_consumed_item_instance`` and ``forfeit_item_instance``
clear both pointers; the last holder lives on the ledger event.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia import create_object

from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import OwnershipEventType
from world.items.exceptions import ItemNotInPlay
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance, OwnershipEvent
from world.items.services.usage import destroy_consumed_item_instance, forfeit_item_instance


def _carried(sheet, *, template=None, **fields) -> ItemInstance:
    obj = create_object("typeclasses.objects.Object", key="thing", nohome=True)
    obj.location = sheet.character
    obj.save()
    return ItemInstanceFactory(
        template=template or ItemTemplateFactory(value=100),
        holder_character_sheet=sheet,
        game_object=obj,
        **fields,
    )


def _with_history(instance: ItemInstance, sheet) -> ItemInstance:
    OwnershipEvent.objects.create(
        item_instance=instance, event_type=OwnershipEventType.GIVEN, to_character_sheet=sheet
    )
    return instance


def _fence_away(instance: ItemInstance) -> None:
    destroy_consumed_item_instance(
        instance, note="Sold to a fence.", event_type=OwnershipEventType.TRANSFERRED
    )


class SoftDeleteClearsOwnershipTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()

    def test_soft_delete_clears_holder_and_container_and_keeps_the_last_holder_on_the_ledger(
        self,
    ) -> None:
        pouch = _carried(self.sheet, template=ItemTemplateFactory(is_container=True))
        item = _with_history(_carried(self.sheet), self.sheet)
        item.contained_in = pouch
        item.save(update_fields=["contained_in"])

        _fence_away(item)

        item.refresh_from_db()
        self.assertIsNotNone(item.destroyed_at)
        self.assertIsNone(item.holder_character_sheet_id)
        self.assertIsNone(item.contained_in_id)
        event = item.ownership_events.get(event_type=OwnershipEventType.TRANSFERRED)
        self.assertEqual(event.from_character_sheet, self.sheet)

    def test_forfeit_clears_holder_too(self) -> None:
        item = _carried(self.sheet)
        forfeit_item_instance(item_instance=item)
        item.refresh_from_db()
        self.assertIsNone(item.holder_character_sheet_id)
        self.assertEqual(
            item.ownership_events.get(
                event_type=OwnershipEventType.TRANSFERRED
            ).from_character_sheet,
            self.sheet,
        )

    def test_a_destroyed_containers_contents_spill_to_where_it_was_still_held(self) -> None:
        pouch = _with_history(
            _carried(self.sheet, template=ItemTemplateFactory(is_container=True)), self.sheet
        )
        coin = _carried(self.sheet)
        coin.contained_in = pouch
        coin.save(update_fields=["contained_in"])
        coin.game_object.location = pouch.game_object

        _fence_away(pouch)

        coin.refresh_from_db()
        self.assertIsNone(coin.destroyed_at)
        self.assertIsNone(coin.contained_in_id)
        self.assertEqual(coin.holder_character_sheet, self.sheet)
        self.assertEqual(coin.game_object.location, self.sheet.character)
        self.assertIn(coin, list(self.sheet.character.carried_items))


class PouchExploitTests(TestCase):
    """A fenced item that was in a carried pouch must not still count as carried."""

    def test_a_fenced_item_from_a_carried_pouch_cannot_be_dropped_given_or_equipped(
        self,
    ) -> None:
        sheet = CharacterSheetFactory()
        pouch = _carried(sheet, template=ItemTemplateFactory(is_container=True))
        item = _with_history(_carried(sheet), sheet)
        item.contained_in = pouch
        item.save(update_fields=["contained_in"])
        item.game_object.location = pouch.game_object

        _fence_away(item)

        actor = CharacterState(sheet.character, context=MagicMock())
        state = ItemState(item, context=MagicMock())
        self.assertFalse(state.can_drop(dropper=actor))
        self.assertFalse(state.can_give(giver=actor, recipient=actor))
        self.assertFalse(state.can_equip(wearer=actor))


class FencedWareAndDecorTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona

    def test_a_fenced_ware_cannot_be_listed(self) -> None:
        from world.items.market.models import MarketSquare, MarketStall
        from world.items.market.services import MarketServiceError, list_ware

        ware = _with_history(_carried(self.sheet, crafter_character_sheet=self.sheet), self.sheet)
        _fence_away(ware)
        from world.areas.models import Area

        square = MarketSquare.objects.create(
            name="Fence Square", area=Area.objects.create(name="Fence Ward", level=20)
        )
        stall = MarketStall.objects.create(square=square, name="Wares")
        with self.assertRaises(MarketServiceError):
            list_ware(stall=stall, seller=self.persona, item_instance=ware, price=10)

    def test_fenced_decor_cannot_be_placed(self) -> None:
        from world.buildings.factories import DecorationKindFactory
        from world.buildings.services import (
            DecorationPlacementError,
            _validate_crafted_decoration_placement,
        )

        template = ItemTemplateFactory()
        piece = _with_history(_carried(self.sheet, template=template), self.sheet)
        _fence_away(piece)
        with self.assertRaises(DecorationPlacementError):
            _validate_crafted_decoration_placement(
                kind=DecorationKindFactory(crafted_item_template=template),
                item_instance=piece,
                buyer_persona=self.persona,
            )


class TouchstoneRespendTests(TestCase):
    def setUp(self) -> None:
        from world.magic.factories import (
            CharacterResonanceFactory,
            ResonanceFactory,
            ResonanceTierFactory,
            RitualComponentRequirementFactory,
            RitualFactory,
        )

        self.sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        tier = ResonanceTierFactory(tier_level=1)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=resonance)
        self.ritual = RitualFactory()
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=tier
        )
        self.touchstone = _carried(
            self.sheet,
            template=ItemTemplateFactory(tied_resonance=resonance, resonance_tier=tier),
            attuned_to_character_sheet=self.sheet,
            custom_name="Mother's fang",
        )

    def _perform(self) -> None:
        from world.magic.services.ritual_components import resolve_and_consume_ritual_components

        resolve_and_consume_ritual_components(
            ritual=self.ritual, components=[self.touchstone], performer_sheet=self.sheet
        )

    def test_a_spent_touchstone_cannot_be_offered_again_through_the_web(self) -> None:
        from rest_framework import serializers

        from world.magic.serializers import RitualPerformRequestSerializer

        self._perform()
        with self.assertRaises(serializers.ValidationError):
            RitualPerformRequestSerializer().validate(
                {"character_sheet_id": self.sheet, "components": [self.touchstone]}
            )

    def test_a_spent_touchstone_does_not_satisfy_a_second_ritual(self) -> None:
        from world.magic.exceptions import RitualComponentError

        self._perform()
        with self.assertRaises(RitualComponentError):
            self._perform()


class DestroyedItemRefusedTests(TestCase):
    """Minor sites: each refuses a destroyed item."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona
        self.item = _with_history(_carried(self.sheet), self.sheet)
        _fence_away(self.item)

    def test_org_vault_deposit_refuses(self) -> None:
        from world.items.services.org_vault import deposit_item_to_vault
        from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory

        org = OrganizationFactory()
        OrganizationMembershipFactory(persona=self.persona, organization=org, rank=1)
        with self.assertRaises(ValidationError):
            deposit_item_to_vault(organization=org, persona=self.persona, item_instance=self.item)

    def test_a_specific_bequest_of_a_destroyed_item_is_adeemed(self) -> None:
        from world.estates.constants import BequestKind
        from world.estates.factories import BequestFactory, WillFactory
        from world.estates.services import _deliver_specific_item

        bequest = BequestFactory(
            will=WillFactory(character_sheet=self.sheet),
            kind=BequestKind.SPECIFIC_ITEM,
            item=self.item,
        )
        heir = CharacterSheetFactory().primary_persona
        self.assertIsNone(_deliver_specific_item(self.sheet, bequest, heir))
        self.item.refresh_from_db()
        self.assertIsNone(self.item.holder_character_sheet_id)

    def test_gem_cut_serializer_refuses(self) -> None:
        from world.items.serializers import GemCutWriteSerializer

        serializer = GemCutWriteSerializer(data={"item_instance": self.item.pk})
        self.assertFalse(serializer.is_valid())

    def test_facet_and_style_attach_refuse(self) -> None:
        from world.items.services.facets import assert_facet_attachable
        from world.items.services.styles import assert_style_attachable

        with self.assertRaises(ItemNotInPlay):
            assert_facet_attachable(self.item, MagicMock())
        with self.assertRaises(ItemNotInPlay):
            assert_style_attachable(self.item, MagicMock())

    def test_market_crafting_service_refuses(self) -> None:
        from world.items.market.services import MarketServiceError, run_service_craft

        with self.assertRaises(MarketServiceError):
            run_service_craft(
                offer=MagicMock(),
                buyer=self.persona,
                buyer_character=self.sheet.character,
                item_instance=self.item,
                target=None,
            )

    def test_write_permission_does_not_pass_for_a_destroyed_item(self) -> None:
        from world.items.views import _user_holds_item

        self.assertFalse(_user_holds_item(MagicMock(), self.item))


class RecycleEquippedTests(TestCase):
    def test_recycling_an_equipped_item_does_not_crash(self) -> None:
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import EquippedItemFactory
        from world.items.models import EquippedItem
        from world.items.services.recycle import recycle_item

        sheet = CharacterSheetFactory()
        item = _carried(sheet)
        EquippedItemFactory(
            character=sheet,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        recycle_item(item_instance=item, actor_sheet=sheet)
        self.assertFalse(EquippedItem.objects.filter(item_instance_id=item.pk).exists())


class ReclamationOfDestroyedItemsTests(TestCase):
    def test_the_last_holder_of_a_destroyed_item_is_read_from_the_ledger(self) -> None:
        from world.items.services.provenance import last_holder

        sheet = CharacterSheetFactory()
        item = _with_history(_carried(sheet), sheet)
        self.assertEqual(last_holder(item), sheet)
        _fence_away(item)
        self.assertEqual(last_holder(item), sheet)

    def test_reclamation_never_re_points_a_holder_at_a_destroyed_item(self) -> None:
        from types import SimpleNamespace

        from world.items.services.reclamation import ReclamationError, _return_item

        sheet = CharacterSheetFactory()
        item = _with_history(_carried(sheet), sheet)
        _fence_away(item)
        claim = SimpleNamespace(pk=1, item_instance=item, claimant_sheet=sheet)
        with self.assertRaises(ReclamationError):
            _return_item(claim, "recovered_lawful")
        item.refresh_from_db()
        self.assertIsNone(item.holder_character_sheet_id)
