"""Tests for LookAtItemAction."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.perception import LookAtItemAction
from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem


class LookAtItemActionTests(TestCase):
    def setUp(self) -> None:
        self.actor = CharacterFactory(db_key="LookActor")
        self.actor_account = AccountFactory(username="actor_account")
        self.actor_account.is_staff = False
        self.actor_account.save()
        self.actor.db_account = self.actor_account
        self.actor.save()

        self.target = CharacterFactory(db_key="LookTarget")
        self.target.db.desc = "A poised stranger."
        self.target.save()

    def _equip(
        self,
        character,
        name: str,
        region: str,
        layer: str,
        *,
        covers: bool = False,
    ):
        template = ItemTemplateFactory(name=name)
        TemplateSlotFactory(
            template=template,
            body_region=region,
            equipment_layer=layer,
            covers_lower_layers=covers,
        )
        item_obj = ObjectDBFactory(
            db_key=f"{name}_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item = ItemInstanceFactory(template=template, game_object=item_obj)
        EquippedItem.objects.create(
            character=character,
            item_instance=item,
            body_region=region,
            equipment_layer=layer,
        )
        return item

    def test_visible_item_on_owner_returns_appearance(self) -> None:
        self._equip(self.target, "Hat", BodyRegion.HEAD, EquipmentLayer.OUTER)
        action = LookAtItemAction()
        result = action.run(self.actor, owner_id=self.target.pk, item_name="hat")
        self.assertTrue(result.success)
        self.assertIn("Hat", result.message or "")

    def test_concealed_item_for_other_observer_fails(self) -> None:
        # Coat covers shirt; non-staff observer can't see shirt.
        self._equip(
            self.target,
            "Coat",
            BodyRegion.TORSO,
            EquipmentLayer.OVER,
            covers=True,
        )
        self._equip(self.target, "Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        action = LookAtItemAction()
        result = action.run(self.actor, owner_id=self.target.pk, item_name="shirt")
        self.assertFalse(result.success)
        self.assertIn("don't see", (result.message or "").lower())

    def test_self_can_see_concealed(self) -> None:
        # Concealed shirt visible when looking at self.
        self._equip(
            self.actor,
            "Coat",
            BodyRegion.TORSO,
            EquipmentLayer.OVER,
            covers=True,
        )
        self._equip(self.actor, "Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        action = LookAtItemAction()
        result = action.run(self.actor, owner_id=self.actor.pk, item_name="shirt")
        self.assertTrue(result.success)

    def test_staff_can_see_concealed(self) -> None:
        # Staff actor can see concealed items.
        self.actor_account.is_staff = True
        self.actor_account.save()
        self._equip(
            self.target,
            "Coat",
            BodyRegion.TORSO,
            EquipmentLayer.OVER,
            covers=True,
        )
        self._equip(self.target, "Shirt", BodyRegion.TORSO, EquipmentLayer.BASE)
        action = LookAtItemAction()
        result = action.run(self.actor, owner_id=self.target.pk, item_name="shirt")
        self.assertTrue(result.success)

    def test_unknown_item_name_fails(self) -> None:
        action = LookAtItemAction()
        result = action.run(
            self.actor,
            owner_id=self.target.pk,
            item_name="nonexistent",
        )
        self.assertFalse(result.success)

    def test_no_owner_or_container_fails(self) -> None:
        action = LookAtItemAction()
        result = action.run(self.actor, item_name="hat")
        self.assertFalse(result.success)


class LookAtItemActionContainerTests(TestCase):
    def setUp(self) -> None:
        self.actor = CharacterFactory(db_key="ContActor")
        self.actor_account = AccountFactory(username="cont_actor_account")
        self.actor_account.is_staff = False
        self.actor_account.save()
        self.actor.db_account = self.actor_account
        self.actor.save()

    def _make_container(self, *, is_open: bool = True):
        template = ItemTemplateFactory(
            name="Pouch",
            is_container=True,
            container_capacity=10,
            supports_open_close=True,
        )
        container_obj = ObjectDBFactory(
            db_key="pouch_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        return ItemInstanceFactory(
            template=template,
            game_object=container_obj,
            is_open=is_open,
        )

    def _put_in_container(self, container, name: str):
        item_template = ItemTemplateFactory(name=name)
        item_obj = ObjectDBFactory(
            db_key=f"{name}_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        return ItemInstanceFactory(
            template=item_template,
            game_object=item_obj,
            contained_in=container,
        )

    def test_open_container_returns_item_appearance(self) -> None:
        container = self._make_container(is_open=True)
        self._put_in_container(container, "GoldCoin")
        action = LookAtItemAction()
        result = action.run(
            self.actor,
            container_id=container.game_object.pk,
            item_name="goldcoin",
        )
        self.assertTrue(result.success)
        self.assertIn("GoldCoin", result.message or "")

    def test_closed_container_fails(self) -> None:
        container = self._make_container(is_open=False)
        self._put_in_container(container, "GoldCoin")
        action = LookAtItemAction()
        result = action.run(
            self.actor,
            container_id=container.game_object.pk,
            item_name="goldcoin",
        )
        self.assertFalse(result.success)
        self.assertIn("closed", (result.message or "").lower())
