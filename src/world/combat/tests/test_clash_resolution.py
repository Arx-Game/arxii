"""Tests for npc_round_contribution and affinity_tilt in world.combat.clash."""

from decimal import Decimal

from django.test import TestCase

from world.combat.clash import affinity_tilt, npc_round_contribution
from world.combat.constants import ClashFlavor, LockPcRole
from world.combat.factories import (
    BreakClashFactory,
    ClashConfigFactory,
    ClashFactory,
    LockClashFactory,
    ThreatPoolEntryFactory,
    WardClashFactory,
)
from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceValence,
)
from world.magic.factories import (
    AffinityFactory,
    AffinityInteractionFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models.resonance_environment import AffinityInteraction


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


class AffinityTiltTests(TestCase):
    """Unit tests for affinity_tilt — one test per branch of the function."""

    def setUp(self) -> None:
        # Clear the AffinityInteraction manager cache so each test starts cold.
        AffinityInteraction.objects.clear_cache()
        self.config = ClashConfigFactory()

    def _make_technique_with_affinity(self, affinity):  # type: ignore[no-untyped-def]
        """Build a Gift+Resonance+Technique chain with the given affinity."""
        resonance = ResonanceFactory(affinity=affinity)
        gift = GiftFactory()
        gift.resonances.add(resonance)
        return TechniqueFactory(gift=gift)

    def test_same_affinity_returns_zero(self) -> None:
        """Technique affinity == NPC affinity (ALIGNED interaction) → 0."""
        affinity = AffinityFactory()
        technique = self._make_technique_with_affinity(affinity)
        # Create an ALIGNED row for the same-vs-same pair.
        AffinityInteractionFactory(
            source_affinity=affinity,
            environment_affinity=affinity,
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("2.00"),
        )
        # Cache is stale from the factory load; clear it again so the new row is visible.
        AffinityInteraction.objects.clear_cache()
        result = affinity_tilt(
            contributor_technique=technique,
            npc_attack_affinity=affinity,
            config=self.config,
        )
        self.assertEqual(result, 0)
        self.assertIsInstance(result, int)

    def test_no_npc_affinity_returns_zero(self) -> None:
        """npc_attack_affinity=None (non-magical NPC attack) → 0."""
        affinity = AffinityFactory()
        technique = self._make_technique_with_affinity(affinity)
        result = affinity_tilt(
            contributor_technique=technique,
            npc_attack_affinity=None,
            config=self.config,
        )
        self.assertEqual(result, 0)
        self.assertIsInstance(result, int)

    def test_no_matrix_row_returns_zero(self) -> None:
        """No AffinityInteraction row for the (tech, npc) pair → 0."""
        tech_affinity = AffinityFactory()
        npc_affinity = AffinityFactory()
        technique = self._make_technique_with_affinity(tech_affinity)
        # No interaction row exists for this pair — clear cache so manager sees empty table.
        AffinityInteraction.objects.clear_cache()
        result = affinity_tilt(
            contributor_technique=technique,
            npc_attack_affinity=npc_affinity,
            config=self.config,
        )
        self.assertEqual(result, 0)
        self.assertIsInstance(result, int)

    def test_opposed_contributor_dominates_positive_tilt(self) -> None:
        """OPPOSED interaction with aggressor=CASTER → positive tilt (contributor dominates).

        Uses severity_multiplier=4.00 so round(4.00 × 0.25) = 1 (non-zero).
        """
        tech_affinity = AffinityFactory()
        npc_affinity = AffinityFactory()
        technique = self._make_technique_with_affinity(tech_affinity)
        AffinityInteractionFactory(
            source_affinity=tech_affinity,
            environment_affinity=npc_affinity,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.CASTER,
            severity_multiplier=Decimal("4.00"),
        )
        AffinityInteraction.objects.clear_cache()
        result = affinity_tilt(
            contributor_technique=technique,
            npc_attack_affinity=npc_affinity,
            config=self.config,
        )
        self.assertGreater(result, 0)
        self.assertIsInstance(result, int)

    def test_opposed_npc_dominates_negative_tilt(self) -> None:
        """OPPOSED interaction with aggressor=ENVIRONMENT → negative tilt (NPC dominates).

        Uses severity_multiplier=4.00 so round(4.00 × 0.25) = 1 (non-zero), then negated.
        """
        tech_affinity = AffinityFactory()
        npc_affinity = AffinityFactory()
        technique = self._make_technique_with_affinity(tech_affinity)
        AffinityInteractionFactory(
            source_affinity=tech_affinity,
            environment_affinity=npc_affinity,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REPEL,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("4.00"),
        )
        AffinityInteraction.objects.clear_cache()
        result = affinity_tilt(
            contributor_technique=technique,
            npc_attack_affinity=npc_affinity,
            config=self.config,
        )
        self.assertLess(result, 0)
        self.assertIsInstance(result, int)

    def test_tilt_magnitude_uses_severity_and_coefficient(self) -> None:
        """Magnitude == round(severity_multiplier × config.affinity_tilt_coefficient).

        With severity_multiplier=4.00 and affinity_tilt_coefficient=0.25 (default),
        the expected magnitude is round(4.00 × 0.25) = round(1.00) = 1.
        The CASTER aggressor means the tilt is positive: +1.
        """
        tech_affinity = AffinityFactory()
        npc_affinity = AffinityFactory()
        technique = self._make_technique_with_affinity(tech_affinity)
        AffinityInteractionFactory(
            source_affinity=tech_affinity,
            environment_affinity=npc_affinity,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.CASTER,
            severity_multiplier=Decimal("4.00"),
        )
        AffinityInteraction.objects.clear_cache()
        # Default affinity_tilt_coefficient on ClashConfig is 0.25.
        # round(Decimal("4.00") * Decimal("0.25")) == round(Decimal("1.00")) == 1
        result = affinity_tilt(
            contributor_technique=technique,
            npc_attack_affinity=npc_affinity,
            config=self.config,
        )
        self.assertEqual(result, 1)
        self.assertIsInstance(result, int)

    def test_no_technique_affinity_returns_zero(self) -> None:
        """Technique gift has no resonances → tech_affinity=None → 0."""
        npc_affinity = AffinityFactory()
        gift = GiftFactory()  # no resonances added
        technique = TechniqueFactory(gift=gift)
        result = affinity_tilt(
            contributor_technique=technique,
            npc_attack_affinity=npc_affinity,
            config=self.config,
        )
        self.assertEqual(result, 0)
        self.assertIsInstance(result, int)
