"""Tests for knockback + Trap position-scoping wired into combat (#1317).

Knockback is authored as an on-hit ConsequencePool on ThreatPoolEntry, fired
deterministically (no roll — the attack's own hit already determined it
landed) after the existing #1273 Interpose seam resolves, using the same
mutable DamagePreApplyPayload.amount check that makes "clean interpose also
blocks the knockback" fall out for free.
"""

from __future__ import annotations

from django.test import TestCase

from world.combat.factories import ThreatPoolEntryFactory


class ThreatPoolEntryOnHitPoolTest(TestCase):
    def test_on_hit_consequence_pool_defaults_to_none(self) -> None:
        entry = ThreatPoolEntryFactory()
        assert entry.on_hit_consequence_pool is None
