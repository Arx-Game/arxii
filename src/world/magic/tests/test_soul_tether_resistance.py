"""Tests for CORRUPTION_RESISTANCE effect resolution (Spec B §10, Phase 9).

Tests cover:
    9.1  No Thread → no resistance (lifetime_helped accumulates but is dormant)
    9.2  Sineater Thread woven + lifetime_helped → accrual reduced by formula
    9.3  Per-resonance independence (Abyssal lifetime_helped doesn't reduce Primal accrual)
    9.4  Redirect path NOT affected by resistance (overflow is not the Sineater's own cast)
    9.5  resolve_pull_effects: CORRUPTION_RESISTANCE rows produce scaled_value=None (not 0)
"""

from __future__ import annotations

import math

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import SoulTetherRole, TargetKind
from world.magic.factories import (
    AffinityFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    wire_soul_tether_content,
)
from world.magic.models import Thread
from world.magic.models.aura import CharacterResonance
from world.magic.services.corruption import (
    _CORRUPTION_RESISTANCE_THRESHOLD,
    _apply_sineater_corruption_resistance,
    accrue_corruption,
)
from world.magic.services.resonance import resolve_pull_effects
from world.magic.types.corruption import CorruptionSource
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipCapstoneFactory,
    RelationshipTrackFactory,
)


def _make_sineater_thread_for(
    sineater_sheet: object,
    resonance: object,
    *,
    lifetime_helped: int = 500,
) -> tuple[object, Thread]:
    """Set up a Sineater-side RELATIONSHIP_CAPSTONE Thread for *sineater_sheet*.

    Creates:
    - Two bidirectional CharacterRelationship rows (Sineater→Sinner, Sinner→Sineater)
      flagged as is_soul_tether=True with correct roles.
    - A RelationshipCapstone on the Sineater→Sinner relationship.
    - A RELATIONSHIP_CAPSTONE Thread owned by the sineater_sheet.
    - A CharacterResonance row with lifetime_helped set to *lifetime_helped*.

    Returns:
        (CharacterResonance, Thread) — the resonance row and the created Thread.
    """
    sinner_sheet = CharacterSheetFactory()
    track = RelationshipTrackFactory()

    # Create both directional relationship rows (Sineater→Sinner, Sinner→Sineater).
    rel_sineater_to_sinner = CharacterRelationshipFactory(
        source=sineater_sheet,
        target=sinner_sheet,
        is_pending=False,
        is_soul_tether=True,
        soul_tether_role=SoulTetherRole.SINEATER,
    )
    CharacterRelationshipFactory(
        source=sinner_sheet,
        target=sineater_sheet,
        is_pending=False,
        is_soul_tether=True,
        soul_tether_role=SoulTetherRole.ABYSSAL,
    )

    capstone = RelationshipCapstoneFactory(
        relationship=rel_sineater_to_sinner,
        author=sineater_sheet,
        track=track,
    )

    # Create directly to avoid the factory defaulting to TRAIT kind + target_trait.
    thread = Thread.objects.create(
        owner=sineater_sheet,
        resonance=resonance,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        target_capstone=capstone,
        name="Sineater Thread (test)",
    )

    cr, _ = CharacterResonance.objects.get_or_create(
        character_sheet=sineater_sheet,
        resonance=resonance,
    )
    cr.lifetime_helped = lifetime_helped
    cr.save(update_fields=["lifetime_helped"])

    return cr, thread


# ---------------------------------------------------------------------------
# 9.1  No Thread → no resistance (lifetime_helped dormant)
# ---------------------------------------------------------------------------


class CorruptionResistanceGatingTests(TestCase):
    """9.1: Without a Sineater Thread, lifetime_helped accumulates but resistance doesn't apply.

    Spec B §10.2 — resistance is gated on owning an active RELATIONSHIP_CAPSTONE
    Thread where the relationship has soul_tether_role=SINEATER for the owner's side.
    If no such Thread exists, accrual is unreduced regardless of lifetime_helped.
    """

    def setUp(self) -> None:
        wire_soul_tether_content()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        self.sineater = CharacterSheetFactory()

    def test_no_thread_no_resistance_full_amount_accrues(self) -> None:
        """No active Sineater Thread → full amount accrues, even with large lifetime_helped."""
        # Seed a high lifetime_helped counter without a matching Thread.
        cr = CharacterResonanceFactory(
            character_sheet=self.sineater,
            resonance=self.resonance,
            lifetime_helped=500,
        )

        result = accrue_corruption(
            character_sheet=self.sineater,
            resonance=self.resonance,
            amount=10,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        # Full 10 must have accrued — no thread, no resistance.
        cr.refresh_from_db()
        self.assertEqual(result.amount_applied, 10)
        self.assertEqual(cr.corruption_current, 10)

    def test_no_thread_helper_returns_amount_unchanged(self) -> None:
        """_apply_sineater_corruption_resistance returns amount unchanged with no thread."""
        # Ensure a high lifetime_helped but NO thread.
        CharacterResonanceFactory(
            character_sheet=self.sineater,
            resonance=self.resonance,
            lifetime_helped=999,
        )

        result = _apply_sineater_corruption_resistance(
            self.sineater, self.resonance, 20, redirect_origin=None
        )
        self.assertEqual(result, 20)

    def test_zero_lifetime_helped_no_reduction(self) -> None:
        """Even with a Sineater Thread, zero lifetime_helped means no reduction."""
        _cr, _thread = _make_sineater_thread_for(self.sineater, self.resonance, lifetime_helped=0)

        result = _apply_sineater_corruption_resistance(
            self.sineater, self.resonance, 10, redirect_origin=None
        )
        # lifetime_helped == 0 → multiplier would be 1.0 → no reduction
        self.assertEqual(result, 10)


# ---------------------------------------------------------------------------
# 9.2  Sineater Thread woven + lifetime_helped → accrual reduced by formula
# ---------------------------------------------------------------------------


class CorruptionResistanceAppliedTests(TestCase):
    """9.2: Sineater with Thread + lifetime_helped receives reduced corruption accrual.

    The multiplier formula is: max(0.1, 1.0 - lifetime_helped / threshold).
    This tests both the helper directly and via accrue_corruption.
    """

    def setUp(self) -> None:
        wire_soul_tether_content()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        self.sineater = CharacterSheetFactory()

    def test_thread_and_lifetime_helped_reduces_accrual(self) -> None:
        """With Sineater Thread + lifetime_helped=500, corruption should be halved."""
        _make_sineater_thread_for(self.sineater, self.resonance, lifetime_helped=500)

        # At threshold=1000, lifetime_helped=500 → multiplier = max(0.1, 0.5) = 0.5
        # ceil(10 * 0.5) = 5
        expected = math.ceil(10 * max(0.1, 1.0 - 500 / _CORRUPTION_RESISTANCE_THRESHOLD))

        result = _apply_sineater_corruption_resistance(
            self.sineater, self.resonance, 10, redirect_origin=None
        )
        self.assertEqual(result, expected)
        self.assertLess(result, 10)

    def test_accrual_reduced_via_accrue_corruption(self) -> None:
        """End-to-end: accrue_corruption applies resistance when Thread + lifetime_helped set."""
        cr, _thread = _make_sineater_thread_for(self.sineater, self.resonance, lifetime_helped=500)
        # Reset corruption_current to zero for a clean measurement.
        cr.corruption_current = 0
        cr.save(update_fields=["corruption_current"])

        result = accrue_corruption(
            character_sheet=self.sineater,
            resonance=self.resonance,
            amount=10,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        expected = math.ceil(10 * max(0.1, 1.0 - 500 / _CORRUPTION_RESISTANCE_THRESHOLD))
        self.assertEqual(result.amount_applied, expected)
        cr.refresh_from_db()
        self.assertEqual(cr.corruption_current, expected)

    def test_resistance_capped_at_90_percent(self) -> None:
        """Resistance caps at 90%: floor of 0.1 means at most ceil(amount * 0.1) accrues."""
        # lifetime_helped >> threshold pushes multiplier below 0.1 → floor at 0.1
        _make_sineater_thread_for(
            self.sineater, self.resonance, lifetime_helped=_CORRUPTION_RESISTANCE_THRESHOLD * 10
        )

        result = _apply_sineater_corruption_resistance(
            self.sineater, self.resonance, 100, redirect_origin=None
        )
        # max(0.1, 1 - 10000/1000) = max(0.1, -9.0) = 0.1 → ceil(100 * 0.1) = 10
        self.assertEqual(result, math.ceil(100 * 0.1))
        self.assertGreaterEqual(result, 1)

    def test_formula_ceil_rounds_up(self) -> None:
        """math.ceil ensures we always accrue at least 1 unit when multiplier > 0."""
        # lifetime_helped=500, amount=1 → ceil(1 * 0.5) = 1 (no rounding needed)
        _make_sineater_thread_for(self.sineater, self.resonance, lifetime_helped=500)

        result = _apply_sineater_corruption_resistance(
            self.sineater, self.resonance, 1, redirect_origin=None
        )
        self.assertGreaterEqual(result, 1)


# ---------------------------------------------------------------------------
# 9.3  Per-resonance independence
# ---------------------------------------------------------------------------


class CorruptionResistancePerResonanceTests(TestCase):
    """9.3: Sineater resistance is per-resonance — Abyssal lifetime_helped doesn't reduce Primal.

    The Sineater's Thread and lifetime_helped are keyed on a specific resonance.
    Accruing in a DIFFERENT resonance should see no reduction.
    """

    def setUp(self) -> None:
        wire_soul_tether_content()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        primal_affinity = AffinityFactory(name="Primal")
        self.abyssal_resonance = ResonanceFactory(affinity=abyssal_affinity)
        self.primal_resonance = ResonanceFactory(affinity=primal_affinity)
        self.sineater = CharacterSheetFactory()

    def test_abyssal_thread_does_not_reduce_primal_accrual(self) -> None:
        """Sineater Thread in Abyssal resonance gives no resistance to Primal accrual."""
        # Set up a Sineater Thread for Abyssal with high lifetime_helped.
        _make_sineater_thread_for(self.sineater, self.abyssal_resonance, lifetime_helped=500)

        # Accrue Primal corruption — should NOT be reduced.
        result = _apply_sineater_corruption_resistance(
            self.sineater, self.primal_resonance, 10, redirect_origin=None
        )
        self.assertEqual(result, 10)

    def test_primal_thread_does_not_reduce_abyssal_accrual(self) -> None:
        """Sineater Thread in Primal resonance gives no resistance to Abyssal accrual."""
        _make_sineater_thread_for(self.sineater, self.primal_resonance, lifetime_helped=500)

        result = _apply_sineater_corruption_resistance(
            self.sineater, self.abyssal_resonance, 10, redirect_origin=None
        )
        self.assertEqual(result, 10)

    def test_matching_resonance_thread_reduces_matching_accrual(self) -> None:
        """Resistance applies only to the matching resonance."""
        _make_sineater_thread_for(self.sineater, self.abyssal_resonance, lifetime_helped=500)

        abyssal_result = _apply_sineater_corruption_resistance(
            self.sineater, self.abyssal_resonance, 10, redirect_origin=None
        )
        primal_result = _apply_sineater_corruption_resistance(
            self.sineater, self.primal_resonance, 10, redirect_origin=None
        )

        # Abyssal is reduced; Primal is not.
        self.assertLess(abyssal_result, 10)
        self.assertEqual(primal_result, 10)


# ---------------------------------------------------------------------------
# 9.4  Redirect path NOT affected by resistance
# ---------------------------------------------------------------------------


class CorruptionResistanceRedirectGuardTests(TestCase):
    """9.4: When redirect_origin is set, the resistance helper skips without reducing.

    Spec B §10.2: resistance is for the Sineater's OWN casts only.
    Overflow accrual (redirect_origin is not None) is NOT the character's own cast;
    it comes from absorbing a Sinner's corruption via the Soul Tether.
    """

    def setUp(self) -> None:
        wire_soul_tether_content()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        self.sineater = CharacterSheetFactory()

    def test_redirect_origin_bypasses_resistance(self) -> None:
        """Helper returns amount unchanged when redirect_origin is set."""
        _make_sineater_thread_for(self.sineater, self.resonance, lifetime_helped=999)

        # Simulate overflow accrual: pass a fake redirect_origin sheet.
        sinner = CharacterSheetFactory()
        result = _apply_sineater_corruption_resistance(
            self.sineater, self.resonance, 10, redirect_origin=sinner
        )
        self.assertEqual(result, 10)

    def test_no_redirect_origin_applies_resistance(self) -> None:
        """Same setup, no redirect_origin → resistance IS applied (confirms gate works)."""
        _make_sineater_thread_for(self.sineater, self.resonance, lifetime_helped=500)

        result = _apply_sineater_corruption_resistance(
            self.sineater, self.resonance, 10, redirect_origin=None
        )
        self.assertLess(result, 10)

    def test_retired_thread_not_counted(self) -> None:
        """A retired (soft-deleted) Sineater Thread does not grant resistance."""
        _cr, thread = _make_sineater_thread_for(self.sineater, self.resonance, lifetime_helped=500)
        # Soft-retire the thread.
        from django.utils import timezone

        thread.retired_at = timezone.now()
        thread.save(update_fields=["retired_at"])

        result = _apply_sineater_corruption_resistance(
            self.sineater, self.resonance, 10, redirect_origin=None
        )
        # Retired thread → no active Sineater Thread → no resistance.
        self.assertEqual(result, 10)


# ---------------------------------------------------------------------------
# 9.5  resolve_pull_effects: CORRUPTION_RESISTANCE rows have scaled_value=None
# ---------------------------------------------------------------------------


class ResolveCorruptionResistancePullEffectTests(TestCase):
    """9.5: CORRUPTION_RESISTANCE rows in resolve_pull_effects produce scaled_value=None.

    The runtime value derives from lifetime_helped (applied in accrue_corruption),
    not from a payload column.  resolve_pull_effects must NOT compute a numeric
    scaled_value for these rows — it should be None (matching CAPABILITY_GRANT /
    NARRATIVE_ONLY behavior per the CheckConstraint).
    """

    def setUp(self) -> None:
        wire_soul_tether_content()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        self.sineater = CharacterSheetFactory()

    def test_corruption_resistance_row_resolves_with_null_scaled_value(self) -> None:
        """CORRUPTION_RESISTANCE ThreadPullEffect rows resolve with scaled_value=None."""
        from world.magic.constants import EffectKind
        from world.magic.models import ThreadPullEffect

        track = RelationshipTrackFactory()
        sinner_sheet = CharacterSheetFactory()

        rel_sineater_to_sinner = CharacterRelationshipFactory(
            source=self.sineater,
            target=sinner_sheet,
            is_pending=False,
            is_soul_tether=True,
            soul_tether_role=SoulTetherRole.SINEATER,
        )
        capstone = RelationshipCapstoneFactory(
            relationship=rel_sineater_to_sinner,
            author=self.sineater,
            track=track,
        )

        # Create directly to avoid the factory defaulting to TRAIT kind + target_trait.
        thread = Thread.objects.create(
            owner=self.sineater,
            resonance=self.resonance,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=capstone,
            name="Sineater Thread (test 9.5)",
            level=10,
        )

        # Author a tier-0 CORRUPTION_RESISTANCE pull effect (all payload cols null).
        effect_row = ThreadPullEffect.objects.create(
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=self.resonance,
            tier=0,
            min_thread_level=1,
            effect_kind=EffectKind.CORRUPTION_RESISTANCE,
            # All payload columns intentionally null (CheckConstraint requires it).
            flat_bonus_amount=None,
            intensity_bump_amount=None,
            vital_bonus_amount=None,
            vital_target=None,
            capability_grant=None,
            narrative_snippet="",
        )

        resolved = resolve_pull_effects([thread], tier=0, in_combat=False)

        corruption_resistance_effects = [
            e for e in resolved if e.kind == EffectKind.CORRUPTION_RESISTANCE
        ]
        self.assertEqual(len(corruption_resistance_effects), 1)
        effect = corruption_resistance_effects[0]
        # scaled_value must be None, not 0 — the runtime value comes from lifetime_helped.
        self.assertIsNone(effect.scaled_value)
        self.assertIsNone(effect.authored_value)
        # Clean up the authored row so it doesn't bleed into other tests.
        effect_row.delete()
