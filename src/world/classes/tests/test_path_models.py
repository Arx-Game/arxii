"""Tests for Path models."""

from django.test import TestCase

from world.classes.models import Aspect, Path, PathAspect, PathStage


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


class AspectModelTest(TestCase):
    """Tests for Aspect model."""

    def test_create_aspect(self):
        """Can create an aspect."""
        aspect = Aspect.objects.create(
            name="Warfare",
            description="Combat and martial prowess",
        )
        self.assertEqual(aspect.name, "Warfare")
        self.assertEqual(str(aspect), "Warfare")


class PathAspectModelTest(TestCase):
    """Tests for PathAspect model."""

    @classmethod
    def setUpTestData(cls):
        cls.steel_path = Path.objects.create(
            name="Path of Steel",
            description="Test",
            stage=PathStage.QUIESCENT,
            minimum_level=1,
        )
        cls.warfare = Aspect.objects.create(name="Warfare", description="Combat")
        cls.martial = Aspect.objects.create(name="Martial", description="Physical")

    def test_create_path_aspect(self):
        """Can link aspect to path with weight."""
        pa = PathAspect.objects.create(
            character_path=self.steel_path,
            aspect=self.warfare,
            weight=2,
        )
        self.assertEqual(pa.weight, 2)
        self.assertEqual(pa.character_path, self.steel_path)
        self.assertEqual(pa.aspect, self.warfare)

    def test_path_aspect_default_weight(self):
        """PathAspect defaults to weight 1."""
        pa = PathAspect.objects.create(
            character_path=self.steel_path,
            aspect=self.martial,
        )
        self.assertEqual(pa.weight, 1)

    def test_path_aspects_relationship(self):
        """Can access aspects through path."""
        PathAspect.objects.create(character_path=self.steel_path, aspect=self.warfare, weight=2)
        PathAspect.objects.create(character_path=self.steel_path, aspect=self.martial, weight=1)

        aspects = self.steel_path.path_aspects.all()
        self.assertEqual(aspects.count(), 2)
