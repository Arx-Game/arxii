"""Tests for npc_round_contribution, affinity_tilt, and aggregate_clash_round."""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.clash import affinity_tilt, aggregate_clash_round, npc_round_contribution
from world.combat.constants import ClashActionSlot, ClashFlavor, LockPcRole
from world.combat.factories import (
    BreakClashFactory,
    ClashConfigFactory,
    ClashFactory,
    LockClashFactory,
    ThreatPoolEntryFactory,
    WardClashFactory,
)
from world.combat.models import ClashContribution, ClashRound
from world.combat.types import ClashContributionResult
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
from world.traits.factories import CheckOutcomeFactory


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


class AggregateClashRoundTests(TestCase):
    """Unit tests for aggregate_clash_round — one test per flavor branch and audit invariant."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.check_outcome = CheckOutcomeFactory(name="aggr_success", success_level=1)
        cls.technique = TechniqueFactory()
        cls.character_a = CharacterSheetFactory()
        cls.character_b = CharacterSheetFactory()

    def _make_contribution(
        self,
        *,
        character: object = None,
        progress_delta: int = 1,
        action_slot: str = ClashActionSlot.FOCUSED,
    ) -> ClashContributionResult:
        """Construct a ClashContributionResult directly (no magic pipeline needed)."""
        from unittest.mock import MagicMock

        return ClashContributionResult(
            character=character if character is not None else self.character_a,
            action_slot=action_slot,
            technique=self.technique,
            check_outcome=self.check_outcome,
            progress_delta=progress_delta,
            anima_committed=5,
            was_overburn=False,
            was_audere=False,
            soulfray_severity_accrued=0,
            technique_use_result=MagicMock(),
        )

    # -------------------------------------------------------------------------
    # Sign-convention tests (one per flavor / sub-case)
    # -------------------------------------------------------------------------

    def test_clash_meter_pc_pushes_positive_npc_negative(self) -> None:
        """CLASH: progress_after = clash.progress + pc_delta_sum - npc_delta."""
        clash = ClashFactory(progress=10)
        contributions = [self._make_contribution(progress_delta=5)]
        result = aggregate_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=contributions,
            npc_delta=3,
        )
        # 10 + 5 - 3 = 12
        self.assertEqual(result.progress_after, 12)
        self.assertEqual(result.pc_delta_sum, 5)
        self.assertEqual(result.npc_delta, 3)

    def test_lock_sustaining_pc_pushes_up_npc_down(self) -> None:
        """LOCK/SUSTAINING: progress_after = clash.progress + pc_delta_sum - npc_delta."""
        clash = LockClashFactory(lock_pc_role=LockPcRole.SUSTAINING, progress=0)
        contributions = [self._make_contribution(progress_delta=4)]
        result = aggregate_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=contributions,
            npc_delta=1,
        )
        # 0 + 4 - 1 = 3
        self.assertEqual(result.progress_after, 3)

    def test_lock_escaping_pc_pushes_down_npc_up(self) -> None:
        """LOCK/ESCAPING: progress_after = clash.progress - pc_delta_sum + npc_delta."""
        clash = LockClashFactory(lock_pc_role=LockPcRole.ESCAPING, progress=10)
        contributions = [self._make_contribution(progress_delta=4)]
        result = aggregate_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=contributions,
            npc_delta=1,
        )
        # 10 - 4 + 1 = 7
        self.assertEqual(result.progress_after, 7)

    def test_ward_pc_strengthens_npc_drains(self) -> None:
        """WARD: progress_after = clash.progress + pc_delta_sum - npc_delta."""
        clash = WardClashFactory(progress=5)
        contributions = [self._make_contribution(progress_delta=2)]
        result = aggregate_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=contributions,
            npc_delta=3,
        )
        # 5 + 2 - 3 = 4
        self.assertEqual(result.progress_after, 4)

    def test_break_npc_delta_is_zero(self) -> None:
        """BREAK: npc_delta is always 0; progress_after = clash.progress + pc_delta_sum."""
        clash = BreakClashFactory(progress=0)
        contributions = [self._make_contribution(progress_delta=3)]
        result = aggregate_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=contributions,
            npc_delta=0,
        )
        # 0 + 3 - 0 = 3
        self.assertEqual(result.progress_after, 3)

    # -------------------------------------------------------------------------
    # DB write and audit invariants
    # -------------------------------------------------------------------------

    def test_writes_clash_round_and_contributions(self) -> None:
        """2 PC contributions → 1 ClashRound row and 2 ClashContribution rows."""
        clash = ClashFactory(progress=0)
        contributions = [
            self._make_contribution(character=self.character_a, progress_delta=3),
            self._make_contribution(character=self.character_b, progress_delta=2),
        ]
        result = aggregate_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=contributions,
            npc_delta=1,
        )

        # One ClashRound row.
        self.assertIsNotNone(result.clash_round.pk)
        db_round = ClashRound.objects.get(pk=result.clash_round.pk)
        self.assertEqual(db_round.clash_id, clash.pk)
        self.assertEqual(db_round.round_number, 1)
        self.assertEqual(db_round.pc_progress_delta, 5)  # 3 + 2
        self.assertEqual(db_round.npc_progress_delta, 1)
        self.assertEqual(db_round.progress_after, 4)  # 0 + 5 - 1

        # Two ClashContribution rows.
        self.assertEqual(len(result.contributions), 2)
        db_count = ClashContribution.objects.filter(clash_round=result.clash_round).count()
        self.assertEqual(db_count, 2)

        # Spot-check the first contribution row.
        contrib = ClashContribution.objects.get(
            clash_round=result.clash_round,
            character=self.character_a,
        )
        self.assertEqual(contrib.progress_delta, 3)
        self.assertEqual(contrib.action_slot, ClashActionSlot.FOCUSED)
        self.assertEqual(contrib.anima_committed, 5)
        self.assertFalse(contrib.was_overburn)
        self.assertFalse(contrib.was_audere)
        self.assertEqual(contrib.soulfray_severity_accrued, 0)

    def test_clash_progress_persists(self) -> None:
        """After aggregation, clash.refresh_from_db() reflects the updated progress."""
        clash = ClashFactory(progress=0)
        contributions = [self._make_contribution(progress_delta=7)]
        aggregate_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=contributions,
            npc_delta=2,
        )
        clash.refresh_from_db()
        self.assertEqual(clash.progress, 5)  # 0 + 7 - 2

    def test_empty_contributions_only_npc_moves_meter(self) -> None:
        """Empty PC contributions, npc_delta=5, CLASH → progress_after = clash.progress - 5."""
        clash = ClashFactory(progress=10)
        result = aggregate_clash_round(
            clash=clash,
            round_number=1,
            pc_contributions=[],
            npc_delta=5,
        )
        # 10 + 0 - 5 = 5
        self.assertEqual(result.progress_after, 5)
        self.assertEqual(result.pc_delta_sum, 0)

        # One ClashRound row written.
        self.assertTrue(ClashRound.objects.filter(pk=result.clash_round.pk).exists())

        # Zero ClashContribution rows.
        db_count = ClashContribution.objects.filter(clash_round=result.clash_round).count()
        self.assertEqual(db_count, 0)
        self.assertEqual(len(result.contributions), 0)
