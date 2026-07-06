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
from flows.service_functions.inventory import pick_up, steal, steal_permitted, take_out
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.consent.constants import ConsentMode
from world.consent.services import (
    add_social_consent_whitelist,
    set_social_consent_category_rule,
    set_social_consent_preference,
    theft_category,
)
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
        owner_sheet: CharacterSheet | None,
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

    # ------------------------------------------------------------------
    # Unowned container: no owner -> policy cannot bar anyone, even OWNER_ONLY.
    # ------------------------------------------------------------------

    def test_unowned_owner_only_container_is_still_takeable_from(self) -> None:
        container = self._container(owner_sheet=None, policy=ContainerAccessPolicy.OWNER_ONLY)
        item_state = self._item_in_container(container, holder=None)
        take_out(self.actor_state, item_state)
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.game_object.location, self.actor)

    # ------------------------------------------------------------------
    # Sheet-less actor (GM/staff/companion tooling): the gate must not crash
    # on a character with no CharacterSheet — legacy free-take applies, since
    # theft consequence machinery is sheet-anchored (#1909 review fix).
    # ------------------------------------------------------------------

    def test_sheetless_actor_pick_up_of_owned_item_does_not_raise(self) -> None:
        sheetless = CharacterFactory(db_key="AccessPolicySheetless", location=self.room)
        sheetless_state = CharacterState(sheetless, context=MagicMock())
        item_state = self._room_item(holder=self.owner_sheet)
        pick_up(sheetless_state, item_state)
        item_state.instance.refresh_from_db()
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.game_object.location, sheetless)
        # Ownership is preserved — pick_up never reassigns an owned item.
        self.assertEqual(item_state.instance.holder_character_sheet, self.owner_sheet)

        # Unowned item: pick_up succeeds and holder stays None — a sheet-less
        # actor can't own things, so the owner assignment is skipped entirely.
        unowned_state = self._room_item(holder=None)
        pick_up(sheetless_state, unowned_state)
        unowned_state.instance.refresh_from_db()
        unowned_state.instance.game_object.refresh_from_db()
        self.assertEqual(unowned_state.instance.game_object.location, sheetless)
        self.assertIsNone(unowned_state.instance.holder_character_sheet)

    def test_sheetless_actor_take_out_from_owner_only_container_does_not_raise(self) -> None:
        sheetless = CharacterFactory(db_key="AccessPolicySheetless2", location=self.room)
        sheetless_state = CharacterState(sheetless, context=MagicMock())
        container = self._container(
            owner_sheet=self.owner_sheet, policy=ContainerAccessPolicy.OWNER_ONLY
        )
        item_state = self._item_in_container(container, holder=self.owner_sheet)
        take_out(sheetless_state, item_state)
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.game_object.location, sheetless)

    # ------------------------------------------------------------------
    # Third-party stash (#1909 branch review): an item owned by neither the
    # taker nor the container's owner is not the container owner's to lend —
    # a passing policy sanctions borrowing only the container OWNER's items.
    # ------------------------------------------------------------------

    def _third_sheet(self) -> CharacterSheet:
        third_char = CharacterFactory(db_key="AccessPolicyThird", location=self.room)
        return CharacterSheetFactory(character=third_char)

    def _allow_theft(self, owner_tenure: RosterTenure, actor_tenure: RosterTenure) -> None:
        preference = set_social_consent_preference(owner_tenure, allow_social_actions=True)
        set_social_consent_category_rule(preference, theft_category(), ConsentMode.ALLOWLIST)
        add_social_consent_whitelist(owner_tenure, actor_tenure, theft_category())

    def test_third_party_item_in_open_container_raises_owned_by_another(self) -> None:
        third_sheet = self._third_sheet()
        container = self._container(owner_sheet=self.owner_sheet, policy=ContainerAccessPolicy.OPEN)
        item_state = self._item_in_container(container, holder=third_sheet)
        with self.assertRaises(OwnedByAnother):
            take_out(self.actor_state, item_state)

    def test_owned_item_in_unowned_container_raises_owned_by_another(self) -> None:
        container = self._container(owner_sheet=None, policy=ContainerAccessPolicy.OPEN)
        item_state = self._item_in_container(container, holder=self.owner_sheet)
        with self.assertRaises(OwnedByAnother):
            take_out(self.actor_state, item_state)

    def test_third_party_stash_steal_gated_by_item_owner_consent(self) -> None:
        """Steal of a third-party stash consults the ITEM owner's consent, not the container's."""
        third_sheet = self._third_sheet()
        third_tenure = self._active_tenure(third_sheet)
        actor_tenure = self._active_tenure(self.actor_sheet)
        self._active_tenure(self.owner_sheet)  # container owner: theft default-deny, no rule
        self._allow_theft(third_tenure, actor_tenure)

        container = self._container(owner_sheet=self.owner_sheet, policy=ContainerAccessPolicy.OPEN)
        item_state = self._item_in_container(container, holder=third_sheet)

        self.assertTrue(steal_permitted(self.actor_sheet, item_state.instance))
        steal(self.actor_state, item_state)
        item_state.instance.refresh_from_db()
        item_state.instance.game_object.refresh_from_db()
        self.assertEqual(item_state.instance.holder_character_sheet, self.actor_sheet)
        self.assertEqual(item_state.instance.game_object.location, self.actor)

    def test_third_party_stash_steal_blocked_when_item_owner_denies(self) -> None:
        """Container owner's consent cannot green-light stealing someone ELSE's item."""
        third_sheet = self._third_sheet()
        self._active_tenure(third_sheet)  # item owner: theft default-deny, no rule
        actor_tenure = self._active_tenure(self.actor_sheet)
        owner_tenure = self._active_tenure(self.owner_sheet)
        self._allow_theft(owner_tenure, actor_tenure)  # container owner consents — irrelevant

        container = self._container(owner_sheet=self.owner_sheet, policy=ContainerAccessPolicy.OPEN)
        item_state = self._item_in_container(container, holder=third_sheet)

        self.assertFalse(steal_permitted(self.actor_sheet, item_state.instance))
