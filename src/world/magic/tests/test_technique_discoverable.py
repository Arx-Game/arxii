"""Tests that Technique inherits DiscoverableContent (nullable discovery_achievement)."""

from django.test import TestCase

from world.magic.factories import TechniqueFactory


class TechniqueDiscoverableTests(TestCase):
    """Technique must carry a nullable discovery_achievement FK from DiscoverableContent."""

    def test_technique_has_nullable_discovery_achievement(self):
        tech = TechniqueFactory()
        self.assertIsNone(tech.discovery_achievement)
