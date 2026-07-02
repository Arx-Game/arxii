"""Model-shape tests for the stakes-contract models (#1770 PR1)."""

from django.db import IntegrityError
from django.test import TestCase

from world.societies.constants import RenownRisk
from world.stories.constants import (
    StakeResolutionColumn,
    StakeSeverity,
    StakeSubjectKind,
)
from world.stories.factories import (
    BeatFactory,
    StakeFactory,
    StakeResolutionFactory,
    seed_default_risk_calibrations,
)
from world.stories.models import RiskCalibration, StakeContractActivation


class StakeModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.beat = BeatFactory(risk=RenownRisk.HIGH, target_level=4)
        cls.stake = StakeFactory(
            beat=cls.beat,
            subject_kind=StakeSubjectKind.CUSTOM,
            severity=StakeSeverity.GRAVE,
            subject_label="The town of Erenwold",
        )

    def test_stake_reverse_accessor(self):
        self.assertIn(self.stake, self.beat.stakes.all())

    def test_resolution_unique_per_column(self):
        StakeResolutionFactory(stake=self.stake, column=StakeResolutionColumn.LOSS)
        with self.assertRaises(IntegrityError):
            StakeResolutionFactory(stake=self.stake, column=StakeResolutionColumn.LOSS)


class RiskCalibrationTests(TestCase):
    def test_seed_defaults_creates_four_rows(self):
        seed_default_risk_calibrations()
        self.assertEqual(RiskCalibration.objects.count(), 4)
        extreme = RiskCalibration.objects.get(risk=RenownRisk.EXTREME)
        self.assertEqual(extreme.max_fuse_hops, 0)
        self.assertEqual(extreme.severity_ceiling, StakeSeverity.REMOVAL)


class ActivationConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.beat = BeatFactory(risk=RenownRisk.LOW, target_level=2)

    def test_only_one_open_activation_per_beat(self):
        StakeContractActivation.objects.create(
            beat=self.beat,
            party_average_level=2,
            declared_target_level=2,
            declared_risk=RenownRisk.LOW,
            effective_risk=RenownRisk.LOW,
            is_ready=True,
        )
        with self.assertRaises(IntegrityError):
            StakeContractActivation.objects.create(
                beat=self.beat,
                party_average_level=2,
                declared_target_level=2,
                declared_risk=RenownRisk.LOW,
                effective_risk=RenownRisk.LOW,
                is_ready=True,
            )
