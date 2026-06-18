"""Tests for compute_party_profile (Task 2, #566).

Covers:
- Basic level aggregation: 3 ACTIVE participants with primary class levels 2/4/6 → avg 4.0, size 3
- Only ACTIVE participants count (FLED/REMOVED excluded)
- Empty party → avg_level 0.0, party_size 0
- Invariant: threads (covenant_role, or any non-level attribute) do not change the profile
"""

from django.test import TestCase

from world.classes.factories import CharacterClassLevelFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.scaling import PartyProfile, compute_party_profile


class ComputePartyProfileBasicTest(TestCase):
    """compute_party_profile aggregates ACTIVE participant primary class levels."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = CombatEncounterFactory()

        # Build 3 ACTIVE participants with primary class levels 2, 4, 6
        cls.participants = []
        for level in (2, 4, 6):
            participant = CombatParticipantFactory(
                encounter=cls.encounter,
                status=ParticipantStatus.ACTIVE,
            )
            CharacterClassLevelFactory(
                character=participant.character_sheet.character,
                level=level,
                is_primary=True,
            )
            cls.participants.append(participant)

    def test_party_size_is_three(self):
        profile = compute_party_profile(self.encounter)
        self.assertEqual(profile.party_size, 3)

    def test_avg_level_is_four(self):
        profile = compute_party_profile(self.encounter)
        self.assertAlmostEqual(profile.avg_level, 4.0)

    def test_returns_party_profile_dataclass(self):
        profile = compute_party_profile(self.encounter)
        self.assertIsInstance(profile, PartyProfile)

    def test_party_profile_is_frozen(self):
        profile = compute_party_profile(self.encounter)
        with self.assertRaises((AttributeError, TypeError)):
            profile.party_size = 99  # type: ignore[misc]


class ComputePartyProfileExcludesInactiveTest(TestCase):
    """Only ACTIVE participants count; FLED/REMOVED are excluded."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = CombatEncounterFactory()

        # 2 ACTIVE participants with level 4
        cls.active_participants = []
        for _ in range(2):
            participant = CombatParticipantFactory(
                encounter=cls.encounter,
                status=ParticipantStatus.ACTIVE,
            )
            CharacterClassLevelFactory(
                character=participant.character_sheet.character,
                level=4,
                is_primary=True,
            )
            cls.active_participants.append(participant)

        # 1 FLED participant with level 10 — must NOT affect the result
        fled_participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.FLED,
        )
        CharacterClassLevelFactory(
            character=fled_participant.character_sheet.character,
            level=10,
            is_primary=True,
        )

        # 1 REMOVED participant with level 10 — must NOT affect the result
        removed_participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.REMOVED,
        )
        CharacterClassLevelFactory(
            character=removed_participant.character_sheet.character,
            level=10,
            is_primary=True,
        )

    def test_party_size_excludes_fled_and_removed(self):
        profile = compute_party_profile(self.encounter)
        self.assertEqual(profile.party_size, 2)

    def test_avg_level_excludes_fled_and_removed(self):
        profile = compute_party_profile(self.encounter)
        self.assertAlmostEqual(profile.avg_level, 4.0)


class ComputePartyProfileEmptyPartyTest(TestCase):
    """An encounter with no ACTIVE participants returns a zero profile."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = CombatEncounterFactory()

    def test_empty_party_size_is_zero(self):
        profile = compute_party_profile(self.encounter)
        self.assertEqual(profile.party_size, 0)

    def test_empty_avg_level_is_zero(self):
        profile = compute_party_profile(self.encounter)
        self.assertAlmostEqual(profile.avg_level, 0.0)


class ComputePartyProfileThreadInvariantTest(TestCase):
    """Threads (covenant_role, etc.) do not change the party profile.

    Two encounters whose ACTIVE participants have identical primary class levels
    must yield identical PartyProfiles even when one party has covenant_role set.
    """

    @classmethod
    def setUpTestData(cls):
        # Encounter A: plain participants, no covenant_role
        cls.encounter_a = CombatEncounterFactory()
        for level in (3, 5):
            participant = CombatParticipantFactory(
                encounter=cls.encounter_a,
                status=ParticipantStatus.ACTIVE,
                covenant_role=None,
            )
            CharacterClassLevelFactory(
                character=participant.character_sheet.character,
                level=level,
                is_primary=True,
            )

        # Encounter B: same levels, but participants have covenant_role attached
        from world.covenants.factories import CovenantRoleFactory

        cls.encounter_b = CombatEncounterFactory()
        role = CovenantRoleFactory()
        for level in (3, 5):
            participant = CombatParticipantFactory(
                encounter=cls.encounter_b,
                status=ParticipantStatus.ACTIVE,
                covenant_role=role,
            )
            CharacterClassLevelFactory(
                character=participant.character_sheet.character,
                level=level,
                is_primary=True,
            )

    def test_covenant_role_does_not_change_profile(self):
        profile_a = compute_party_profile(self.encounter_a)
        profile_b = compute_party_profile(self.encounter_b)
        self.assertEqual(profile_a, profile_b)

    def test_profiles_have_expected_values(self):
        profile_a = compute_party_profile(self.encounter_a)
        self.assertEqual(profile_a.party_size, 2)
        self.assertAlmostEqual(profile_a.avg_level, 4.0)
