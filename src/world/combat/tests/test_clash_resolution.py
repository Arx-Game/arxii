"""Tests for npc_round_contribution in world.combat.clash."""

from django.test import TestCase

from world.combat.clash import npc_round_contribution
from world.combat.constants import ClashFlavor, LockPcRole
from world.combat.factories import (
    BreakClashFactory,
    ClashFactory,
    LockClashFactory,
    ThreatPoolEntryFactory,
    WardClashFactory,
)


class NpcRoundContributionTests(TestCase):
    """Unit tests for npc_round_contribution — one test per flavor branch."""

    def test_break_returns_zero(self) -> None:
        """BREAK clash always returns 0, regardless of triggering_threat_entry."""
        entry = ThreatPoolEntryFactory(clash_npc_pressure=9)
        clash = BreakClashFactory(triggering_threat_entry=entry)
        result = npc_round_contribution(clash=clash, round_number=1)
        self.assertEqual(result, 0)

    def test_no_triggering_entry_returns_zero(self) -> None:
        """Non-BREAK clash with triggering_threat_entry=None returns 0 (defensive guard)."""
        clash = ClashFactory(triggering_threat_entry=None)
        self.assertEqual(clash.flavor, ClashFlavor.CLASH)
        result = npc_round_contribution(clash=clash, round_number=1)
        self.assertEqual(result, 0)

    def test_clash_uses_entry_pressure(self) -> None:
        """CLASH flavor returns triggering_threat_entry.clash_npc_pressure."""
        entry = ThreatPoolEntryFactory(clash_npc_pressure=8)
        clash = ClashFactory(triggering_threat_entry=entry)
        result = npc_round_contribution(clash=clash, round_number=1)
        self.assertEqual(result, 8)

    def test_ward_uses_entry_pressure(self) -> None:
        """WARD flavor returns triggering_threat_entry.clash_npc_pressure."""
        entry = ThreatPoolEntryFactory(clash_npc_pressure=5)
        clash = WardClashFactory(triggering_threat_entry=entry)
        result = npc_round_contribution(clash=clash, round_number=1)
        self.assertEqual(result, 5)

    def test_lock_sustaining_uses_break_free_force(self) -> None:
        """LOCK / SUSTAINING: PC holds the lock, NPC breaks free — uses clash_break_free_force."""
        entry = ThreatPoolEntryFactory(clash_break_free_force=4)
        clash = LockClashFactory(lock_pc_role=LockPcRole.SUSTAINING, triggering_threat_entry=entry)
        result = npc_round_contribution(clash=clash, round_number=1)
        self.assertEqual(result, 4)

    def test_lock_escaping_uses_npc_pressure(self) -> None:
        """LOCK / ESCAPING (PC escapes lock, NPC maintains it): uses clash_npc_pressure."""
        entry = ThreatPoolEntryFactory(clash_npc_pressure=6)
        clash = LockClashFactory(lock_pc_role=LockPcRole.ESCAPING, triggering_threat_entry=entry)
        result = npc_round_contribution(clash=clash, round_number=1)
        self.assertEqual(result, 6)
