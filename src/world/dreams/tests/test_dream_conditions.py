"""Tests for dream-specific conditions and the Dream Peril pool (#2290)."""

from django.test import TestCase

from world.dreams.conditions import ensure_dream_conditions
from world.dreams.constants import MADNESS_CONDITION_NAME, NIGHTMARES_CONDITION_NAME
from world.vitals.constants import POOL_DREAM_PERIL
from world.vitals.factories import create_dream_peril_pool


class DreamPerilPoolTests(TestCase):
    """Tests for the Dream Peril consequence pool."""

    def test_pool_exists_with_four_outcomes(self):
        pool = create_dream_peril_pool()
        assert pool.name == POOL_DREAM_PERIL
        entries = pool.cached_consequences
        labels = {e.label for e in entries}
        assert "wake_shaken" in labels
        assert "nightmares" in labels
        assert "madness" in labels
        assert "die" in labels

    def test_die_outcome_is_character_loss(self):
        pool = create_dream_peril_pool()
        die_entry = next(e for e in pool.cached_consequences if e.label == "die")
        assert die_entry.character_loss is True

    def test_non_death_outcomes_are_not_character_loss(self):
        pool = create_dream_peril_pool()
        for entry in pool.cached_consequences:
            if entry.label != "die":
                assert entry.character_loss is False


class DreamConditionTests(TestCase):
    """Tests for the Nightmare and Madness condition templates."""

    def test_conditions_exist(self):
        ensure_dream_conditions()
        from world.conditions.models import ConditionTemplate

        assert ConditionTemplate.objects.filter(name=NIGHTMARES_CONDITION_NAME).exists()
        assert ConditionTemplate.objects.filter(name=MADNESS_CONDITION_NAME).exists()

    def test_madness_alters_behavior(self):
        ensure_dream_conditions()
        from world.conditions.models import ConditionTemplate

        madness = ConditionTemplate.objects.get(name=MADNESS_CONDITION_NAME)
        assert madness.category.alters_behavior is True

    def test_nightmares_does_not_alter_behavior(self):
        ensure_dream_conditions()
        from world.conditions.models import ConditionTemplate

        nightmares = ConditionTemplate.objects.get(name=NIGHTMARES_CONDITION_NAME)
        assert nightmares.category.alters_behavior is False
