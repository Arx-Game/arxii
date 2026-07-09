"""Tests for relationship bond combat bonuses (#2021)."""

from unittest.mock import MagicMock

from django.test import TestCase

from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.relationships.services import (
    bond_bonus,
    bond_combat_bonus,
    soul_tether_active,
)


def _make_bonded_pair(sheet_factory, developed_points=27):
    """Create a directed relationship with the given developed points."""
    sheet = sheet_factory()
    ally = sheet_factory()
    rel = CharacterRelationshipFactory(source=sheet, target=ally, is_active=True, is_pending=False)
    track = RelationshipTrackFactory(sign="POSITIVE")
    RelationshipTrackProgressFactory(
        relationship=rel, track=track, developed_points=developed_points
    )
    return sheet, ally, rel


def _make_mock_encounter(ally_sheets):
    """Build a mock encounter with the given ally sheets as ACTIVE participants.

    The mock returns a list of participant mocks from the chained queryset call
    (filter → exclude → select_related → iteration). Since the service iterates
    the result, a plain list works.
    """
    encounter = MagicMock()
    participants = []
    for sheet in ally_sheets:
        p = MagicMock()
        p.character_sheet = sheet
        p.status = "active"
        participants.append(p)
    # The service does: encounter.participants.filter(...).exclude(...).select_related(...)
    # select_related returns the queryset, which is then iterated. A list works.
    qs = encounter.participants.filter.return_value
    qs.exclude.return_value.select_related.return_value = participants
    return encounter


class BondCombatBonusTests(TestCase):
    """Tests for bond_combat_bonus service (#2021)."""

    def test_no_bond_returns_empty(self):
        """No relationship → no contributions."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        encounter = _make_mock_encounter([])
        contributions = bond_combat_bonus(sheet, encounter)
        self.assertEqual(contributions, [])

    def test_bond_below_floor_skipped(self):
        """Relationship below min_developed_absolute_value → no contribution."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet, ally, _ = _make_bonded_pair(CharacterSheetFactory, developed_points=5)
        encounter = _make_mock_encounter([ally])
        contributions = bond_combat_bonus(sheet, encounter)
        self.assertEqual(contributions, [])

    def test_bond_above_floor_grants_bonus(self):
        """Relationship above floor → contribution with mechanical_bonus value."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet, ally, _ = _make_bonded_pair(CharacterSheetFactory, developed_points=27)
        encounter = _make_mock_encounter([ally])
        contributions = bond_combat_bonus(sheet, encounter)
        self.assertEqual(len(contributions), 1)
        # cube root of 27 = 3.0 → int = 3
        self.assertEqual(contributions[0].value, 3)
        self.assertIn("Bond", contributions[0].source_label)

    def test_multiple_allies_stack(self):
        """Two bonded allies → two contributions."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        ally1, ally2 = CharacterSheetFactory(), CharacterSheetFactory()
        for ally in (ally1, ally2):
            rel = CharacterRelationshipFactory(
                source=sheet, target=ally, is_active=True, is_pending=False
            )
            track = RelationshipTrackFactory(sign="POSITIVE")
            RelationshipTrackProgressFactory(relationship=rel, track=track, developed_points=27)
        encounter = _make_mock_encounter([ally1, ally2])
        contributions = bond_combat_bonus(sheet, encounter)
        self.assertEqual(len(contributions), 2)

    def test_incapacitated_ally_excluded(self):
        """No active participants → no contributions."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet, _ally, _ = _make_bonded_pair(CharacterSheetFactory, developed_points=27)
        encounter = _make_mock_encounter([])
        contributions = bond_combat_bonus(sheet, encounter)
        self.assertEqual(contributions, [])

    def test_pending_relationship_excluded(self):
        """Pending (unreciprocated) relationship → no contribution."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        ally = CharacterSheetFactory()
        rel = CharacterRelationshipFactory(
            source=sheet, target=ally, is_active=True, is_pending=True
        )
        track = RelationshipTrackFactory(sign="POSITIVE")
        RelationshipTrackProgressFactory(relationship=rel, track=track, developed_points=27)
        encounter = _make_mock_encounter([ally])
        contributions = bond_combat_bonus(sheet, encounter)
        self.assertEqual(contributions, [])

    def test_inactive_relationship_excluded(self):
        """Inactive relationship → no contribution."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        ally = CharacterSheetFactory()
        rel = CharacterRelationshipFactory(
            source=sheet, target=ally, is_active=False, is_pending=False
        )
        track = RelationshipTrackFactory(sign="POSITIVE")
        RelationshipTrackProgressFactory(relationship=rel, track=track, developed_points=27)
        encounter = _make_mock_encounter([ally])
        contributions = bond_combat_bonus(sheet, encounter)
        self.assertEqual(contributions, [])


class BondBonusTests(TestCase):
    """Tests for bond_bonus (protection-scoped) service (#2021)."""

    def test_no_relationship_returns_zero(self):
        """No directed relationship → 0."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        ally = CharacterSheetFactory()
        actor = MagicMock()
        actor.sheet_data = sheet
        protected = MagicMock()
        protected.sheet_data = ally
        self.assertEqual(bond_bonus(actor, protected), 0)

    def test_bond_above_floor_returns_bonus(self):
        """Directed relationship above floor → int(mechanical_bonus)."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet, ally, _ = _make_bonded_pair(CharacterSheetFactory, developed_points=27)
        actor = MagicMock()
        actor.sheet_data = sheet
        protected = MagicMock()
        protected.sheet_data = ally
        self.assertEqual(bond_bonus(actor, protected), 3)

    def test_bond_below_floor_returns_zero(self):
        """Directed relationship below floor → 0."""
        from world.character_sheets.factories import CharacterSheetFactory

        sheet, ally, _ = _make_bonded_pair(CharacterSheetFactory, developed_points=5)
        actor = MagicMock()
        actor.sheet_data = sheet
        protected = MagicMock()
        protected.sheet_data = ally
        self.assertEqual(bond_bonus(actor, protected), 0)

    def test_no_sheet_data_returns_zero(self):
        """Actor/protected with no sheet_data → 0."""
        actor = MagicMock()
        actor.sheet_data = None
        protected = MagicMock()
        protected.sheet_data = None
        self.assertEqual(bond_bonus(actor, protected), 0)


class SoulTetherActiveTests(TestCase):
    """Tests for soul_tether_active detection (#2021)."""

    def test_no_tether_returns_false(self):
        """No RELATIONSHIP_CAPSTONE thread → False."""
        from world.character_sheets.factories import CharacterSheetFactory

        a = CharacterSheetFactory()
        b = CharacterSheetFactory()
        self.assertFalse(soul_tether_active(a, b))
