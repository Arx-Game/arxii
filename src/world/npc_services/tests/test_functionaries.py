"""Tests for the Functionary room-placement layer (#1766)."""

from __future__ import annotations

import django.test

from evennia_extensions.factories import RoomProfileFactory
from world.npc_services.factories import FunctionaryFactory, NPCRoleFactory
from world.npc_services.functionaries import (
    functionaries_in_location,
    functionaries_in_room,
    functionary_in_location,
    functionary_in_room,
    place_functionary,
    remove_functionary,
)
from world.npc_services.models import Functionary


class FunctionaryModelTests(django.test.TestCase):
    def test_display_name_prefers_override(self) -> None:
        role = NPCRoleFactory(name="Barkeep")
        plain = FunctionaryFactory(role=role, name_override="")
        named = FunctionaryFactory(role=role, name_override="Old Marta")
        self.assertEqual(plain.display_name, "Barkeep")
        self.assertEqual(named.display_name, "Old Marta")

    def test_unique_role_room(self) -> None:
        from django.db import IntegrityError

        room = RoomProfileFactory()
        role = NPCRoleFactory()
        FunctionaryFactory(role=role, room=room)
        with self.assertRaises(IntegrityError):
            Functionary.objects.create(role=role, room=room)


class FunctionariesInRoomTests(django.test.TestCase):
    def setUp(self) -> None:
        self.room = RoomProfileFactory()
        self.role = NPCRoleFactory(name="Guild Clerk")

    def test_lists_active_only(self) -> None:
        present = FunctionaryFactory(role=self.role, room=self.room, is_active=True)
        FunctionaryFactory(role=NPCRoleFactory(name="Gone"), room=self.room, is_active=False)
        results = list(functionaries_in_room(self.room))
        self.assertEqual(results, [present])

    def test_excludes_inactive_role(self) -> None:
        FunctionaryFactory(role=NPCRoleFactory(name="Retired", is_active=False), room=self.room)
        self.assertEqual(list(functionaries_in_room(self.room)), [])


class FunctionaryInRoomResolutionTests(django.test.TestCase):
    def setUp(self) -> None:
        self.room = RoomProfileFactory()
        self.clerk = FunctionaryFactory(
            role=NPCRoleFactory(name="Builders Guild Clerk"), room=self.room
        )
        self.marta = FunctionaryFactory(
            role=NPCRoleFactory(name="Barkeep"), room=self.room, name_override="Old Marta"
        )

    def test_resolves_by_id(self) -> None:
        self.assertEqual(functionary_in_room(self.room, str(self.clerk.pk)), self.clerk)

    def test_resolves_by_role_name(self) -> None:
        self.assertEqual(functionary_in_room(self.room, "builders guild clerk"), self.clerk)

    def test_resolves_by_placement_name_override(self) -> None:
        self.assertEqual(functionary_in_room(self.room, "old marta"), self.marta)

    def test_resolves_unique_partial(self) -> None:
        self.assertEqual(functionary_in_room(self.room, "marta"), self.marta)

    def test_ambiguous_partial_returns_none(self) -> None:
        # Two functionaries whose names share a substring → ambiguous → None.
        FunctionaryFactory(role=NPCRoleFactory(name="Guild Steward"), room=self.room)
        self.assertIsNone(functionary_in_room(self.room, "guild"))

    def test_not_present_returns_none(self) -> None:
        other_room = RoomProfileFactory()
        self.assertIsNone(functionary_in_room(other_room, "Barkeep"))


class PlaceRemoveFunctionaryTests(django.test.TestCase):
    def setUp(self) -> None:
        self.room = RoomProfileFactory()
        self.role = NPCRoleFactory(name="Town Guard")

    def test_place_is_idempotent_and_updates(self) -> None:
        first = place_functionary(role=self.role, room=self.room, name_override="Sergeant Vale")
        second = place_functionary(role=self.role, room=self.room, name_override="Captain Vale")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.name_override, "Captain Vale")
        self.assertEqual(Functionary.objects.filter(role=self.role, room=self.room).count(), 1)

    def test_place_reactivates(self) -> None:
        FunctionaryFactory(role=self.role, room=self.room, is_active=False)
        placed = place_functionary(role=self.role, room=self.room)
        self.assertTrue(placed.is_active)

    def test_remove_soft_deactivates(self) -> None:
        FunctionaryFactory(role=self.role, room=self.room, is_active=True)
        self.assertTrue(remove_functionary(role=self.role, room=self.room))
        self.assertFalse(functionaries_in_room(self.room).exists())
        # Row survives (soft-remove), just inactive.
        self.assertEqual(Functionary.objects.filter(role=self.role, room=self.room).count(), 1)

    def test_remove_absent_returns_false(self) -> None:
        self.assertFalse(remove_functionary(role=self.role, room=self.room))


class FunctionaryLocationTests(django.test.TestCase):
    def test_resolves_via_room_objectdb(self) -> None:
        profile = RoomProfileFactory()
        room_obj = profile.objectdb
        func = FunctionaryFactory(role=NPCRoleFactory(name="Ferryman"), room=profile)
        self.assertEqual(list(functionaries_in_location(room_obj)), [func])
        self.assertEqual(functionary_in_location(room_obj, "Ferryman"), func)

    def test_none_location_is_empty(self) -> None:
        self.assertEqual(list(functionaries_in_location(None)), [])
        self.assertIsNone(functionary_in_location(None, "anyone"))

    def test_non_objectdb_location_is_empty(self) -> None:
        # A non-placed / mock location must not hit the DB — it yields nothing.
        self.assertEqual(list(functionaries_in_location(object())), [])
        self.assertIsNone(functionary_in_location(object(), "anyone"))
