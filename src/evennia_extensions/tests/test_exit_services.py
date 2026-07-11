"""Tests for exit service helpers (#2175)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.constants import ExitKind, RoomEnclosure
from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import ExitProfile, RoomProfile
from evennia_extensions.services.exits import (
    effective_enclosure_for_room,
    is_window,
    set_window_open,
)


class ExitServiceTests(TestCase):
    def test_is_window_true_for_window(self):
        exit_obj = ObjectDBFactory(db_key="win", db_typeclass_path="typeclasses.exits.Exit")
        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        profile.exit_kind = ExitKind.WINDOW
        profile.save()
        assert is_window(exit_obj) is True

    def test_is_window_false_for_door(self):
        exit_obj = ObjectDBFactory(db_key="door", db_typeclass_path="typeclasses.exits.Exit")
        assert is_window(exit_obj) is False

    def test_set_window_open(self):
        exit_obj = ObjectDBFactory(db_key="win", db_typeclass_path="typeclasses.exits.Exit")
        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        profile.exit_kind = ExitKind.WINDOW
        profile.save()
        set_window_open(exit_obj, True)
        profile.refresh_from_db()
        assert profile.is_open is True

    def test_set_window_open_noop_for_door(self):
        exit_obj = ObjectDBFactory(db_key="door", db_typeclass_path="typeclasses.exits.Exit")
        set_window_open(exit_obj, True)
        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        assert profile.is_open is False

    def test_effective_enclosure_walled_room_open_window_becomes_roofed(self):
        room = ObjectDBFactory(db_key="room", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.get_or_create(
            objectdb=room, defaults={"enclosure": RoomEnclosure.WALLED}
        )
        exit_obj = ObjectDBFactory(
            db_key="window", db_typeclass_path="typeclasses.exits.Exit", location=room
        )
        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        profile.exit_kind = ExitKind.WINDOW
        profile.is_open = True
        profile.save()
        assert effective_enclosure_for_room(room) == RoomEnclosure.ROOFED

    def test_effective_enclosure_unchanged_when_window_closed(self):
        room = ObjectDBFactory(db_key="room", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfile.objects.get_or_create(
            objectdb=room, defaults={"enclosure": RoomEnclosure.WALLED}
        )
        exit_obj = ObjectDBFactory(
            db_key="window", db_typeclass_path="typeclasses.exits.Exit", location=room
        )
        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        profile.exit_kind = ExitKind.WINDOW
        profile.is_open = False
        profile.save()
        assert effective_enclosure_for_room(room) == RoomEnclosure.WALLED

    def test_effective_enclosure_sealed_stays_sealed_with_open_window(self):
        room = ObjectDBFactory(db_key="room", db_typeclass_path="typeclasses.rooms.Room")
        room_profile = room.room_profile
        room_profile.enclosure = RoomEnclosure.SEALED
        room_profile.save()
        exit_obj = ObjectDBFactory(
            db_key="window", db_typeclass_path="typeclasses.exits.Exit", location=room
        )
        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        profile.exit_kind = ExitKind.WINDOW
        profile.is_open = True
        profile.save()
        assert effective_enclosure_for_room(room) == RoomEnclosure.SEALED
