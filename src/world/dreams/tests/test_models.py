"""Tests for the DreamReflection model."""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.dreams.models import DreamReflection


class DreamReflectionTests(TestCase):
    """Tests for DreamReflection model creation and lookup."""

    def setUp(self):
        self.waking_room = ObjectDB.objects.create(db_key="Waking Room")
        self.dream_room = ObjectDB.objects.create(db_key="Dream Room")

    def test_create_reflection(self):
        reflection = DreamReflection.objects.create(
            waking_room=self.waking_room,
            dream_room=self.dream_room,
        )
        assert reflection.waking_room == self.waking_room
        assert reflection.dream_room == self.dream_room
        assert reflection.is_active is True
        assert reflection.descent_target is None

    def test_for_waking_room_returns_reflection(self):
        DreamReflection.objects.create(
            waking_room=self.waking_room,
            dream_room=self.dream_room,
        )
        result = DreamReflection.objects.for_waking_room(self.waking_room)
        assert result is not None
        assert result.dream_room == self.dream_room

    def test_for_waking_room_returns_none_when_absent(self):
        other_room = ObjectDB.objects.create(db_key="Other Room")
        assert DreamReflection.objects.for_waking_room(other_room) is None

    def test_for_waking_room_excludes_inactive(self):
        DreamReflection.objects.create(
            waking_room=self.waking_room,
            dream_room=self.dream_room,
            is_active=False,
        )
        assert DreamReflection.objects.for_waking_room(self.waking_room) is None

    def test_descent_target_optional(self):
        deep_room = ObjectDB.objects.create(db_key="Deep Dreaming")
        reflection = DreamReflection.objects.create(
            waking_room=self.waking_room,
            dream_room=self.dream_room,
            descent_target=deep_room,
        )
        assert reflection.descent_target == deep_room
