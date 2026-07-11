"""Model-shape tests for the stakes-contract models (#1770 PR1)."""

from django.db import IntegrityError, transaction
from django.test import TestCase
from evennia.utils.test_resources import EvenniaTestCase

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
from world.stories.services.stake_resolution import stake_resolution_payload_problems


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


class StakeResolutionOutcomeKeyTests(EvenniaTestCase):
    """Open branch vocabulary (#1760): multiple named branches per column."""

    def test_two_loss_branches_with_different_outcome_keys_coexist(self) -> None:
        stake = StakeFactory()
        StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, outcome_key="destroyed"
        )
        StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, outcome_key="captured"
        )
        self.assertEqual(stake.resolutions.count(), 2)

    def test_duplicate_column_and_outcome_key_rejected(self) -> None:
        stake = StakeFactory()
        StakeResolutionFactory(
            stake=stake, column=StakeResolutionColumn.LOSS, outcome_key="destroyed"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StakeResolutionFactory(
                    stake=stake, column=StakeResolutionColumn.LOSS, outcome_key="destroyed"
                )

    def test_outcome_key_defaults_to_blank(self) -> None:
        resolution = StakeResolutionFactory()
        self.assertEqual(resolution.outcome_key, "")


class NpcRegardDeltaValidationTests(TestCase):
    """StakeResolution.npc_regard_delta is NPC_FATE-only (#2039)."""

    def _problems_for(self, stake, npc_regard_delta):
        resolution = StakeResolutionFactory.build(stake=stake, npc_regard_delta=npc_regard_delta)
        return stake_resolution_payload_problems(
            stake=resolution.stake,
            forfeits_subject_item=resolution.forfeits_subject_item,
            subject_standing_delta=resolution.subject_standing_delta,
            sets_subject_lifecycle=resolution.sets_subject_lifecycle,
            machine_match_lifecycle_state=resolution.machine_match_lifecycle_state,
            npc_regard_delta=resolution.npc_regard_delta,
        )

    def test_npc_regard_delta_requires_npc_fate_subject(self):
        stake = StakeFactory(subject_kind=StakeSubjectKind.FACTION)
        problems = self._problems_for(stake, npc_regard_delta=10)
        self.assertTrue(any(p.field == "npc_regard_delta" for p in problems))

    def test_npc_regard_delta_allowed_on_npc_fate_subject(self):
        stake = StakeFactory(subject_kind=StakeSubjectKind.NPC_FATE)
        problems = self._problems_for(stake, npc_regard_delta=10)
        self.assertFalse(any(p.field == "npc_regard_delta" for p in problems))

    def test_npc_regard_delta_zero_is_always_allowed(self):
        stake = StakeFactory(subject_kind=StakeSubjectKind.FACTION)
        problems = self._problems_for(stake, npc_regard_delta=0)
        self.assertFalse(any(p.field == "npc_regard_delta" for p in problems))
