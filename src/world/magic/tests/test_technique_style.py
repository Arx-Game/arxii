"""Tests for TechniqueStyle and its Path-side ownership (#2700)."""

from django.test import TestCase

from world.classes.factories import PathFactory
from world.magic.factories import StyleCapabilityRequirementFactory, TechniqueStyleFactory
from world.magic.models import StyleCapabilityRequirement, TechniqueStyle


class TechniqueStyleModelTests(TestCase):
    """Tests for the TechniqueStyle model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods."""
        cls.style = TechniqueStyle.objects.create(
            name="Test Manifestation",
            description="Powers that create visible magical effects.",
        )
        cls.path_steel = PathFactory(name="Path of Steel", style=cls.style)
        cls.path_shadow = PathFactory(name="Path of Shadow", style=cls.style)

    def test_technique_style_str(self):
        """Test string representation."""
        self.assertEqual(str(self.style), "Test Manifestation")

    def test_technique_style_natural_key(self):
        """Test natural_key() returns the name."""
        self.assertEqual(self.style.natural_key(), ("Test Manifestation",))

    def test_technique_style_get_by_natural_key(self):
        """Test get_by_natural_key() lookup."""
        retrieved = TechniqueStyle.objects.get_by_natural_key("Test Manifestation")
        self.assertEqual(retrieved, self.style)

    def test_technique_style_name_unique(self):
        """Test that name is unique."""
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            TechniqueStyle.objects.create(name="Test Manifestation")

    def test_many_paths_share_one_style(self):
        """Style is caster-scoped and many-to-one: several paths may share it (#2700).

        This is the cardinality that rules out putting the FK on TechniqueStyle —
        higher-stage paths inherit their line's style.
        """
        self.assertCountEqual(
            [p.name for p in self.style.paths.all()],
            ["Path of Steel", "Path of Shadow"],
        )

    def test_path_without_style_is_allowed(self):
        """A path may impose no style — pathless/NPC casters are unrestricted."""
        wanderer = PathFactory(name="The Wanderer")
        self.assertIsNone(wanderer.style_id)


class StyleCapabilityRequirementTests(TestCase):
    """Tests for the caster-scoped style casting requirements (#2700)."""

    @classmethod
    def setUpTestData(cls):
        cls.style = TechniqueStyleFactory(name="Incantation")
        cls.requirement = StyleCapabilityRequirementFactory(style=cls.style, minimum_value=2)

    def test_str(self):
        self.assertEqual(
            str(self.requirement),
            f"Incantation requires {self.requirement.capability.name} >= 2",
        )

    def test_natural_key_roundtrip(self):
        """Natural key is (style, capability) so the row is authorable content."""
        key = self.requirement.natural_key()
        retrieved = StyleCapabilityRequirement.objects.get_by_natural_key(*key)
        self.assertEqual(retrieved, self.requirement)

    def test_unique_per_style_and_capability(self):
        """A style may not carry two requirements for the same capability."""
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            StyleCapabilityRequirement.objects.create(
                style=self.style,
                capability=self.requirement.capability,
                minimum_value=5,
            )

    def test_cached_capability_requirements(self):
        """The cached accessor is what technique_performable reads."""
        self.assertEqual(list(self.style.cached_capability_requirements), [self.requirement])


class TechniqueStyleFactoryTests(TestCase):
    """Tests for the TechniqueStyleFactory."""

    def test_factory_creates_technique_style(self):
        """Test that factory creates a valid TechniqueStyle."""
        style = TechniqueStyleFactory()
        self.assertIsInstance(style, TechniqueStyle)
        self.assertTrue(style.name)

    def test_factory_get_or_create_on_name(self):
        """Test factory uses get_or_create on name."""
        style1 = TechniqueStyleFactory(name="Subtle")
        style2 = TechniqueStyleFactory(name="Subtle")
        self.assertEqual(style1.pk, style2.pk)
