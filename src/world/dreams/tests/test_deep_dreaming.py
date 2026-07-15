"""Tests for deep dreaming area and dream seeds (#2290)."""

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.dreams.seeds import ensure_deep_dreaming_area, ensure_dream_content


class DeepDreamingAreaTests(TestCase):
    """Tests for the deep dreaming area seed."""

    def test_area_exists_at_plane_level(self):
        area = ensure_deep_dreaming_area()
        assert area.level == AreaLevel.PLANE

    def test_starter_room_exists(self):
        from evennia.objects.models import ObjectDB

        ensure_deep_dreaming_area()
        from world.dreams.constants import DEEP_DREAMING_STARTER_ROOM_KEY

        room = ObjectDB.objects.filter(db_key=DEEP_DREAMING_STARTER_ROOM_KEY).first()
        assert room is not None

    def test_starter_room_has_room_profile(self):
        from evennia_extensions.models import RoomProfile

        ensure_deep_dreaming_area()
        from evennia.objects.models import ObjectDB

        from world.dreams.constants import DEEP_DREAMING_STARTER_ROOM_KEY

        room = ObjectDB.objects.filter(db_key=DEEP_DREAMING_STARTER_ROOM_KEY).first()
        assert room is not None
        profile = RoomProfile.objects.filter(objectdb=room).first()
        assert profile is not None
        assert profile.area is not None


class DreamDamageTypeTests(TestCase):
    """Tests for dream damage types."""

    def test_damage_types_exist(self):
        ensure_dream_content()
        from world.conditions.models import DamageType

        for name in ("Nightmare", "Dread", "Confusion"):
            assert DamageType.objects.filter(name=name).exists(), f"{name} not found"
