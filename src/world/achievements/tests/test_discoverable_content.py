"""Tests for the DiscoverableContent abstract base."""

from django.test import TestCase

from world.achievements.models import Achievement, DiscoverableContent


class DiscoverableContentTest(TestCase):
    def test_discoverable_content_provides_nullable_achievement_fk(self):
        field = DiscoverableContent._meta.get_field("discovery_achievement")
        assert field.null is True
        assert field.remote_field.model is Achievement
