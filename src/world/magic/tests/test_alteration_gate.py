"""Tests for progression gate integration."""

from evennia.utils.test_resources import BaseEvenniaTest

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import PendingAlterationStatus
from world.magic.factories import AffinityFactory, PendingAlterationFactory, ResonanceFactory
from world.magic.services import has_pending_alterations


class ProgressionGateTests(BaseEvenniaTest):
    """Test that has_pending_alterations correctly gates progression."""

    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(name="Shadow", affinity=cls.affinity)

    def test_gate_blocks_with_open_pending(self):
        """has_pending_alterations returns True when an OPEN pending exists."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        assert has_pending_alterations(self.sheet) is True

    def test_gate_allows_when_resolved(self):
        """has_pending_alterations returns False when all pendings are RESOLVED."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.RESOLVED,
        )
        assert has_pending_alterations(self.sheet) is False

    def test_gate_allows_when_staff_cleared(self):
        """has_pending_alterations returns False when all pendings are STAFF_CLEARED."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.STAFF_CLEARED,
        )
        assert has_pending_alterations(self.sheet) is False

    def test_gate_allows_when_no_pendings(self):
        """has_pending_alterations returns False when no pending alterations exist."""
        assert has_pending_alterations(self.sheet) is False
