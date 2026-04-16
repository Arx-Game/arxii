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
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        assert has_pending_alterations(self.sheet) is True

    def test_gate_allows_when_resolved(self):
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.RESOLVED,
        )
        assert has_pending_alterations(self.sheet) is False

    def test_gate_allows_when_staff_cleared(self):
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            status=PendingAlterationStatus.STAFF_CLEARED,
        )
        assert has_pending_alterations(self.sheet) is False

    def test_gate_allows_when_no_pendings(self):
        assert has_pending_alterations(self.sheet) is False
