"""Seed tests for the worship content cluster (#2355)."""

from django.test import TestCase, override_settings

from world.achievements.models import Achievement
from world.checks.models import CheckType, CheckTypeAspect
from world.seeds.worship_content import (
    CEREMONY_CHECK_TYPE,
    seed_worship_content,
)
from world.skills.models import Skill, Specialization
from world.worship.models import WorshippedBeing, WorshipTradition


@override_settings(SEED_SAMPLE_CONTENT=True)  # seed_worship_content gates on #2698
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

    def test_seed_sets_the_favor_terms_and_being_targets(self) -> None:
        """#4333: the invocation check, the example bonuses, two targets per being."""
        from world.mechanics.models import ModifierTarget
        from world.worship.invocation_services import get_devotion_config
        from world.worship.models import FavorOutcomeAward

        seed_worship_content()
        seed_worship_content()

        config = get_devotion_config()
        self.assertEqual(config.invocation_check_type.name, CEREMONY_CHECK_TYPE)
        bonuses = dict(
            FavorOutcomeAward.objects.filter(kind="invocation").values_list(
                "outcome_tier__name", "amount"
            )
        )
        self.assertEqual(bonuses["Success"], 10)
        self.assertEqual(len(bonuses), 5)
        self.assertEqual(
            ModifierTarget.objects.filter(target_being__isnull=False).count(),
            2 * WorshippedBeing.objects.count(),
        )
