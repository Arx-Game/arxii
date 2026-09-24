"""Tests for relationship bond combat bonuses (#2021, #3957: tier ladder, not developed value)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTierFactory
from world.relationships.models import BondCombatConfig
from world.relationships.services import bond_bonus, bond_combat_bonus, soul_tether_active


def _make_bonded_pair(tier_number=3):
    """Create a directed relationship claimed at the given tier."""
    sheet = CharacterSheetFactory()
    ally = CharacterSheetFactory()
    rel = CharacterRelationshipFactory(source=sheet, target=ally, is_active=True, tier=tier_number)
    return sheet, ally, rel


def _make_mock_encounter(ally_sheets):
    """Build a mock encounter with the given ally sheets as ACTIVE participants.

    The mock returns a list of participant mocks from the chained queryset call
    (filter -> exclude -> select_related -> iteration). Since the service iterates
    the result, a plain list works.
    """
    encounter = MagicMock()
    participants = []
    for sheet in ally_sheets:
        p = MagicMock()
        p.character_sheet = sheet
        p.status = "active"
        participants.append(p)
    qs = encounter.participants.filter.return_value
    qs.exclude.return_value.select_related.return_value = participants
    return encounter


class BondCombatBonusTests(TestCase):
    """Tests for bond_combat_bonus service (#2021, #3957)."""

    @classmethod
    def setUpTestData(cls):
        RelationshipTierFactory(tier_number=1, combat_bonus=1)
        RelationshipTierFactory(tier_number=2, combat_bonus=2)
        RelationshipTierFactory(tier_number=3, combat_bonus=3)
        BondCombatConfig.objects.update_or_create(pk=1, defaults={"min_tier": 2})

    def test_no_bond_returns_empty(self):
        """No relationship -> no contributions."""
        sheet = CharacterSheetFactory()
        encounter = _make_mock_encounter([])
        self.assertEqual(bond_combat_bonus(sheet, encounter), [])

    def test_bond_below_floor_skipped(self):
        """Relationship below min_tier -> no contribution."""
        sheet, ally, _ = _make_bonded_pair(tier_number=1)
        encounter = _make_mock_encounter([ally])
        self.assertEqual(bond_combat_bonus(sheet, encounter), [])

    def test_bond_above_floor_grants_bonus(self):
        """Relationship at/above min_tier -> contribution valued by tier's combat_bonus."""
        sheet, ally, _ = _make_bonded_pair(tier_number=3)
        encounter = _make_mock_encounter([ally])
        contributions = bond_combat_bonus(sheet, encounter)
        self.assertEqual(len(contributions), 1)
        self.assertEqual(contributions[0].value, 3)
        self.assertIn("Bond", contributions[0].source_label)

    def test_multiple_allies_stack(self):
        """Two bonded allies -> two contributions."""
        sheet = CharacterSheetFactory()
        ally1, ally2 = CharacterSheetFactory(), CharacterSheetFactory()
        for ally in (ally1, ally2):
            CharacterRelationshipFactory(source=sheet, target=ally, is_active=True, tier=3)
        encounter = _make_mock_encounter([ally1, ally2])
        contributions = bond_combat_bonus(sheet, encounter)
        self.assertEqual(len(contributions), 2)

    def test_incapacitated_ally_excluded(self):
        """No active participants -> no contributions."""
        sheet, _ally, _ = _make_bonded_pair(tier_number=3)
        encounter = _make_mock_encounter([])
        self.assertEqual(bond_combat_bonus(sheet, encounter), [])

    def test_inactive_relationship_excluded(self):
        """Inactive relationship -> no contribution."""
        sheet = CharacterSheetFactory()
        ally = CharacterSheetFactory()
        CharacterRelationshipFactory(source=sheet, target=ally, is_active=False, tier=3)
        encounter = _make_mock_encounter([ally])
        self.assertEqual(bond_combat_bonus(sheet, encounter), [])

    def test_soul_tether_doubles_the_bonus(self):
        """A soul-tethered bond's contribution is multiplied by soul_tether_multiplier."""
        sheet, ally, _ = _make_bonded_pair(tier_number=3)
        encounter = _make_mock_encounter([ally])
        with patch("world.relationships.services.soul_tether_active", return_value=True):
            contributions = bond_combat_bonus(sheet, encounter)
        self.assertEqual(contributions[0].value, 6)  # combat_bonus 3 x multiplier 2


class BondBonusTests(TestCase):
    """Tests for bond_bonus (protection-scoped) service (#2021, #3957)."""

    @classmethod
    def setUpTestData(cls):
        RelationshipTierFactory(tier_number=1, combat_bonus=1)
        RelationshipTierFactory(tier_number=3, combat_bonus=3)
        BondCombatConfig.objects.update_or_create(pk=1, defaults={"min_tier": 2})

    def test_no_relationship_returns_zero(self):
        """No directed relationship -> 0."""
        sheet = CharacterSheetFactory()
        ally = CharacterSheetFactory()
        actor = MagicMock()
        actor.character_sheet = sheet
        protected = MagicMock()
        protected.character_sheet = ally
        self.assertEqual(bond_bonus(actor, protected), 0)

    def test_bond_above_floor_returns_bonus(self):
        """Directed relationship above floor -> the claimed tier's combat_bonus."""
        sheet, ally, _ = _make_bonded_pair(tier_number=3)
        actor = MagicMock()
        actor.character_sheet = sheet
        protected = MagicMock()
        protected.character_sheet = ally
        self.assertEqual(bond_bonus(actor, protected), 3)

    def test_bond_below_floor_returns_zero(self):
        """Directed relationship below floor -> 0."""
        sheet, ally, _ = _make_bonded_pair(tier_number=1)
        actor = MagicMock()
        actor.character_sheet = sheet
        protected = MagicMock()
        protected.character_sheet = ally
        self.assertEqual(bond_bonus(actor, protected), 0)

    def test_no_sheet_data_returns_zero(self):
        """Actor/protected with no sheet -> 0."""
        actor = MagicMock()
        actor.character_sheet = None
        protected = MagicMock()
        protected.character_sheet = None
        self.assertEqual(bond_bonus(actor, protected), 0)


class SoulTetherActiveTests(TestCase):
    """Tests for soul_tether_active detection (#2021)."""

    def test_no_tether_returns_false(self):
        """No RELATIONSHIP_CAPSTONE thread -> False."""
        a = CharacterSheetFactory()
        b = CharacterSheetFactory()
        self.assertFalse(soul_tether_active(a, b))
