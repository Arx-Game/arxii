"""Tests for Path models."""

from django.test import TestCase

from world.classes.models import Path, PathStage


class PathStageTest(TestCase):
    """Tests for PathStage enum."""

    def test_pathstage_values(self):
        """PathStage has correct values."""
        self.assertEqual(PathStage.QUIESCENT, 1)
        self.assertEqual(PathStage.POTENTIAL, 2)
        self.assertEqual(PathStage.PUISSANT, 3)
        self.assertEqual(PathStage.TRUE, 4)
        self.assertEqual(PathStage.GRAND, 5)
        self.assertEqual(PathStage.TRANSCENDENT, 6)

    def test_pathstage_labels(self):
        """PathStage has correct labels."""
        self.assertEqual(PathStage.QUIESCENT.label, "Quiescent")
        self.assertEqual(PathStage.PUISSANT.label, "Puissant")


class PathModelTest(TestCase):
    """Tests for Path model."""

    def test_create_path(self):
        """Can create a basic path."""
        path = Path.objects.create(
            name="Path of Steel",
            description="The martial path",
            stage=PathStage.QUIESCENT,
            minimum_level=1,
        )
        self.assertEqual(path.name, "Path of Steel")
        self.assertEqual(path.stage, PathStage.QUIESCENT)
        self.assertEqual(path.minimum_level, 1)
        self.assertTrue(path.is_active)

    def test_path_str(self):
        """Path string representation."""
        path = Path.objects.create(
            name="Path of Steel",
            description="Test",
            stage=PathStage.QUIESCENT,
            minimum_level=1,
        )
        self.assertIn("Path of Steel", str(path))

    def test_path_parent_relationship(self):
        """Paths can have parent paths."""
        steel = Path.objects.create(
            name="Path of Steel",
            description="Starting martial",
            stage=PathStage.QUIESCENT,
            minimum_level=1,
        )
        vanguard = Path.objects.create(
            name="Vanguard",
            description="Tank evolution",
            stage=PathStage.POTENTIAL,
            minimum_level=3,
        )
        vanguard.parent_paths.add(steel)

        self.assertIn(steel, vanguard.parent_paths.all())
        self.assertIn(vanguard, steel.child_paths.all())
