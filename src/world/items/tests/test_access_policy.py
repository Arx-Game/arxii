"""Container access policy + ownership gate tests on pick_up/take_out (#1909).

Covers the 7-case matrix from the task-3 brief: unowned/owned room items, and
container access policies (OPEN/FRIENDS/OWNER_ONLY) including the NPC-owner
edge case (no active RosterTenure).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.service_functions.inventory import pick_up, take_out
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.items.constants import ContainerAccessPolicy
from world.items.exceptions import ContainerAccessDenied, OwnedByAnother
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.models import RosterTenure
from world.scenes.models import Friendship


class ContainerAccessPolicyTests(TestCase):
    """The 7-case matrix for the ownership/policy gate (#1909)."""

    def setUp(self) -> None:
        # Evennia typeclass instances cannot live on setUpTestData (DbHolder
        # deepcopy issue) — same per-test setUp pattern as test_inventory_services.py.
        self.room = ObjectDBFactory(
            db_key="AccessPolicyRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.owner = CharacterFactory(db_key="AccessPolicyOwner", location=self.room)
        self.owner_sheet = CharacterSheetFactory(character=self.owner)
        self.actor = CharacterFactory(db_key="AccessPolicyActor", location=self.room)
        self.actor_sheet = CharacterSheetFactory(character=self.actor)

        self.actor_state = CharacterState(self.actor, context=MagicMock())
        self.owner_state = CharacterState(self.owner, context=MagicMock())

    # ------------------------------------------------------------------
    # Fixture builders
    # ------------------------------------------------------------------

    def _room_item(self, *, holder: CharacterSheet | None) -> ItemState:
        item_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        item_obj.location = self.room
        item_obj.save()
        instance = ItemInstanceFactory(game_object=item_obj, holder_character_sheet=holder)
        return ItemState(instance, context=MagicMock())

    def _container(
        self,
        *,
        owner_sheet: CharacterSheet,
        policy: str = ContainerAccessPolicy.OPEN,
    ) -> ItemInstance:
        template = ItemTemplateFactory(name="AccessPolicyBox", is_container=True)
        container_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        container_obj.location = self.room
        container_obj.save()
        return ItemInstanceFactory(
            template=template,
            game_object=container_obj,
            holder_character_sheet=owner_sheet,
            access_policy=policy,
        )

    def _item_in_container(
        self,
        container_instance: ItemInstance,
        *,
        holder: CharacterSheet | None,
    ) -> ItemState:
        item_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        item_obj.location = container_instance.game_object
        item_obj.save()
        instance = ItemInstanceFactory(
            game_object=item_obj,
            holder_character_sheet=holder,
            contained_in=container_instance,
        )
        return ItemState(instance, context=MagicMock())

    def _active_tenure(self, sheet: CharacterSheet) -> RosterTenure:
        return RosterTenureFactory(roster_entry=RosterEntryFactory(character_sheet=sheet))

    # ------------------------------------------------------------------
    # Case 1: unowned room item -> pick_up succeeds (legacy behavior).
    # ------------------------------------------------------------------

    def test_unowned_room_item_pick_up_succeeds(self) -> None:
        item_state = self._room_item(holder=None)
        pick_up(self.actor_state, item_state)
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.game_object.location, self.actor)

    # ------------------------------------------------------------------
    # Case 2: room item owned by actor -> succeeds.
    # ------------------------------------------------------------------

    def test_room_item_owned_by_actor_pick_up_succeeds(self) -> None:
        item_state = self._room_item(holder=self.actor_sheet)
        pick_up(self.actor_state, item_state)
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.game_object.location, self.actor)

    # ------------------------------------------------------------------
    # Case 3: room item owned by another sheet -> OwnedByAnother.
    # ------------------------------------------------------------------

    def test_room_item_owned_by_another_raises_owned_by_another(self) -> None:
        item_state = self._room_item(holder=self.owner_sheet)
        with self.assertRaises(OwnedByAnother):
            pick_up(self.actor_state, item_state)

    # ------------------------------------------------------------------
    # Case 4: OPEN container, item owned by container owner, stranger takes
    # -> succeeds (sanctioned borrowing); ownership persists.
    # ------------------------------------------------------------------

    def test_open_container_stranger_take_succeeds_ownership_persists(self) -> None:
        container = self._container(owner_sheet=self.owner_sheet, policy=ContainerAccessPolicy.OPEN)
        item_state = self._item_in_container(container, holder=self.owner_sheet)
        take_out(self.actor_state, item_state)
        item_state.instance.refresh_from_db()
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.holder_character_sheet, self.owner_sheet)
        self.assertEqual(item_state.instance.game_object.location, self.actor)

    # ------------------------------------------------------------------
    # Case 5: FRIENDS container -> friend succeeds, non-friend denied.
    # ------------------------------------------------------------------

    def test_friends_container_friend_taker_succeeds(self) -> None:
        owner_tenure = self._active_tenure(self.owner_sheet)
        actor_tenure = self._active_tenure(self.actor_sheet)
        Friendship.objects.create(friender_tenure=owner_tenure, friend_tenure=actor_tenure)
        Friendship.objects.create(friender_tenure=actor_tenure, friend_tenure=owner_tenure)

        container = self._container(
            owner_sheet=self.owner_sheet, policy=ContainerAccessPolicy.FRIENDS
        )
        item_state = self._item_in_container(container, holder=self.owner_sheet)
        take_out(self.actor_state, item_state)
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.game_object.location, self.actor)

    def test_friends_container_non_friend_raises_container_access_denied(self) -> None:
        self._active_tenure(self.owner_sheet)
        self._active_tenure(self.actor_sheet)

        container = self._container(
            owner_sheet=self.owner_sheet, policy=ContainerAccessPolicy.FRIENDS
        )
        item_state = self._item_in_container(container, holder=self.owner_sheet)
        with self.assertRaises(ContainerAccessDenied):
            take_out(self.actor_state, item_state)

    # ------------------------------------------------------------------
    # Case 6: OWNER_ONLY container -> non-owner denied, owner succeeds.
    # ------------------------------------------------------------------

    def test_owner_only_container_non_owner_raises_container_access_denied(self) -> None:
        container = self._container(
            owner_sheet=self.owner_sheet, policy=ContainerAccessPolicy.OWNER_ONLY
        )
        item_state = self._item_in_container(container, holder=self.owner_sheet)
        with self.assertRaises(ContainerAccessDenied):
            take_out(self.actor_state, item_state)

    def test_owner_only_container_owner_succeeds(self) -> None:
        container = self._container(
            owner_sheet=self.owner_sheet, policy=ContainerAccessPolicy.OWNER_ONLY
        )
        item_state = self._item_in_container(container, holder=self.owner_sheet)
        take_out(self.owner_state, item_state)
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.game_object.location, self.owner)

    # ------------------------------------------------------------------
    # Case 7: NPC-owned (owner sheet has no active tenure) — plain take
    # never bypasses ownership/policy just because the owner is an NPC.
    # ------------------------------------------------------------------

    def test_npc_owned_room_item_raises_owned_by_another(self) -> None:
        # self.owner_sheet has no RosterTenure at all in this test -> NPC.
        item_state = self._room_item(holder=self.owner_sheet)
        with self.assertRaises(OwnedByAnother):
            pick_up(self.actor_state, item_state)

    def test_npc_owned_friends_container_raises_container_access_denied(self) -> None:
        # Owner has no active tenure -> FRIENDS resolves to deny regardless of actor.
        container = self._container(
            owner_sheet=self.owner_sheet, policy=ContainerAccessPolicy.FRIENDS
        )
        item_state = self._item_in_container(container, holder=self.owner_sheet)
        with self.assertRaises(ContainerAccessDenied):
            take_out(self.actor_state, item_state)
