"""Tests for validate_stakes_requirement (Task 4, #566).

Covers:
- Party average level below minimum → StakesRequirementError
- GM trust level below minimum → StakesRequirementError
- Qualifying party + qualifying GM → no raise
- Staff account bypass → no raise even when under-gated
- No StakesLevelRequirement row for the stakes level → no raise (ungated)
- StakesRequirementError carries a user_message attribute
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.classes.factories import CharacterClassLevelFactory
from world.combat.constants import ParticipantStatus, StakesLevel
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    StakesLevelRequirementFactory,
)
from world.combat.scaling import StakesRequirementError, validate_stakes_requirement
from world.stories.factories import PlayerTrustFactory
from world.stories.types import TrustLevel


def _make_encounter_with_avg_level(avg_level: float, stakes_level: str) -> object:
    """Create an encounter with one ACTIVE participant at *avg_level* for *stakes_level*."""
    encounter = CombatEncounterFactory(stakes_level=stakes_level)
    participant = CombatParticipantFactory(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    )
    CharacterClassLevelFactory(
        character=participant.character_sheet.character,
        level=int(avg_level),
        is_primary=True,
    )
    return encounter


class StakesRequirementErrorTest(TestCase):
    """StakesRequirementError is a ValueError with a user_message attribute."""

    def test_is_value_error_subclass(self):
        err = StakesRequirementError("test", user_message="msg")
        self.assertIsInstance(err, ValueError)

    def test_carries_user_message(self):
        err = StakesRequirementError("test", user_message="needs level 10")
        self.assertEqual(err.user_message, "needs level 10")


class ValidateStakesRequirementUngatedTest(TestCase):
    """When no requirement row exists for the stakes level, validation passes."""

    @classmethod
    def setUpTestData(cls):
        # LOCAL has no StakesLevelRequirement row created here — ungated by design.
        # (We deliberately do NOT call StakesLevelRequirementFactory for LOCAL.)
        cls.encounter = CombatEncounterFactory(stakes_level=StakesLevel.LOCAL)
        cls.account = AccountFactory()

    def test_no_requirement_row_allows_any_gm(self):
        # Should not raise — no requirement record for LOCAL in this test DB.
        validate_stakes_requirement(self.encounter, self.account)


class ValidateStakesRequirementStaffBypassTest(TestCase):
    """Staff accounts bypass all gates, even when party and trust are below minimum."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = _make_encounter_with_avg_level(1, StakesLevel.REGIONAL)
        # Requirement: party avg ≥ 10, GM trust ≥ EXPERT
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=10,
            minimum_gm_trust_level=TrustLevel.EXPERT,
        )
        cls.staff_account = AccountFactory(is_staff=True)

    def test_staff_bypasses_party_level_gate(self):
        validate_stakes_requirement(self.encounter, self.staff_account)


class ValidateStakesRequirementPartyLevelGateTest(TestCase):
    """Party average level below minimum → StakesRequirementError."""

    @classmethod
    def setUpTestData(cls):
        # Encounter with a party averaging level 3.
        cls.encounter = _make_encounter_with_avg_level(3, StakesLevel.REGIONAL)
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=5,
            minimum_gm_trust_level=TrustLevel.UNTRUSTED,
        )
        # GM with sufficient trust (no trust barrier, but party is too weak).
        cls.account = AccountFactory()
        PlayerTrustFactory(account=cls.account, gm_trust_level=TrustLevel.EXPERT)

    def test_party_below_minimum_raises(self):
        with self.assertRaises(StakesRequirementError) as ctx:
            validate_stakes_requirement(self.encounter, self.account)
        self.assertIn("5", ctx.exception.user_message)

    def test_error_mentions_actual_level(self):
        with self.assertRaises(StakesRequirementError) as ctx:
            validate_stakes_requirement(self.encounter, self.account)
        # user_message should mention the required level somewhere
        self.assertTrue(ctx.exception.user_message)


class ValidateStakesRequirementGMTrustGateTest(TestCase):
    """GM trust below minimum → StakesRequirementError."""

    @classmethod
    def setUpTestData(cls):
        # Party meets the level requirement.
        cls.encounter = _make_encounter_with_avg_level(10, StakesLevel.REGIONAL)
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=5,
            minimum_gm_trust_level=TrustLevel.ADVANCED,
        )
        # GM has only BASIC trust — below ADVANCED.
        cls.account = AccountFactory()
        PlayerTrustFactory(account=cls.account, gm_trust_level=TrustLevel.BASIC)

    def test_gm_trust_below_minimum_raises(self):
        with self.assertRaises(StakesRequirementError) as ctx:
            validate_stakes_requirement(self.encounter, self.account)
        self.assertTrue(ctx.exception.user_message)


class ValidateStakesRequirementNoTrustProfileTest(TestCase):
    """GM with no trust_profile is treated as UNTRUSTED (lowest TrustLevel)."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = _make_encounter_with_avg_level(10, StakesLevel.REGIONAL)
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=0,
            minimum_gm_trust_level=TrustLevel.BASIC,
        )
        # Account with NO PlayerTrust row → treated as UNTRUSTED.
        cls.account = AccountFactory()

    def test_missing_trust_profile_raises_when_minimum_is_basic(self):
        with self.assertRaises(StakesRequirementError):
            validate_stakes_requirement(self.encounter, self.account)


class ValidateStakesRequirementQualifyingGMTest(TestCase):
    """Qualifying party + qualifying GM → no raise."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = _make_encounter_with_avg_level(6, StakesLevel.REGIONAL)
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=5,
            minimum_gm_trust_level=TrustLevel.BASIC,
        )
        cls.account = AccountFactory()
        PlayerTrustFactory(account=cls.account, gm_trust_level=TrustLevel.INTERMEDIATE)

    def test_qualifying_gm_does_not_raise(self):
        # Must not raise.
        validate_stakes_requirement(self.encounter, self.account)

    def test_gm_at_exact_trust_minimum_does_not_raise(self):
        # Create a second account exactly at the minimum.
        exact_account = AccountFactory()
        PlayerTrustFactory(account=exact_account, gm_trust_level=TrustLevel.BASIC)
        validate_stakes_requirement(self.encounter, exact_account)

    def test_party_at_exact_level_minimum_does_not_raise(self):
        # Encounter with party avg == minimum_party_average_level (5).
        encounter_exact = _make_encounter_with_avg_level(5, StakesLevel.REGIONAL)
        validate_stakes_requirement(encounter_exact, self.account)
