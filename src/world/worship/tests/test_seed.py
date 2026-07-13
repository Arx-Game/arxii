"""Seed tests for the worship content cluster (#2355)."""

from django.test import TestCase

from world.achievements.models import Achievement
from world.checks.models import CheckType, CheckTypeAspect
from world.seeds.worship_content import (
    CEREMONY_CHECK_TYPE,
    seed_worship_content,
)
from world.skills.models import Skill, Specialization
from world.worship.models import WorshippedBeing, WorshipTradition


class WorshipSeedTests(TestCase):
    def test_seed_creates_expected_rows_and_is_idempotent(self) -> None:
        seed_worship_content()
        first_counts = (
            Skill.objects.filter(trait__name="Rites").count(),
            Specialization.objects.filter(parent_skill__trait__name="Rites").count(),
            CheckType.objects.filter(name=CEREMONY_CHECK_TYPE).count(),
            Achievement.objects.filter(name__startswith="God's Favorite").count(),
            WorshipTradition.objects.count(),
            WorshippedBeing.objects.count(),
        )
        self.assertEqual(first_counts, (1, 4, 1, 3, 4, 5))
        check_type = CheckType.objects.get(name=CEREMONY_CHECK_TYPE)
        self.assertEqual(
            CheckTypeAspect.objects.filter(check_type=check_type, aspect__name="Devotion").count(),
            1,
        )

        seed_worship_content()
        second_counts = (
            Skill.objects.filter(trait__name="Rites").count(),
            Specialization.objects.filter(parent_skill__trait__name="Rites").count(),
            CheckType.objects.filter(name=CEREMONY_CHECK_TYPE).count(),
            Achievement.objects.filter(name__startswith="God's Favorite").count(),
            WorshipTradition.objects.count(),
            WorshippedBeing.objects.count(),
        )
        self.assertEqual(second_counts, first_counts)

    def test_every_tradition_specialization_is_under_rites(self) -> None:
        seed_worship_content()
        for tradition in WorshipTradition.objects.all():
            self.assertEqual(tradition.rites_specialization.parent_skill.trait.name, "Rites")
