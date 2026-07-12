"""Tests for the #2177 defense models (bars/ward/alarm)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from evennia_extensions.models import ExitProfile
from world.room_features.constants import (
    EXIT_BARS_MAX_LEVEL,
    ROOM_ALARM_MAX_LEVEL,
    ROOM_WARD_MAX_LEVEL,
    DefenseKind,
)
from world.room_features.models import ExitBarsDetails, RoomAlarmDetails, RoomWardDetails


class ExitBarsDetailsTests(TestCase):
    def test_one_bars_row_per_exit_independent_of_room_features(self):
        room = ObjectDBFactory(db_key="BarsRoom", db_typeclass_path="typeclasses.rooms.Room")
        dest = ObjectDBFactory(db_key="BarsDest", db_typeclass_path="typeclasses.rooms.Room")
        exit_obj = ObjectDBFactory(db_key="north", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = dest
        exit_obj.save()
        exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        bars = ExitBarsDetails.objects.create(exit_profile=exit_profile, level=2)
        assert bars.level == 2
        assert ExitBarsDetails.objects.filter(exit_profile=exit_profile).active().count() == 1

    def test_dissolved_bars_excluded_from_active(self):
        from django.utils import timezone

        room = ObjectDBFactory(db_key="BarsRoom2", db_typeclass_path="typeclasses.rooms.Room")
        dest = ObjectDBFactory(db_key="BarsDest2", db_typeclass_path="typeclasses.rooms.Room")
        exit_obj = ObjectDBFactory(db_key="south", db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = room
        exit_obj.destination = dest
        exit_obj.save()
        exit_profile = ExitProfile.get_or_create_for_exit(exit_obj)
        bars = ExitBarsDetails.objects.create(
            exit_profile=exit_profile, dissolved_at=timezone.now()
        )
        assert not ExitBarsDetails.objects.filter(exit_profile=exit_profile).active().exists()
        assert ExitBarsDetails.objects.filter(pk=bars.pk).exists()


class RoomWardAlarmCoexistenceTests(TestCase):
    def test_ward_and_alarm_and_room_feature_coexist(self):
        from world.room_features.constants import RoomFeatureServiceStrategy
        from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory

        room_profile = RoomProfileFactory()
        kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.LAB)
        RoomFeatureInstanceFactory(room_profile=room_profile, feature_kind=kind)

        from world.magic.factories import ResonanceFactory

        resonance = ResonanceFactory()
        ward = RoomWardDetails.objects.create(room_profile=room_profile, resonance=resonance)
        alarm = RoomAlarmDetails.objects.create(room_profile=room_profile)

        assert ward.room_profile_id == room_profile.pk
        assert alarm.room_profile_id == room_profile.pk
        # RoomFeatureInstance still active -- the three models don't collide.
        assert room_profile.feature_instance.feature_kind_id == kind.pk


class DefenseConstantsTests(TestCase):
    def test_max_levels_are_five(self):
        assert EXIT_BARS_MAX_LEVEL == 5
        assert ROOM_WARD_MAX_LEVEL == 5
        assert ROOM_ALARM_MAX_LEVEL == 5

    def test_defense_kind_choices(self):
        assert set(DefenseKind.values) == {"EXIT_BARS", "ROOM_WARD", "ROOM_ALARM"}
