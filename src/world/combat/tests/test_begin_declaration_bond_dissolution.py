"""Tests for graduated MentorBond dissolution inside begin_declaration_phase (#1165, Task 6).

Spec: when begin_declaration_phase is called, any active MentorBond for a party
participant whose adjusted side has leveled into the covenant band (is_bond_graduated)
is dissolved by setting dissolved_at.  Non-graduated bonds are left untouched.
"""

from django.test import TestCase
from django.utils import timezone

from world.classes.factories import CharacterClassLevelFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import begin_declaration_phase
from world.covenants.constants import MentorBondAdjusted
from world.covenants.factories import CovenantFactory, MentorBondFactory, seed_mentor_bond_defaults
from world.scenes.constants import RoundStatus


class BeginDeclarationPhaseDissolvesBondTest(TestCase):
    """begin_declaration_phase dissolves a graduated MentorBond.

    A "graduated" bond is one where the adjusted party's raw primary level is
    already within the covenant band — the bond is mechanically inactive so the
    row should be dissolved at encounter start for honest bookkeeping.
    """

    def setUp(self):
        super().setUp()
        # MentorBondConfig singleton: band_width=2, adjacency_offset=1.
        seed_mentor_bond_defaults()

        # Covenant at level 3 → band [1, 5] (level - 2 to level + 2).
        self.covenant = CovenantFactory(level=3)

        self.encounter = CombatEncounterFactory(status=RoundStatus.BETWEEN_ROUNDS)
        # Need at least one active opponent for begin_declaration_phase to proceed.
        CombatOpponentFactory(encounter=self.encounter)

        # Sidekick participant: raw level 3 — now IN band [1, 5] → bond is graduated.
        self.sidekick_participant = CombatParticipantFactory(
            encounter=self.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        self.sidekick_sheet = self.sidekick_participant.character_sheet
        CharacterClassLevelFactory(
            character=self.sidekick_sheet,
            level=3,
            is_primary=True,
        )

        # Mentor (not in this encounter; their sheet just provides the bond).
        from world.character_sheets.factories import CharacterSheetFactory

        self.mentor_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=self.mentor_sheet,
            level=4,
            is_primary=True,
        )

        # Active bond: sidekick is the adjusted party; sidekick's raw level 3 is
        # already in-band → this bond is graduated.
        self.bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
            dissolved_at=None,
        )

    def test_graduated_bond_dissolved_at_encounter_start(self):
        """begin_declaration_phase sets dissolved_at on the graduated bond."""
        self.assertIsNone(self.bond.dissolved_at, "bond must start active")

        begin_declaration_phase(self.encounter)

        self.bond.refresh_from_db()
        self.assertIsNotNone(
            self.bond.dissolved_at,
            "graduated bond must be dissolved after begin_declaration_phase",
        )

    def test_dissolved_at_is_recent(self):
        """dissolved_at is set close to now (not a sentinel)."""
        before = timezone.now()
        begin_declaration_phase(self.encounter)
        after = timezone.now()

        self.bond.refresh_from_db()
        self.assertGreaterEqual(self.bond.dissolved_at, before)
        self.assertLessEqual(self.bond.dissolved_at, after)


class BeginDeclarationPhasePreservesActiveBondTest(TestCase):
    """begin_declaration_phase does NOT dissolve a non-graduated (still-active) bond."""

    def setUp(self):
        super().setUp()
        seed_mentor_bond_defaults()

        # Covenant at level 6 → band [4, 8].
        self.covenant = CovenantFactory(level=6)

        self.encounter = CombatEncounterFactory(status=RoundStatus.BETWEEN_ROUNDS)
        CombatOpponentFactory(encounter=self.encounter)

        # Sidekick participant: raw level 2 — OUT of band [4, 8] → bond is NOT graduated.
        self.sidekick_participant = CombatParticipantFactory(
            encounter=self.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        self.sidekick_sheet = self.sidekick_participant.character_sheet
        CharacterClassLevelFactory(
            character=self.sidekick_sheet,
            level=2,
            is_primary=True,
        )

        from world.character_sheets.factories import CharacterSheetFactory

        self.mentor_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=self.mentor_sheet,
            level=6,
            is_primary=True,
        )

        self.bond = MentorBondFactory(
            covenant=self.covenant,
            mentor_sheet=self.mentor_sheet,
            sidekick_sheet=self.sidekick_sheet,
            adjusted_party=MentorBondAdjusted.SIDEKICK,
            dissolved_at=None,
        )

    def test_non_graduated_bond_is_not_dissolved(self):
        """Non-graduated bond remains active after begin_declaration_phase."""
        begin_declaration_phase(self.encounter)

        self.bond.refresh_from_db()
        self.assertIsNone(
            self.bond.dissolved_at,
            "non-graduated bond must remain active after begin_declaration_phase",
        )
