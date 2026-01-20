from django.db import IntegrityError
from django.test import TestCase

from world.magic.models import Affinity
from world.magic.types import AffinityType


class AffinityModelTests(TestCase):
    """Tests for the Affinity model."""

    @classmethod
    def setUpTestData(cls):
        cls.celestial = Affinity.objects.create(
            affinity_type=AffinityType.CELESTIAL,
            name="Celestial",
            description="Magic of divine ideals and impossible virtue.",
            admin_notes="High control, never backfires, demands paragon lifestyle.",
        )

    def test_affinity_str(self):
        """Test string representation."""
        self.assertEqual(str(self.celestial), "Celestial")

    def test_affinity_natural_key(self):
        """Test natural key lookup."""
        self.assertEqual(
            Affinity.objects.get_by_natural_key("celestial"),
            self.celestial,
        )

    def test_affinity_unique_type(self):
        """Test that affinity_type is unique."""
        with self.assertRaises(IntegrityError):
            Affinity.objects.create(
                affinity_type=AffinityType.CELESTIAL,
                name="Duplicate Celestial",
                description="Should fail.",
            )
