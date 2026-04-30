"""Tests for inventory mutation service functions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.service_functions.inventory import pick_up
from world.items.exceptions import PermissionDenied
from world.items.factories import ItemInstanceFactory


class PickUpTests(TestCase):
    """Cover the four behaviors of ``pick_up``."""

    def setUp(self) -> None:
        # Evennia typeclass instances cannot live on ``setUpTestData`` because
        # Django's per-test deepcopy of class data fails on DbHolder objects.
        self.account = AccountFactory()
        self.room = ObjectDBFactory(
            db_key="PickUpTestRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.character = CharacterFactory(
            db_key="PickUpTestChar",
            location=self.room,
        )
        self.character.db_account = self.account
        self.character.save()

        # Build an ObjectDB for the item, place it in the room, then bind it
        # to a fresh ItemInstance.
        item_obj = ObjectDBFactory(
            db_key="PickUpTestItemObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item_obj.location = self.room
        item_obj.save()
        self.item = ItemInstanceFactory(game_object=item_obj)

        ctx = MagicMock()
        self.character_state = CharacterState(self.character, context=ctx)
        self.item_state = ItemState(self.item, context=ctx)

    def test_basic_pickup_moves_object_into_character(self) -> None:
        pick_up(self.character_state, self.item_state)
        self.item.game_object.refresh_from_db()
        self.assertEqual(self.item.game_object.location, self.character)

    def test_pickup_sets_owner_when_unowned(self) -> None:
        self.item.owner = None
        self.item.save()
        pick_up(self.character_state, self.item_state)
        self.item.refresh_from_db()
        self.assertEqual(self.item.owner, self.account)

    def test_pickup_does_not_overwrite_existing_owner(self) -> None:
        other_account = AccountFactory(username="other_owner")
        self.item.owner = other_account
        self.item.save()
        pick_up(self.character_state, self.item_state)
        self.item.refresh_from_db()
        self.assertEqual(self.item.owner, other_account)

    def test_pickup_denied_by_can_take_raises(self) -> None:
        with patch.object(ItemState, "can_take", return_value=False):
            with self.assertRaises(PermissionDenied):
                pick_up(self.character_state, self.item_state)
