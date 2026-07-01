"""Tests for item-specific actions (equip, unequip, put_in, take_out)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.constants import TargetKind
from actions.definitions.items import (
    EquipAction,
    PutInAction,
    TakeOutAction,
    UnequipAction,
    UseItemAction,
)
from actions.prerequisites import (
    HoldsItemPrerequisite,
    ItemUsablePrerequisite,
    OnUseTargetPrerequisite,
)
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.items.services import equip_item


class EquipActionTests(TestCase):
    def _build_actor_and_item(self) -> tuple:
        room = ObjectDBFactory(
            db_key="EquipActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        account = AccountFactory(username="equip_action_account")
        actor = CharacterFactory(db_key="EquipActionAlice", location=room)
        actor.db_account = account
        actor.save()
        CharacterSheetFactory(character=actor)

        template = ItemTemplateFactory(name="Equip Action Shirt")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item_obj = ObjectDBFactory(db_key="EquipActionShirt", location=actor)
        item_instance = ItemInstanceFactory(template=template, game_object=item_obj)
        return room, actor, item_obj, item_instance

    def test_equip_creates_equipped_row(self) -> None:
        room, actor, item_obj, item_instance = self._build_actor_and_item()

        action = EquipAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj)

        assert result.success is True
        assert EquippedItem.objects.filter(
            character=actor,
            item_instance=item_instance,
        ).exists()

    def test_equip_without_item_instance_fails_gracefully(self) -> None:
        room = ObjectDBFactory(
            db_key="EquipActionNoInstanceRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="EquipActionNoInstanceActor", location=room)
        bare_object = ObjectDBFactory(db_key="EquipActionBareObject", location=actor)

        action = EquipAction()
        result = action.run(actor, target=bare_object)
        assert result.success is False
        assert result.message == "That can't be equipped."

    def test_equip_inventory_error_surfaces_user_message(self) -> None:
        """A denied equip surfaces the typed exception's user_message."""
        _room, actor, item_obj, _ = self._build_actor_and_item()

        from world.items.exceptions import PermissionDenied

        action = EquipAction()
        with patch(
            "actions.definitions.items.equip",
            side_effect=PermissionDenied,
        ):
            result = action.run(actor, target=item_obj)

        assert result.success is False
        assert result.message == PermissionDenied.user_message


class UnequipActionTests(TestCase):
    def test_unequip_removes_equipped_row(self) -> None:
        room = ObjectDBFactory(
            db_key="UnequipActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="UnequipActionAlice", location=room)
        sheet = CharacterSheetFactory(character=actor)

        template = ItemTemplateFactory(name="Unequip Action Shirt")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item_obj = ObjectDBFactory(db_key="UnequipActionShirt", location=actor)
        item_instance = ItemInstanceFactory(template=template, game_object=item_obj)
        equip_item(
            character_sheet=sheet,
            item_instance=item_instance,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        action = UnequipAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj)

        assert result.success is True
        assert not EquippedItem.objects.filter(item_instance=item_instance).exists()

    def test_unequip_when_not_equipped_surfaces_user_message(self) -> None:
        room = ObjectDBFactory(
            db_key="UnequipActionNotEquippedRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="UnequipActionNotEquippedActor", location=room)

        template = ItemTemplateFactory(name="Unequip Action NotEquipped Shirt")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        item_obj = ObjectDBFactory(
            db_key="UnequipActionNotEquippedShirt",
            location=actor,
        )
        ItemInstanceFactory(template=template, game_object=item_obj)

        action = UnequipAction()
        result = action.run(actor, target=item_obj)
        assert result.success is False

        from world.items.exceptions import NotEquipped

        assert result.message == NotEquipped.user_message


class PutInActionTests(TestCase):
    def _build_scene(self) -> tuple:
        room = ObjectDBFactory(
            db_key="PutInActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="PutInActionAlice", location=room)

        container_template = ItemTemplateFactory(
            name="PutInAction Bag",
            is_container=True,
            container_capacity=2,
            container_max_item_size=5,
            supports_open_close=True,
        )
        container_obj = ObjectDBFactory(db_key="PutInActionBag", location=actor)
        container = ItemInstanceFactory(
            template=container_template,
            game_object=container_obj,
            is_open=True,
        )

        item_template = ItemTemplateFactory(name="PutInAction Coin", size=1)
        item_obj = ObjectDBFactory(db_key="PutInActionCoin", location=actor)
        item_instance = ItemInstanceFactory(template=item_template, game_object=item_obj)
        return room, actor, item_obj, item_instance, container_obj, container

    def test_put_in_sets_contained_in(self) -> None:
        room, actor, item_obj, item_instance, container_obj, container = self._build_scene()

        action = PutInAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj, container=container_obj)

        assert result.success is True
        item_instance.refresh_from_db()
        assert item_instance.contained_in == container

    def test_put_in_missing_container_arg_fails(self) -> None:
        room = ObjectDBFactory(
            db_key="PutInActionMissingContainerRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="PutInActionMissingContainerActor", location=room)
        item_obj = ObjectDBFactory(db_key="PutInActionMissingContainerItem", location=actor)
        ItemInstanceFactory(game_object=item_obj)

        action = PutInAction()
        result = action.run(actor, target=item_obj)
        assert result.success is False
        assert result.message == "Put what into what?"

    def test_put_in_closed_container_surfaces_user_message(self) -> None:
        _room, actor, item_obj, _, container_obj, container = self._build_scene()
        container.is_open = False
        container.save()

        action = PutInAction()
        result = action.run(actor, target=item_obj, container=container_obj)
        assert result.success is False

        from world.items.exceptions import ContainerClosed

        assert result.message == ContainerClosed.user_message

    def test_put_in_non_item_container_fails_gracefully(self) -> None:
        """Container without an ItemInstance row returns a clean error."""
        room = ObjectDBFactory(
            db_key="PutInActionBareContainerRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="PutInActionBareContainerActor", location=room)
        item_obj = ObjectDBFactory(db_key="PutInActionItemForBare", location=actor)
        ItemInstanceFactory(game_object=item_obj)
        bare_container = ObjectDBFactory(
            db_key="PutInActionBareContainer",
            location=actor,
        )

        action = PutInAction()
        result = action.run(actor, target=item_obj, container=bare_container)
        assert result.success is False
        assert result.message == "That isn't a container."


class TakeOutActionTests(TestCase):
    def _build_scene(self) -> tuple:
        room = ObjectDBFactory(
            db_key="TakeOutActionRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="TakeOutActionAlice", location=room)

        container_template = ItemTemplateFactory(
            name="TakeOutAction Box",
            is_container=True,
        )
        container_obj = ObjectDBFactory(db_key="TakeOutActionBox", location=actor)
        container = ItemInstanceFactory(
            template=container_template,
            game_object=container_obj,
        )

        item_obj = ObjectDBFactory(db_key="TakeOutActionItem", location=container_obj)
        item_instance = ItemInstanceFactory(game_object=item_obj, contained_in=container)
        return room, actor, item_obj, item_instance, container

    def test_take_out_clears_contained_in_and_moves_to_actor(self) -> None:
        room, actor, item_obj, item_instance, _container = self._build_scene()

        action = TakeOutAction()
        with patch.object(room, "msg_contents"):
            result = action.run(actor, target=item_obj)

        assert result.success is True
        item_instance.refresh_from_db()
        item_obj.refresh_from_db()
        assert item_instance.contained_in is None
        assert item_obj.location == actor

    def test_take_out_without_item_instance_fails_gracefully(self) -> None:
        room = ObjectDBFactory(
            db_key="TakeOutActionNoInstanceRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        actor = CharacterFactory(db_key="TakeOutActionNoInstanceActor", location=room)
        bare_object = ObjectDBFactory(db_key="TakeOutActionBareObject", location=actor)

        action = TakeOutAction()
        result = action.run(actor, target=bare_object)
        assert result.success is False
        assert result.message == "That can't be taken out."


class UseItemPrereqTests(TestCase):
    def _ctx(self, item_obj):
        return {"kwargs": {"item": item_obj}}

    def test_holds_item_fails_when_not_carried(self) -> None:
        room = ObjectDBFactory(db_key="PReqRoom", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="PReqAlice", location=room)
        item_obj = ObjectDBFactory(db_key="PReqLooseItem", location=room)  # on floor
        ItemInstanceFactory(template=ItemTemplateFactory(name="Loose"), game_object=item_obj)
        met, reason = HoldsItemPrerequisite().is_met(actor, context=self._ctx(item_obj))
        assert met is False
        assert reason

    def test_holds_item_passes_when_carried(self) -> None:
        actor = CharacterFactory(db_key="PReqBob")
        item_obj = ObjectDBFactory(db_key="PReqHeldItem", location=actor)
        ItemInstanceFactory(template=ItemTemplateFactory(name="Held"), game_object=item_obj)
        met, _ = HoldsItemPrerequisite().is_met(actor, context=self._ctx(item_obj))
        assert met is True

    def test_item_usable_requires_on_use_pool(self) -> None:
        actor = CharacterFactory(db_key="PReqCarl")
        item_obj = ObjectDBFactory(db_key="PReqNoPool", location=actor)
        ItemInstanceFactory(template=ItemTemplateFactory(name="NoPool"), game_object=item_obj)
        met, reason = ItemUsablePrerequisite().is_met(actor, context=self._ctx(item_obj))
        assert met is False
        assert reason

    def test_item_usable_passes_with_on_use_pool(self) -> None:
        from actions.factories import ConsequencePoolFactory

        actor = CharacterFactory(db_key="PReqDan")
        item_obj = ObjectDBFactory(db_key="PReqWithPool", location=actor)
        pool = ConsequencePoolFactory()
        template = ItemTemplateFactory(name="WithPool", on_use_pool=pool)
        ItemInstanceFactory(template=template, game_object=item_obj)
        met, _ = ItemUsablePrerequisite().is_met(actor, context=self._ctx(item_obj))
        assert met is True

    def test_item_usable_fails_consumable_with_no_charges(self) -> None:
        from actions.factories import ConsequencePoolFactory

        actor = CharacterFactory(db_key="PReqEve")
        item_obj = ObjectDBFactory(db_key="PReqDepletedConsumable", location=actor)
        pool = ConsequencePoolFactory()
        template = ItemTemplateFactory(name="DepletedPotion", on_use_pool=pool, is_consumable=True)
        ItemInstanceFactory(template=template, game_object=item_obj, charges=0)
        met, reason = ItemUsablePrerequisite().is_met(actor, context=self._ctx(item_obj))
        assert met is False
        assert reason


class OnUseTargetPrereqTests(TestCase):
    def _ctx(self, item_obj):
        return {"kwargs": {"item": item_obj}}

    def _usable_item(self, actor, kind):
        item_obj = ObjectDBFactory(db_key=f"OUT-{kind}", location=actor)
        template = ItemTemplateFactory(name=f"OUT-{kind}", on_use_target_kind=kind)
        ItemInstanceFactory(template=template, game_object=item_obj)
        return item_obj

    def test_self_only_rejects_supplied_target(self) -> None:
        actor = CharacterFactory(db_key="OUTAlice")
        other = CharacterFactory(db_key="OUTOther", location=actor.location)
        item_obj = self._usable_item(actor, None)  # on_use_target_kind null
        met, reason = OnUseTargetPrerequisite().is_met(
            actor, target=other, context=self._ctx(item_obj)
        )
        assert met is False
        assert reason

    def test_self_only_passes_without_target(self) -> None:
        actor = CharacterFactory(db_key="OUTBob")
        item_obj = self._usable_item(actor, None)
        met, _ = OnUseTargetPrerequisite().is_met(actor, target=None, context=self._ctx(item_obj))
        assert met is True

    def test_character_kind_requires_target(self) -> None:
        actor = CharacterFactory(db_key="OUTCarl")
        item_obj = self._usable_item(actor, TargetKind.CHARACTER)
        met, reason = OnUseTargetPrerequisite().is_met(
            actor, target=None, context=self._ctx(item_obj)
        )
        assert met is False
        assert reason

    def test_character_target_in_other_room_fails(self) -> None:
        room_a = ObjectDBFactory(db_key="OUTRoomA", db_typeclass_path="typeclasses.rooms.Room")
        room_b = ObjectDBFactory(db_key="OUTRoomB", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="OUTDan", location=room_a)
        far = CharacterFactory(db_key="OUTFar", location=room_b)
        item_obj = self._usable_item(actor, TargetKind.CHARACTER)
        met, reason = OnUseTargetPrerequisite().is_met(
            actor, target=far, context=self._ctx(item_obj)
        )
        assert met is False
        assert reason

    def test_character_target_same_room_passes(self) -> None:
        actor = CharacterFactory(db_key="OUTErin")
        near = CharacterFactory(db_key="OUTNear", location=actor.location)
        item_obj = self._usable_item(actor, TargetKind.CHARACTER)
        met, _ = OnUseTargetPrerequisite().is_met(actor, target=near, context=self._ctx(item_obj))
        assert met is True

    def test_character_kind_rejects_non_character_target(self) -> None:
        """CHARACTER-kind item targeting a Room in the same location must fail (type guard)."""
        room = ObjectDBFactory(db_key="OUTTypeRoom", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="OUTTypeActor", location=room)
        item_obj = self._usable_item(actor, TargetKind.CHARACTER)
        # Room is in same location as actor — would pass adjacency/visibility — but must fail type.
        met, reason = OnUseTargetPrerequisite().is_met(
            actor, target=room, context=self._ctx(item_obj)
        )
        assert met is False
        assert reason == "That can only be used on a character."

    def test_item_kind_reachable_target_passes(self) -> None:
        """ITEM-kind item targeting a carried item (reachable) must pass."""
        actor = CharacterFactory(db_key="OUTItemActor")
        item_obj = self._usable_item(actor, TargetKind.ITEM)
        target_item_obj = ObjectDBFactory(db_key="OUTItemTarget", location=actor)
        tpl = ItemTemplateFactory(name="OUTItemTargetTpl")
        ItemInstanceFactory(template=tpl, game_object=target_item_obj)
        met, _ = OnUseTargetPrerequisite().is_met(
            actor, target=target_item_obj, context=self._ctx(item_obj)
        )
        assert met is True

    def test_item_kind_unreachable_target_fails(self) -> None:
        """ITEM-kind item targeting an item in a different room must fail (reachability)."""
        room_a = ObjectDBFactory(db_key="OUTItemRoomA", db_typeclass_path="typeclasses.rooms.Room")
        room_b = ObjectDBFactory(db_key="OUTItemRoomB", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="OUTItemFarActor", location=room_a)
        item_obj = self._usable_item(actor, TargetKind.ITEM)
        far_item_obj = ObjectDBFactory(db_key="OUTItemFarTarget", location=room_b)
        ItemInstanceFactory(
            template=ItemTemplateFactory(name="OUTItemFarTpl"), game_object=far_item_obj
        )
        met, reason = OnUseTargetPrerequisite().is_met(
            actor, target=far_item_obj, context=self._ctx(item_obj)
        )
        assert met is False
        assert reason


# ---------------------------------------------------------------------------
# UseItemAction tests
# ---------------------------------------------------------------------------


def _fake_use_result():
    from world.items.types import UseItemResult

    return UseItemResult(
        applied_effects=[],
        charges_remaining=1,
        destroyed=False,
        soft_deleted=False,
        check_result=None,
    )


def _pool_with_condition_effect():
    """Build a ConsequencePool with one apply_condition effect (target=self).

    Mirrors the construction used in world/items/tests/test_item_instance_views.py
    for the use-endpoint tests.
    """
    from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
    from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
    from world.conditions.factories import ConditionTemplateFactory

    pool = ConsequencePoolFactory()
    consequence = ConsequenceFactory(label="UseItemActionEffect")
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type="apply_condition",
        target="self",
        condition_template=ConditionTemplateFactory(),
    )
    return pool


class UseItemActionTests(TestCase):
    def test_run_blocks_when_not_holding(self) -> None:
        room = ObjectDBFactory(db_key="UseRoom", db_typeclass_path="typeclasses.rooms.Room")
        actor = CharacterFactory(db_key="UseAlice", location=room)
        item_obj = ObjectDBFactory(db_key="UseLoose", location=room)  # not held
        ItemInstanceFactory(template=ItemTemplateFactory(name="UseLoose"), game_object=item_obj)
        result = UseItemAction().run(actor, item=item_obj)
        assert result.success is False

    def test_happy_path_self_use_calls_service(self) -> None:
        actor = CharacterFactory(db_key="UseBob")
        item_obj = ObjectDBFactory(db_key="UseHeld", location=actor)
        template = ItemTemplateFactory(
            name="UsePotion",
            is_consumable=True,
            max_charges=2,
            on_use_pool=_pool_with_condition_effect(),
            on_use_check_type=None,
        )
        ItemInstanceFactory(template=template, game_object=item_obj, charges=2)
        with patch("actions.definitions.items.use_item") as mock_use:
            mock_use.return_value = _fake_use_result()
            result = UseItemAction().run(actor, item=item_obj)
        assert result.success is True
        mock_use.assert_called_once()
        assert mock_use.call_args.kwargs["target"] is None  # self-use

    def test_item_error_maps_to_failure_result(self) -> None:
        """ItemError raised by use_item is caught and returned as ActionResult(success=False).

        This covers the ``except ItemError as exc:`` branch in UseItemAction.execute().
        If that clause were removed, the exception would propagate uncaught and the
        test would error rather than seeing success=False.
        """
        from world.items.exceptions import ItemNotUsable

        actor = CharacterFactory(db_key="UseItemErrorActor")
        item_obj = ObjectDBFactory(db_key="UseItemErrorItem", location=actor)
        template = ItemTemplateFactory(
            name="UseItemErrorPotion",
            is_consumable=True,
            max_charges=1,
            on_use_pool=_pool_with_condition_effect(),
            on_use_check_type=None,
            on_use_target_kind=None,
        )
        ItemInstanceFactory(template=template, game_object=item_obj, charges=1)
        with patch("actions.definitions.items.use_item", side_effect=ItemNotUsable):
            result = UseItemAction().run(actor, item=item_obj)
        assert result.success is False
        assert result.message == ItemNotUsable.user_message

    def test_happy_path_targeted_use_passes_validated_target(self) -> None:
        actor = CharacterFactory(db_key="UseCarl")
        near = CharacterFactory(db_key="UseNear", location=actor.location)
        item_obj = ObjectDBFactory(db_key="UseSalve", location=actor)
        template = ItemTemplateFactory(
            name="UseSalve",
            on_use_target_kind="character",
            is_consumable=True,
            max_charges=2,
            on_use_pool=_pool_with_condition_effect(),
            on_use_check_type=None,
        )
        ItemInstanceFactory(template=template, game_object=item_obj, charges=2)
        with patch("actions.definitions.items.use_item") as mock_use:
            mock_use.return_value = _fake_use_result()
            result = UseItemAction().run(actor, item=item_obj, target=near)
        assert result.success is True
        assert mock_use.call_args.kwargs["target"] == near


class UseItemTechniqueGrantTests(TestCase):
    """Tests that UseItemAction learns a technique via a TechniqueGrant (#1732)."""

    def setUp(self):
        from world.action_points.models import ActionPointPool
        from world.magic.constants import GiftKind, TargetKind
        from world.magic.factories import (
            GiftFactory,
            ResonanceFactory,
            TechniqueFactory,
        )
        from world.magic.models import CharacterGift, Thread

        self.sheet = CharacterSheetFactory()
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.resonance = ResonanceFactory()
        self.gift.resonances.add(self.resonance)
        CharacterGift.objects.create(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=0,
        )
        self.technique = TechniqueFactory(gift=self.gift)
        # Item template with an on-use pool (required by ItemUsablePrerequisite).
        from actions.factories import ConsequencePoolFactory

        pool = ConsequencePoolFactory()
        self.template = ItemTemplateFactory(
            is_consumable=True,
            max_charges=1,
            on_use_pool=pool,
            on_use_check_type=None,
        )
        from world.magic.models import TechniqueGrant

        self.grant = TechniqueGrant.objects.create(
            technique=self.technique,
            item_template=self.template,
            verb="study",
        )
        self.actor = self.sheet.character
        self.item_obj = ObjectDBFactory(db_key="Grimoire", location=self.actor)
        ItemInstanceFactory(template=self.template, game_object=self.item_obj, charges=1)
        self.ap_pool = ActionPointPool.get_or_create_for_character(self.actor)
        self.ap_pool.current = 200
        self.ap_pool.save()

    def test_use_item_with_grant_mints_technique(self):
        """Using an item with a TechniqueGrant learns the technique."""
        from world.items.types import UseItemResult
        from world.magic.models import CharacterTechnique

        fake_result = UseItemResult(
            applied_effects=[],
            charges_remaining=0,
            destroyed=True,
            soft_deleted=False,
            check_result=None,
        )
        with patch("actions.definitions.items.use_item", return_value=fake_result):
            result = UseItemAction().run(self.actor, item=self.item_obj)
        assert result.success
        assert CharacterTechnique.objects.filter(
            character=self.sheet, technique=self.technique
        ).exists()
