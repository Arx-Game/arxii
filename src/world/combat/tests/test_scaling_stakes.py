"""Tests for validate_stakes_requirement (Task 4, #566; rewired to GMProfile in #2000).

Covers:
- Party average level below minimum → StakesRequirementError
- GM level below minimum → StakesRequirementError
- Qualifying party + qualifying GM → no raise
- Staff account bypass → no raise even when under-gated
- No StakesLevelRequirement row for the stakes level → no raise (ungated)
- StakesRequirementError carries a user_message attribute
- No-GMProfile rule: fails any row above STARTING, passes STARTING rows
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
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory


def _make_encounter_with_avg_level(avg_level: float, stakes_level: str) -> object:
    """Create an encounter with one ACTIVE participant at *avg_level* for *stakes_level*."""
    encounter = CombatEncounterFactory(stakes_level=stakes_level)
    participant = CombatParticipantFactory(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    )
    CharacterClassLevelFactory(
        character=participant.character_sheet,
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
    """Staff accounts bypass all gates, even when party and GM level are below minimum."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = _make_encounter_with_avg_level(1, StakesLevel.REGIONAL)
        # Requirement: party avg ≥ 10, GM level ≥ SENIOR
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=10,
            minimum_gm_level=GMLevel.SENIOR,
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
            minimum_gm_level=GMLevel.STARTING,
        )
        # GM with sufficient level (no level barrier, but party is too weak).
        cls.account = AccountFactory()
        GMProfileFactory(account=cls.account, level=GMLevel.SENIOR)

    def test_party_below_minimum_raises(self):
        with self.assertRaises(StakesRequirementError) as ctx:
            validate_stakes_requirement(self.encounter, self.account)
        self.assertIn("5", ctx.exception.user_message)

    def test_error_mentions_actual_level(self):
        with self.assertRaises(StakesRequirementError) as ctx:
            validate_stakes_requirement(self.encounter, self.account)
        # message should name the actual party level clause, not just be non-empty
        self.assertIn("Party average level", ctx.exception.user_message)


class ValidateStakesRequirementGMLevelGateTest(TestCase):
    """GM level below minimum → StakesRequirementError."""

    @classmethod
    def setUpTestData(cls):
        # Party meets the level requirement.
        cls.encounter = _make_encounter_with_avg_level(10, StakesLevel.REGIONAL)
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=5,
            minimum_gm_level=GMLevel.EXPERIENCED,
        )
        # GM has only JUNIOR level — below EXPERIENCED.
        cls.account = AccountFactory()
        GMProfileFactory(account=cls.account, level=GMLevel.JUNIOR)

    def test_gm_level_below_minimum_raises(self):
        with self.assertRaises(StakesRequirementError) as ctx:
            validate_stakes_requirement(self.encounter, self.account)
        self.assertTrue(ctx.exception.user_message)


class ValidateStakesRequirementNoGMProfileTest(TestCase):
    """No-GMProfile rule: fails any row above STARTING, passes STARTING rows."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = _make_encounter_with_avg_level(10, StakesLevel.REGIONAL)
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=0,
            minimum_gm_level=GMLevel.JUNIOR,
        )
        # Account with NO GMProfile row → treated as GMLevel.STARTING.
        cls.account = AccountFactory()

    def test_missing_gm_profile_raises_when_minimum_is_above_starting(self):
        with self.assertRaises(StakesRequirementError):
            validate_stakes_requirement(self.encounter, self.account)

    def test_missing_gm_profile_passes_when_minimum_is_starting(self):
        encounter = _make_encounter_with_avg_level(10, StakesLevel.NATIONAL)
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.NATIONAL,
            minimum_party_average_level=0,
            minimum_gm_level=GMLevel.STARTING,
        )
        # Must not raise — no profile passes a STARTING-minimum row.
        validate_stakes_requirement(encounter, self.account)


class ValidateStakesRequirementQualifyingGMTest(TestCase):
    """Qualifying party + qualifying GM → no raise."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = _make_encounter_with_avg_level(6, StakesLevel.REGIONAL)
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=5,
            minimum_gm_level=GMLevel.JUNIOR,
        )
        cls.account = AccountFactory()
        GMProfileFactory(account=cls.account, level=GMLevel.GM)

    def test_qualifying_gm_does_not_raise(self):
        # Must not raise.
        validate_stakes_requirement(self.encounter, self.account)

    def test_gm_at_exact_level_minimum_does_not_raise(self):
        # Create a second account exactly at the minimum.
        exact_account = AccountFactory()
        GMProfileFactory(account=exact_account, level=GMLevel.JUNIOR)
        validate_stakes_requirement(self.encounter, exact_account)

    def test_party_at_exact_level_minimum_does_not_raise(self):
        # Encounter with party avg == minimum_party_average_level (5).
        encounter_exact = _make_encounter_with_avg_level(5, StakesLevel.REGIONAL)
        validate_stakes_requirement(encounter_exact, self.account)


class ValidateStakesRequirementJuniorProfileTest(TestCase):
    """GM with JUNIOR profile passes REGIONAL, fails NATIONAL (brief's example case)."""

    @classmethod
    def setUpTestData(cls):
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=0,
            minimum_gm_level=GMLevel.JUNIOR,
        )
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.NATIONAL,
            minimum_party_average_level=0,
            minimum_gm_level=GMLevel.GM,
        )
        cls.account = AccountFactory()
        GMProfileFactory(account=cls.account, level=GMLevel.JUNIOR)

    def test_junior_gm_passes_regional(self):
        encounter = _make_encounter_with_avg_level(10, StakesLevel.REGIONAL)
        validate_stakes_requirement(encounter, self.account)

    def test_junior_gm_fails_national(self):
        encounter = _make_encounter_with_avg_level(10, StakesLevel.NATIONAL)
        with self.assertRaises(StakesRequirementError):
            validate_stakes_requirement(encounter, self.account)


class ValidateStakesRequirementNoProfileLocalVsRegionalTest(TestCase):
    """Account with no GMProfile fails REGIONAL, passes LOCAL (brief's example case)."""

    @classmethod
    def setUpTestData(cls):
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.LOCAL,
            minimum_party_average_level=0,
            minimum_gm_level=GMLevel.STARTING,
        )
        StakesLevelRequirementFactory(
            stakes_level=StakesLevel.REGIONAL,
            minimum_party_average_level=0,
            minimum_gm_level=GMLevel.JUNIOR,
        )
        cls.account = AccountFactory()

    def test_no_profile_passes_local(self):
        encounter = _make_encounter_with_avg_level(10, StakesLevel.LOCAL)
        validate_stakes_requirement(encounter, self.account)

    def test_no_profile_fails_regional(self):
        encounter = _make_encounter_with_avg_level(10, StakesLevel.REGIONAL)
        with self.assertRaises(StakesRequirementError):
            validate_stakes_requirement(encounter, self.account)
