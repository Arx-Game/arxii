"""Tests for Technique.reach field and TechniqueReach enum."""

from django.test import TestCase

from world.magic.constants import TechniqueReach
from world.magic.factories import TechniqueFactory
from world.magic.models import Technique


class TechniqueReachEnumTest(TestCase):
    """Tests for the TechniqueReach TextChoices enum."""

    def test_values_set(self):
        """TechniqueReach must expose exactly the four expected values."""
        self.assertEqual(
            set(TechniqueReach.values),
            {"same", "adjacent", "any", "reach_n"},
        )


class TechniqueReachFieldTest(TestCase):
    """Tests for the Technique.reach model field."""

    def setUp(self):
        Technique.flush_instance_cache()

    def test_factory_default_reach_is_any(self):
        """A Technique created via TechniqueFactory defaults reach to ANY."""
        technique = TechniqueFactory()
        self.assertEqual(technique.reach, TechniqueReach.ANY)

    def test_reach_persists_to_db(self):
        """reach value round-trips through the database correctly."""
        technique = TechniqueFactory(reach=TechniqueReach.SAME)
        Technique.flush_instance_cache()
        reloaded = Technique.objects.get(pk=technique.pk)
        self.assertEqual(reloaded.reach, TechniqueReach.SAME)

    def test_all_reach_values_accepted(self):
        """All four reach choices can be stored without error."""
        for value in TechniqueReach.values:
            t = TechniqueFactory(reach=value)
            Technique.flush_instance_cache()
            reloaded = Technique.objects.get(pk=t.pk)
            self.assertEqual(reloaded.reach, value)


class TechniqueReachHopsFieldTest(TestCase):
    """Tests for the Technique.reach_hops model field."""

    def setUp(self):
        Technique.flush_instance_cache()

    def test_factory_default_reach_hops_is_1(self):
        """A Technique created via TechniqueFactory defaults reach_hops to 1."""
        technique = TechniqueFactory()
        self.assertEqual(technique.reach_hops, 1)

    def test_reach_hops_persists_to_db(self):
        """reach_hops value round-trips through the database."""
        technique = TechniqueFactory(reach=TechniqueReach.REACH_N, reach_hops=3)
        Technique.flush_instance_cache()
        reloaded = Technique.objects.get(pk=technique.pk)
        self.assertEqual(reloaded.reach_hops, 3)

    def test_clean_raises_for_reach_n_with_zero_hops(self):
        """clean() raises when reach=REACH_N and reach_hops < 1."""
        from django.core.exceptions import ValidationError

        technique = TechniqueFactory.build(reach=TechniqueReach.REACH_N, reach_hops=0)
        with self.assertRaises(ValidationError):
            technique.clean()

    def test_clean_passes_for_any_with_zero_hops(self):
        """clean() does not raise when reach=ANY and reach_hops=0 (ignored)."""
        technique = TechniqueFactory.build(reach=TechniqueReach.ANY, reach_hops=0)
        technique.clean()  # should not raise
