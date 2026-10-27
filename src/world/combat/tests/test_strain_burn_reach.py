"""StrainBurnReach monotonic validation and the strain Required content probes (#4736)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.checks.factories import CheckTypeFactory
from world.combat.models import StrainBurnReach
from world.combat.services.encounter.config import get_strain_config
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.services import ensure_canonical_check_outcome


def _probe_for(key: str) -> rc.ContentProbe:
    return next(dep.probe for dep in rc._declarations() if dep.key == key)


class StrainBurnReachMonotonicTests(TestCase):
    """U-keep: staff authoring validation, no player path."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tiers = {
            name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS
        }
        ordered = sorted(cls.tiers.values(), key=lambda t: t.success_level)
        cls.worst, cls.middle, cls.best = ordered[0], ordered[2], ordered[-1]

    def test_better_tier_may_reach_more(self) -> None:
        StrainBurnReach.objects.create(outcome_tier=self.worst, reach_percent=0)
        StrainBurnReach.objects.create(outcome_tier=self.middle, reach_percent=50)
        row = StrainBurnReach.objects.create(outcome_tier=self.best, reach_percent=100)
        self.assertEqual(row.reach_percent, 100)

    def test_equal_reach_across_tiers_is_allowed(self) -> None:
        StrainBurnReach.objects.create(outcome_tier=self.worst, reach_percent=40)
        StrainBurnReach.objects.create(outcome_tier=self.best, reach_percent=40)

    def test_better_tier_reaching_less_is_refused(self) -> None:
        StrainBurnReach.objects.create(outcome_tier=self.middle, reach_percent=60)
        with self.assertRaises(ValidationError):
            StrainBurnReach.objects.create(outcome_tier=self.best, reach_percent=30)
        self.assertFalse(StrainBurnReach.objects.filter(outcome_tier=self.best).exists())

    def test_worse_tier_reaching_more_is_refused(self) -> None:
        StrainBurnReach.objects.create(outcome_tier=self.middle, reach_percent=60)
        with self.assertRaises(ValidationError):
            StrainBurnReach.objects.create(outcome_tier=self.worst, reach_percent=90)

    def test_editing_a_row_in_place_is_checked_against_the_others(self) -> None:
        StrainBurnReach.objects.create(outcome_tier=self.worst, reach_percent=10)
        row = StrainBurnReach.objects.create(outcome_tier=self.best, reach_percent=80)
        row.reach_percent = 5
        with self.assertRaises(ValidationError):
            row.save()
        row.reach_percent = 90
        row.save()


class StrainProbeTests(TestCase):
    def test_check_type_probe_follows_the_designation(self) -> None:
        probe = _probe_for("strain-check-type")
        config = get_strain_config()
        self.assertFalse(probe.resolve(None).present)
        config.strain_check_type = CheckTypeFactory()
        config.save()
        self.assertTrue(probe.resolve(None).present)

    def test_reach_probe_lists_each_uncovered_canonical_tier(self) -> None:
        probe = _probe_for("strain-burn-reach")
        tiers = {name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS}
        result = probe.resolve(None)
        self.assertFalse(result.present)
        self.assertEqual(set(result.missing), set(CANONICAL_OUTCOME_LEVELS))
        left_out = "Critical Success"
        for name, tier in tiers.items():
            if name != left_out:
                StrainBurnReach.objects.create(outcome_tier=tier, reach_percent=50)
        partial = probe.resolve(None)
        self.assertEqual(set(partial.missing), {left_out})
        StrainBurnReach.objects.create(outcome_tier=tiers[left_out], reach_percent=50)
        self.assertTrue(probe.resolve(None).present)
