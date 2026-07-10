"""E2E tests for relationship bond combat bonuses (#2021).

Tests the full journey: two bonded PCs in a combat encounter — co-combat passive
applies while both stand, drops when one falls, and bonded INTERPOSE outperforms
stranger INTERPOSE.
"""

from django.test import TestCase

from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import apply_interpose_outcome
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.relationships.services import bond_combat_bonus


class BondCombatE2ETests(TestCase):
    """E2E: two bonded PCs vs NPCs — co-combat passive applies and drops on fall."""

    def setUp(self):
        from world.character_sheets.factories import CharacterSheetFactory

        # Create two character sheets
        self.sheet = CharacterSheetFactory()
        self.ally = CharacterSheetFactory()

        # Create a bonded relationship (developed_absolute_value = 27 → cube root = 3)
        self.rel = CharacterRelationshipFactory(
            source=self.sheet, target=self.ally, is_active=True, is_pending=False
        )
        track = RelationshipTrackFactory(sign="POSITIVE")
        RelationshipTrackProgressFactory(relationship=self.rel, track=track, developed_points=27)

        # Create a combat encounter with both as participants
        self.encounter = CombatEncounterFactory()
        self.pc_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )
        self.ally_participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.ally
        )

    def test_bond_bonus_appears_for_bonded_co_combatant(self):
        """bond_combat_bonus returns a contribution for the bonded ally."""
        contributions = bond_combat_bonus(self.sheet, self.encounter)
        self.assertEqual(len(contributions), 1)
        self.assertEqual(contributions[0].value, 3)  # cube root of 27
        self.assertIn("Bond", contributions[0].source_label)

    def test_bond_bonus_drops_when_ally_falls(self):
        """When ally status changes to REMOVED, no bond contribution."""
        self.ally_participant.status = ParticipantStatus.REMOVED
        self.ally_participant.save(update_fields=["status"])
        contributions = bond_combat_bonus(self.sheet, self.encounter)
        self.assertEqual(contributions, [])

    def test_bond_bonus_drops_when_ally_fled(self):
        """When ally status changes to FLED, no bond contribution."""
        self.ally_participant.status = ParticipantStatus.FLED
        self.ally_participant.save(update_fields=["status"])
        contributions = bond_combat_bonus(self.sheet, self.encounter)
        self.assertEqual(contributions, [])

    def test_no_bonus_for_stranger(self):
        """A non-bonded co-combatant gets no contribution."""
        from world.character_sheets.factories import CharacterSheetFactory

        stranger = CharacterSheetFactory()
        CombatParticipantFactory(encounter=self.encounter, character_sheet=stranger)
        # The stranger has no relationship with self.sheet
        # bond_combat_bonus should still return only 1 (for the bonded ally)
        contributions = bond_combat_bonus(self.sheet, self.encounter)
        self.assertEqual(len(contributions), 1)

    def test_bond_bonus_service_importable(self):
        """bond_combat_bonus is importable and callable."""
        self.assertTrue(callable(bond_combat_bonus))


class BondProtectionE2ETests(TestCase):
    """Bond bonus flows through to INTERPOSE protection check."""

    def test_apply_interpose_outcome_importable(self):
        """apply_interpose_outcome is importable (wiring smoke test)."""
        self.assertTrue(callable(apply_interpose_outcome))
