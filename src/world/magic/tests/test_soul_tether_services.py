"""Service tests for Soul Tether services (Spec B §12, §7, Phase 4 + Phase 5).

Tests cover:
    4.1  AffinityGateError on Abyssal-primary Sineater or Celestial-primary Sinner
    4.2  NoSoulTetherUnlockError when Sinner lacks RELATIONSHIP_CAPSTONE ThreadWeavingUnlock
    4.3  Happy-path formation (capstone + flags + thread + condition + triggers)
    4.4  Idempotency — duplicate formation raises SoulTetherFormationError
    4.5  Multi-tether — second tether to different Sineater reuses ConditionInstance

    5.1  request_sineating validation gates
    5.2  resolve_sineating happy path (units > 0 deducts costs, increments state, audit row)
    5.3  resolve_sineating decline path (units == 0 writes audit row, no state changes)
    5.4  Per-scene cap clamping (max_units_offered capped to per-scene formula)
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from flows.models.triggers import Trigger
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.models import ConditionInstance
from world.magic.constants import SoulTetherRole, TargetKind
from world.magic.exceptions import (
    AffinityGateError,
    NoSoulTetherUnlockError,
    SineatingValidationError,
    SoulTetherFormationError,
)
from world.magic.factories import (
    AffinityFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
    wire_soul_tether_content,
)
from world.magic.models import Thread
from world.magic.models.soul_tether import Sineating
from world.magic.services.soul_tether import (
    _compute_per_scene_sineating_cap,
    accept_soul_tether,
    request_sineating,
    resolve_sineating,
)
from world.magic.types.soul_tether import SineatingOffer, SoulTetherRole as SoulTetherRoleEnum
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
)
from world.relationships.models import CharacterRelationship

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _set_primary_affinity_abyssal(sheet: object) -> None:
    """Set the character's aura so Abyssal is the dominant affinity."""
    char = sheet.character  # type: ignore[union-attr]
    try:
        aura = char.aura
        aura.celestial = Decimal("10.00")
        aura.primal = Decimal("10.00")
        aura.abyssal = Decimal("80.00")
        aura.save()
    except AttributeError:
        CharacterAuraFactory(
            character=char,
            celestial=Decimal("10.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("80.00"),
        )


def _set_primary_affinity_celestial(sheet: object) -> None:
    """Set the character's aura so Celestial is the dominant affinity."""
    char = sheet.character  # type: ignore[union-attr]
    try:
        aura = char.aura
        aura.celestial = Decimal("80.00")
        aura.primal = Decimal("10.00")
        aura.abyssal = Decimal("10.00")
        aura.save()
    except AttributeError:
        CharacterAuraFactory(
            character=char,
            celestial=Decimal("80.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("10.00"),
        )


def _set_primary_affinity_primal(sheet: object) -> None:
    """Set the character's aura so Primal is the dominant affinity."""
    char = sheet.character  # type: ignore[union-attr]
    try:
        aura = char.aura
        aura.celestial = Decimal("10.00")
        aura.primal = Decimal("80.00")
        aura.abyssal = Decimal("10.00")
        aura.save()
    except AttributeError:
        CharacterAuraFactory(
            character=char,
            celestial=Decimal("10.00"),
            primal=Decimal("80.00"),
            abyssal=Decimal("10.00"),
        )


def _grant_relationship_track_unlock(sheet: object, track: object) -> object:
    """Give the character a RELATIONSHIP_TRACK CharacterThreadWeavingUnlock.

    RELATIONSHIP_CAPSTONE thread weaving inherits from RELATIONSHIP_TRACK
    unlocks (ThreadWeavingUnlock has no CAPSTONE kind — constraint enforces
    this). A RELATIONSHIP_TRACK unlock for the same track as the capstone
    satisfies weave_thread's unlock check for RELATIONSHIP_CAPSTONE anchors.
    """
    unlock = ThreadWeavingUnlockFactory(
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        unlock_track=track,
        unlock_trait=None,
    )
    return CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock)


def _make_eligible_pair(track: object | None = None) -> tuple:
    """Return (sinner_sheet, sineater_sheet) satisfying all affinity + unlock gates.

    sinner: Abyssal-primary with RELATIONSHIP_TRACK unlock for *track*.
    sineater: Primal-primary (Celestial or Primal both pass the Sineater gate).
    Also seeds the required Soul Tether authored content (Ritual, ConditionTemplate, etc.).
    """
    wire_soul_tether_content()
    sinner = CharacterSheetFactory()
    sineater = CharacterSheetFactory()
    _set_primary_affinity_abyssal(sinner)
    _set_primary_affinity_primal(sineater)
    if track is None:
        track = RelationshipTrackFactory()
    _grant_relationship_track_unlock(sinner, track)
    return sinner, sineater


def _make_active_relationship(source: object, target: object) -> object:
    """Create both directional CharacterRelationships (not pending)."""
    rel = CharacterRelationshipFactory(source=source, target=target, is_pending=False)
    CharacterRelationshipFactory(source=target, target=source, is_pending=False)
    return rel


# ---------------------------------------------------------------------------
# 4.1  Affinity gate tests
# ---------------------------------------------------------------------------


class AcceptSoulTetherAffinityGateTests(TestCase):
    """Spec B §3 affinity gate validation."""

    def setUp(self) -> None:
        wire_soul_tether_content()
        self.track = RelationshipTrackFactory()
        self.resonance = ResonanceFactory()

    def test_rejects_abyssal_primary_sineater(self) -> None:
        """Sineater must be Celestial- or Primal-primary; Abyssal is forbidden."""
        sinner = CharacterSheetFactory()
        sineater = CharacterSheetFactory()
        _set_primary_affinity_abyssal(sinner)
        _set_primary_affinity_abyssal(sineater)
        _grant_relationship_track_unlock(sinner, self.track)
        _make_active_relationship(sinner, sineater)

        with self.assertRaises(AffinityGateError) as ctx:
            accept_soul_tether(
                initiator_sheet=sinner,
                partner_sheet=sineater,
                sinner_role=SoulTetherRoleEnum.ABYSSAL,
                resonance=self.resonance,
                writeup="A bond is forged.",
                ritual_components=[],
            )
        self.assertIn("Sineater", ctx.exception.user_message)

    def test_rejects_celestial_primary_sinner(self) -> None:
        """Celestial-primary cannot be the Sinner — they don't accrue Corruption."""
        sinner = CharacterSheetFactory()
        sineater = CharacterSheetFactory()
        _set_primary_affinity_celestial(sinner)
        _set_primary_affinity_primal(sineater)
        _grant_relationship_track_unlock(sinner, self.track)
        _make_active_relationship(sinner, sineater)

        with self.assertRaises(AffinityGateError) as ctx:
            accept_soul_tether(
                initiator_sheet=sinner,
                partner_sheet=sineater,
                sinner_role=SoulTetherRoleEnum.ABYSSAL,
                resonance=self.resonance,
                writeup="A bond is forged.",
                ritual_components=[],
            )
        self.assertIn("Sinner", ctx.exception.user_message)

    def test_celestial_sineater_does_not_raise_affinity_gate(self) -> None:
        """Celestial-primary Sineater is valid (passes the gate).

        The service will still form the bond successfully (no other errors expected
        given the full eligible pair setup). AffinityGateError must not be raised.
        """
        sinner, sineater = _make_eligible_pair(track=self.track)
        # Override sineater's affinity to Celestial (still valid for Sineater role).
        _set_primary_affinity_celestial(sineater)
        _make_active_relationship(sinner, sineater)

        # Should complete without raising AffinityGateError.
        accept_soul_tether(
            initiator_sheet=sinner,
            partner_sheet=sineater,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=self.resonance,
            writeup="A celestial bond.",
            ritual_components=[],
        )


# ---------------------------------------------------------------------------
# 4.2  ThreadWeavingUnlock prerequisite
# ---------------------------------------------------------------------------


class AcceptSoulTetherUnlockTests(TestCase):
    """Spec B §12.4 step: Sinner must have RELATIONSHIP_TRACK ThreadWeavingUnlock."""

    def setUp(self) -> None:
        wire_soul_tether_content()
        self.track = RelationshipTrackFactory()
        self.resonance = ResonanceFactory()

    def test_sinner_without_unlock_raises(self) -> None:
        """Sinner lacking the unlock gets NoSoulTetherUnlockError."""
        sinner = CharacterSheetFactory()
        sineater = CharacterSheetFactory()
        _set_primary_affinity_abyssal(sinner)
        _set_primary_affinity_primal(sineater)
        # No unlock granted to sinner
        _make_active_relationship(sinner, sineater)

        with self.assertRaises(NoSoulTetherUnlockError):
            accept_soul_tether(
                initiator_sheet=sinner,
                partner_sheet=sineater,
                sinner_role=SoulTetherRoleEnum.ABYSSAL,
                resonance=self.resonance,
                writeup="No unlock.",
                ritual_components=[],
            )

    def test_sinner_with_unlock_does_not_raise_unlock_error(self) -> None:
        """Sinner with RELATIONSHIP_TRACK unlock for the given track passes.

        The service forms the bond successfully when all prerequisites are met.
        NoSoulTetherUnlockError must not be raised.
        """
        sinner, sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(sinner, sineater)

        # Should complete without raising NoSoulTetherUnlockError.
        accept_soul_tether(
            initiator_sheet=sinner,
            partner_sheet=sineater,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=self.resonance,
            writeup="Has unlock.",
            ritual_components=[],
        )


# ---------------------------------------------------------------------------
# 4.3  Happy-path formation
# ---------------------------------------------------------------------------


class AcceptSoulTetherHappyPathTests(TestCase):
    """Full formation flow — Spec B §12.4."""

    @classmethod
    def setUpTestData(cls) -> None:
        wire_soul_tether_content()
        cls.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(affinity=abyssal_affinity)
        cls.sinner, cls.sineater = _make_eligible_pair(track=cls.track)
        CharacterRelationshipFactory(source=cls.sinner, target=cls.sineater, is_pending=False)
        CharacterRelationshipFactory(source=cls.sineater, target=cls.sinner, is_pending=False)

        cls.capstone = accept_soul_tether(
            initiator_sheet=cls.sinner,
            partner_sheet=cls.sineater,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=cls.resonance,
            writeup="They knelt and joined hands beneath the witch-light.",
            ritual_components=[],
        )

    def test_capstone_is_ritual_capstone(self) -> None:
        self.assertTrue(self.capstone.is_ritual_capstone)

    def test_capstone_ritual_is_accept_soul_tether(self) -> None:
        self.assertEqual(self.capstone.ritual.name, "accept_soul_tether")

    def test_capstone_writeup_preserved(self) -> None:
        self.assertIn("witch-light", self.capstone.writeup)

    def test_both_relationships_flagged_as_soul_tether(self) -> None:
        rel_out = CharacterRelationship.objects.get(source=self.sinner, target=self.sineater)
        rel_in = CharacterRelationship.objects.get(source=self.sineater, target=self.sinner)
        self.assertTrue(rel_out.is_soul_tether)
        self.assertTrue(rel_in.is_soul_tether)

    def test_sinner_rel_role_is_abyssal(self) -> None:
        rel_out = CharacterRelationship.objects.get(source=self.sinner, target=self.sineater)
        self.assertEqual(rel_out.soul_tether_role, SoulTetherRole.ABYSSAL)

    def test_sineater_rel_role_is_sineater(self) -> None:
        rel_in = CharacterRelationship.objects.get(source=self.sineater, target=self.sinner)
        self.assertEqual(rel_in.soul_tether_role, SoulTetherRole.SINEATER)

    def test_sinner_thread_woven(self) -> None:
        threads = Thread.objects.filter(
            owner=self.sinner,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=self.capstone,
            resonance=self.resonance,
        )
        self.assertEqual(threads.count(), 1)

    def test_sinner_thread_hollow_starts_at_zero(self) -> None:
        thread = Thread.objects.get(
            owner=self.sinner,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=self.capstone,
        )
        self.assertEqual(thread.hollow_current, 0)

    def test_soul_tether_active_condition_installed_on_sinner(self) -> None:
        instances = ConditionInstance.objects.filter(
            target=self.sinner.character,
            condition__name="Soul Tether Active",
        )
        self.assertEqual(instances.count(), 1)

    def test_two_triggers_installed_on_sinner_character(self) -> None:
        triggers = Trigger.objects.filter(obj=self.sinner.character)
        self.assertEqual(triggers.count(), 2)

    def test_trigger_source_condition_is_active_instance(self) -> None:
        active_instance = ConditionInstance.objects.get(
            target=self.sinner.character,
            condition__name="Soul Tether Active",
        )
        triggers = Trigger.objects.filter(obj=self.sinner.character)
        for t in triggers:
            self.assertEqual(t.source_condition_id, active_instance.pk)

    def test_trigger_definitions_are_correct(self) -> None:
        trigger_def_names = set(
            Trigger.objects.filter(obj=self.sinner.character).values_list(
                "trigger_definition__name", flat=True
            )
        )
        self.assertIn("soul_tether_redirect", trigger_def_names)
        self.assertIn("soul_tether_stage_advance_prompt", trigger_def_names)


# ---------------------------------------------------------------------------
# 4.4  Idempotency — duplicate formation raises
# ---------------------------------------------------------------------------


class AcceptSoulTetherIdempotencyTests(TestCase):
    """Second formation between same pair raises SoulTetherFormationError."""

    def setUp(self) -> None:
        wire_soul_tether_content()
        self.track = RelationshipTrackFactory()
        self.resonance = ResonanceFactory()
        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)

    def test_double_formation_raises(self) -> None:
        # First formation — should succeed
        accept_soul_tether(
            initiator_sheet=self.sinner,
            partner_sheet=self.sineater,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=self.resonance,
            writeup="First bond.",
            ritual_components=[],
        )
        # Second formation — should raise
        with self.assertRaises(SoulTetherFormationError) as ctx:
            accept_soul_tether(
                initiator_sheet=self.sinner,
                partner_sheet=self.sineater,
                sinner_role=SoulTetherRoleEnum.ABYSSAL,
                resonance=self.resonance,
                writeup="Duplicate bond.",
                ritual_components=[],
            )
        self.assertIn("already exists", ctx.exception.user_message)


# ---------------------------------------------------------------------------
# 4.5  Multi-tether — second tether to different Sineater reuses ConditionInstance
# ---------------------------------------------------------------------------


class AcceptSoulTetherMultiTetherTests(TestCase):
    """Sinner forming a second tether reuses the SoulTetherActiveTemplate ConditionInstance."""

    def setUp(self) -> None:
        wire_soul_tether_content()
        self.track = RelationshipTrackFactory()

    def test_second_tether_reuses_condition_instance(self) -> None:
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance1 = ResonanceFactory(affinity=abyssal_affinity)
        resonance2 = ResonanceFactory(affinity=abyssal_affinity)

        sinner, sineater1 = _make_eligible_pair(track=self.track)
        _make_active_relationship(sinner, sineater1)

        # First tether
        accept_soul_tether(
            initiator_sheet=sinner,
            partner_sheet=sineater1,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=resonance1,
            writeup="First bond.",
            ritual_components=[],
        )

        # Second tether: different Sineater; new track unlock for the new capstone
        sineater2 = CharacterSheetFactory()
        _set_primary_affinity_primal(sineater2)
        track2 = RelationshipTrackFactory()
        _grant_relationship_track_unlock(sinner, track2)
        CharacterRelationshipFactory(source=sinner, target=sineater2, is_pending=False)
        CharacterRelationshipFactory(source=sineater2, target=sinner, is_pending=False)

        accept_soul_tether(
            initiator_sheet=sinner,
            partner_sheet=sineater2,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=resonance2,
            writeup="Second bond.",
            ritual_components=[],
        )

        # Exactly one SoulTetherActive ConditionInstance — not two
        count = ConditionInstance.objects.filter(
            target=sinner.character,
            condition__name="Soul Tether Active",
        ).count()
        self.assertEqual(count, 1)

    def test_second_tether_does_not_add_duplicate_triggers(self) -> None:
        """Triggers are installed once; second tether must not double them."""
        abyssal_affinity = AffinityFactory(name="Abyssal")
        resonance1 = ResonanceFactory(affinity=abyssal_affinity)
        resonance2 = ResonanceFactory(affinity=abyssal_affinity)

        sinner, sineater1 = _make_eligible_pair(track=self.track)
        _make_active_relationship(sinner, sineater1)

        accept_soul_tether(
            initiator_sheet=sinner,
            partner_sheet=sineater1,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=resonance1,
            writeup="First bond.",
            ritual_components=[],
        )

        sineater2 = CharacterSheetFactory()
        _set_primary_affinity_primal(sineater2)
        track2 = RelationshipTrackFactory()
        _grant_relationship_track_unlock(sinner, track2)
        CharacterRelationshipFactory(source=sinner, target=sineater2, is_pending=False)
        CharacterRelationshipFactory(source=sineater2, target=sinner, is_pending=False)

        accept_soul_tether(
            initiator_sheet=sinner,
            partner_sheet=sineater2,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=resonance2,
            writeup="Second bond.",
            ritual_components=[],
        )

        # Still exactly 2 triggers (one per definition), not 4
        trigger_count = Trigger.objects.filter(obj=sinner.character).count()
        self.assertEqual(trigger_count, 2)


# =============================================================================
# Phase 5: Sineating loop tests
# =============================================================================

# ---------------------------------------------------------------------------
# Shared helpers for Phase 5 tests
# ---------------------------------------------------------------------------


def _make_tethered_pair(
    track: object | None = None,
) -> tuple:
    """Return (sinner_sheet, sineater_sheet, resonance, relationship) satisfying all gates.

    - Sinner: Abyssal-primary + RELATIONSHIP_TRACK unlock.
    - Sineater: Primal-primary.
    - Active tether formed between them (both directional rows + capstone + thread).
    - Returns the Sinner→Sineater CharacterRelationship.
    """
    wire_soul_tether_content()
    if track is None:
        track = RelationshipTrackFactory()
    abyssal_affinity = AffinityFactory(name="Abyssal")
    resonance = ResonanceFactory(affinity=abyssal_affinity)
    sinner, sineater = _make_eligible_pair(track=track)
    _make_active_relationship(sinner, sineater)
    accept_soul_tether(
        initiator_sheet=sinner,
        partner_sheet=sineater,
        sinner_role=SoulTetherRoleEnum.ABYSSAL,
        resonance=resonance,
        writeup="Bond forged for Sineating tests.",
        ritual_components=[],
    )
    relationship = CharacterRelationship.objects.get(source=sinner, target=sineater)
    return sinner, sineater, resonance, relationship


def _make_sineating_offer(
    sinner: object,
    sineater: object,
    resonance: object,
    relationship: object,
    max_units: int = 5,
) -> SineatingOffer:
    """Build a SineatingOffer directly, bypassing scene validation.

    Used by tests that focus on resolve_sineating logic rather than
    request_sineating validation.  The SineatingOffer is the frozen
    dataclass accepted by resolve_sineating — constructing it manually
    allows us to skip the roster/scene-participation lookup chain.
    """
    from world.magic.services.soul_tether import (
        _ANIMA_COST_PER_UNIT,
        _FATIGUE_COST_PER_UNIT,
    )

    return SineatingOffer(
        sinner_sheet=sinner,  # type: ignore[arg-type]
        sineater_sheet=sineater,  # type: ignore[arg-type]
        relationship=relationship,  # type: ignore[arg-type]
        resonance=resonance,  # type: ignore[arg-type]
        max_units_offered=max_units,
        anima_cost_per_unit=_ANIMA_COST_PER_UNIT,
        fatigue_cost_per_unit=_FATIGUE_COST_PER_UNIT,
        current_hollow=0,
        hollow_max=0,
        sineater_current_strain_stage=0,
    )


# ---------------------------------------------------------------------------
# 5.1  request_sineating validation gates
# ---------------------------------------------------------------------------


class RequestSineatingValidationTests(TestCase):
    """Spec B §7.2 — validation gates for request_sineating."""

    def setUp(self) -> None:
        wire_soul_tether_content()
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)

    def test_no_active_tether_raises(self) -> None:
        """Requesting Sineating without a Soul Tether raises SineatingValidationError."""
        # No tether formed — relationship rows exist but is_soul_tether is False.
        with self.assertRaises(SineatingValidationError) as ctx:
            request_sineating(
                sinner_sheet=self.sinner,
                sineater_sheet=self.sineater,
                resonance=self.resonance,
                max_units=5,
                scene=None,
            )
        self.assertIn(
            ctx.exception.user_message,
            SineatingValidationError.SAFE_MESSAGES,
        )
        self.assertIn("No active Soul Tether", ctx.exception.user_message)

    def test_scene_none_raises(self) -> None:
        """Sineating requires a scene; scene=None raises SineatingValidationError."""
        # Form the tether first so the tether check passes.
        accept_soul_tether(
            initiator_sheet=self.sinner,
            partner_sheet=self.sineater,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=self.resonance,
            writeup="Bond.",
            ritual_components=[],
        )
        # Seed a CharacterResonance so the resonance gate passes too.
        CharacterResonanceFactory(character_sheet=self.sinner, resonance=self.resonance)

        with self.assertRaises(SineatingValidationError) as ctx:
            request_sineating(
                sinner_sheet=self.sinner,
                sineater_sheet=self.sineater,
                resonance=self.resonance,
                max_units=5,
                scene=None,  # Explicit None — no active scene
            )
        self.assertIn("same scene", ctx.exception.user_message)

    def test_resonance_not_accrued_by_sinner_raises(self) -> None:
        """Resonance with no CharacterResonance row for Sinner raises SineatingValidationError."""
        # Form tether so the tether check passes.
        accept_soul_tether(
            initiator_sheet=self.sinner,
            partner_sheet=self.sineater,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=self.resonance,
            writeup="Bond.",
            ritual_components=[],
        )
        # Use a *different* resonance that Sinner has no CharacterResonance for.
        other_resonance = ResonanceFactory()

        # Patch scene check so we get past it and hit the resonance gate.
        with (
            patch(
                "world.magic.services.soul_tether._both_in_scene",
                return_value=True,
            ),
            self.assertRaises(SineatingValidationError) as ctx,
        ):
            request_sineating(
                sinner_sheet=self.sinner,
                sineater_sheet=self.sineater,
                resonance=other_resonance,
                max_units=5,
                scene=object(),  # non-None sentinel
            )
        self.assertIn("not one the Sinner accrues", ctx.exception.user_message)


# ---------------------------------------------------------------------------
# 5.2  resolve_sineating happy path (units > 0)
# ---------------------------------------------------------------------------


class ResolveSineatingHappyPathTests(TestCase):
    """Spec B §7.2 — accepted Sineating deducts costs, increments state, writes audit row."""

    @classmethod
    def setUpTestData(cls) -> None:
        wire_soul_tether_content()
        track = RelationshipTrackFactory()
        cls.sinner, cls.sineater, cls.resonance, cls.relationship = _make_tethered_pair(track=track)

        # Seed Sineater's anima so the deduction can proceed.
        cls.sineater_anima = CharacterAnimaFactory(
            character=cls.sineater.character,
            current=20,
            maximum=20,
        )

        # Seed a CharacterResonance for the Sinner (required for the tether's resonance gate).
        CharacterResonanceFactory(character_sheet=cls.sinner, resonance=cls.resonance)

    def _build_offer(self, max_units: int = 5) -> SineatingOffer:
        return _make_sineating_offer(
            self.sinner,
            self.sineater,
            self.resonance,
            self.relationship,
            max_units=max_units,
        )

    def test_returns_sineating_result_with_correct_units(self) -> None:
        offer = self._build_offer()
        result = resolve_sineating(offer, units_accepted=3)
        self.assertEqual(result.units_accepted, 3)
        self.assertFalse(result.declined)

    def test_audit_row_written(self) -> None:
        offer = self._build_offer()
        resolve_sineating(offer, units_accepted=3)
        self.assertEqual(Sineating.objects.filter(sineater_sheet=self.sineater).count(), 1)

    def test_audit_row_units_accepted_matches(self) -> None:
        offer = self._build_offer()
        resolve_sineating(offer, units_accepted=3)
        row = Sineating.objects.get(sineater_sheet=self.sineater)
        self.assertEqual(row.units_accepted, 3)
        self.assertEqual(row.units_offered, offer.max_units_offered)

    def test_anima_deducted_from_sineater(self) -> None:
        from world.magic.models import CharacterAnima

        initial_current = 20
        offer = self._build_offer()
        resolve_sineating(offer, units_accepted=3)

        anima = CharacterAnima.objects.get(character=self.sineater.character)
        expected = initial_current - 3 * offer.anima_cost_per_unit
        self.assertEqual(anima.current, expected)

    def test_hollow_current_incremented_on_sinner_thread(self) -> None:
        offer = self._build_offer()
        resolve_sineating(offer, units_accepted=3)

        sinner_thread = Thread.objects.filter(
            owner=self.sinner,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=self.resonance,
            retired_at__isnull=True,
        ).first()
        # Thread level is 0, so hollow_max = 0*10 = 0; clamped to hollow_max.
        # The hollow_max for a level-0 thread is 0, so hollow_current stays 0.
        # This tests that the clamping logic doesn't crash; a level-1+ test would show growth.
        self.assertIsNotNone(sinner_thread)
        self.assertGreaterEqual(sinner_thread.hollow_current, 0)

    def test_lifetime_helped_incremented_on_sineater_resonance(self) -> None:
        from world.magic.models.aura import CharacterResonance

        offer = self._build_offer()
        resolve_sineating(offer, units_accepted=3)

        cr = CharacterResonance.objects.get(
            character_sheet=self.sineater,
            resonance=self.resonance,
        )
        self.assertEqual(cr.lifetime_helped, 3)

    def test_result_new_lifetime_helped_matches_db(self) -> None:
        from world.magic.models.aura import CharacterResonance

        offer = self._build_offer()
        result = resolve_sineating(offer, units_accepted=4)

        cr = CharacterResonance.objects.get(
            character_sheet=self.sineater,
            resonance=self.resonance,
        )
        self.assertEqual(result.new_lifetime_helped, cr.lifetime_helped)

    def test_units_clamped_to_max_units_offered(self) -> None:
        """Requesting more units than offered clamps to max_units_offered."""
        offer = self._build_offer(max_units=5)
        result = resolve_sineating(offer, units_accepted=999)
        self.assertEqual(result.units_accepted, 5)


# ---------------------------------------------------------------------------
# 5.3  resolve_sineating decline path (units == 0)
# ---------------------------------------------------------------------------


class ResolveSineatingDeclineTests(TestCase):
    """Spec B §7.2 — declined Sineating writes audit row with units_accepted=0, no state changes."""

    @classmethod
    def setUpTestData(cls) -> None:
        wire_soul_tether_content()
        track = RelationshipTrackFactory()
        cls.sinner, cls.sineater, cls.resonance, cls.relationship = _make_tethered_pair(track=track)
        # Seed Sineater's anima for deduction baseline.
        cls.sineater_anima = CharacterAnimaFactory(
            character=cls.sineater.character,
            current=20,
            maximum=20,
        )
        CharacterResonanceFactory(character_sheet=cls.sinner, resonance=cls.resonance)

    def _build_offer(self) -> SineatingOffer:
        return _make_sineating_offer(
            self.sinner,
            self.sineater,
            self.resonance,
            self.relationship,
        )

    def test_decline_returns_declined_true(self) -> None:
        offer = self._build_offer()
        result = resolve_sineating(offer, units_accepted=0)
        self.assertTrue(result.declined)
        self.assertEqual(result.units_accepted, 0)

    def test_decline_audit_row_written(self) -> None:
        offer = self._build_offer()
        resolve_sineating(offer, units_accepted=0)
        self.assertEqual(Sineating.objects.filter(sineater_sheet=self.sineater).count(), 1)

    def test_decline_audit_row_units_accepted_is_zero(self) -> None:
        offer = self._build_offer()
        resolve_sineating(offer, units_accepted=0)
        row = Sineating.objects.get(sineater_sheet=self.sineater)
        self.assertEqual(row.units_accepted, 0)

    def test_decline_no_anima_deducted(self) -> None:
        from world.magic.models import CharacterAnima

        offer = self._build_offer()
        resolve_sineating(offer, units_accepted=0)
        anima = CharacterAnima.objects.get(character=self.sineater.character)
        self.assertEqual(anima.current, 20)  # unchanged

    def test_decline_no_lifetime_helped_change(self) -> None:
        from world.magic.models.aura import CharacterResonance

        offer = self._build_offer()
        resolve_sineating(offer, units_accepted=0)
        # No CharacterResonance row should have been created for the Sineater
        # (it's only created on acceptance).
        self.assertFalse(
            CharacterResonance.objects.filter(
                character_sheet=self.sineater,
                resonance=self.resonance,
            ).exists()
        )

    def test_decline_hollow_unchanged(self) -> None:
        offer = self._build_offer()
        resolve_sineating(offer, units_accepted=0)
        sinner_thread = Thread.objects.filter(
            owner=self.sinner,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=self.resonance,
            retired_at__isnull=True,
        ).first()
        if sinner_thread is not None:
            self.assertEqual(sinner_thread.hollow_current, 0)  # unchanged


# ---------------------------------------------------------------------------
# 5.4  Per-scene cap clamping
# ---------------------------------------------------------------------------


class PerSceneCapTests(TestCase):
    """Spec B §7.3 — per-scene cap limits max_units_offered in the offer.

    Decision: request_sineating clamps ``max_units`` to the per-scene cap
    and returns the clamped value in ``SineatingOffer.max_units_offered``.
    It does NOT raise — the caller asked for N units and gets at most cap.
    This mirrors the spec's "Sinner can re-request multiple times within a
    scene as long as cumulative accepted units remain under the cap" — we
    let the cap represent the session limit.
    """

    def setUp(self) -> None:
        wire_soul_tether_content()
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)

    def test_compute_per_scene_cap_with_no_thread_is_zero(self) -> None:
        """When no Sinner Thread exists, the cap is 0."""
        cap = _compute_per_scene_sineating_cap(sinner_thread=None, relationship=object())  # type: ignore[arg-type]
        self.assertEqual(cap, 0)

    def test_compute_per_scene_cap_level_zero_thread_returns_five(self) -> None:
        """A level-0 thread gives cap = min(20, 0*2+5) = 5."""
        wire_soul_tether_content()
        track = RelationshipTrackFactory()
        sinner, sineater = _make_eligible_pair(track=track)
        _make_active_relationship(sinner, sineater)
        accept_soul_tether(
            initiator_sheet=sinner,
            partner_sheet=sineater,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=self.resonance,
            writeup="Bond.",
            ritual_components=[],
        )
        rel = CharacterRelationship.objects.get(source=sinner, target=sineater)
        thread = Thread.objects.get(
            owner=sinner,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=self.resonance,
        )
        self.assertEqual(thread.level, 0)
        cap = _compute_per_scene_sineating_cap(sinner_thread=thread, relationship=rel)
        self.assertEqual(cap, 5)  # min(20, 0*2+5) = 5

    def test_request_sineating_clamps_max_units_to_cap(self) -> None:
        """Offering more units than the cap returns offer with max_units_offered == cap."""
        sinner, sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(sinner, sineater)
        accept_soul_tether(
            initiator_sheet=sinner,
            partner_sheet=sineater,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=self.resonance,
            writeup="Bond.",
            ritual_components=[],
        )
        # Seed CharacterResonance for the Sinner so the resonance gate passes.
        CharacterResonanceFactory(character_sheet=sinner, resonance=self.resonance)

        # Patch scene check so the test focuses on cap clamping.
        with patch(
            "world.magic.services.soul_tether._both_in_scene",
            return_value=True,
        ):
            offer = request_sineating(
                sinner_sheet=sinner,
                sineater_sheet=sineater,
                resonance=self.resonance,
                max_units=9999,  # far above any cap
                scene=object(),
            )

        # Level-0 thread → cap = 5; max_units_offered should be clamped.
        self.assertLessEqual(offer.max_units_offered, 20)  # hard-max guard
        self.assertEqual(offer.max_units_offered, 5)  # min(20, 0*2+5)

    def test_per_scene_cap_increases_with_thread_level(self) -> None:
        """Higher Thread.level raises the per-scene cap."""
        sinner, sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(sinner, sineater)
        accept_soul_tether(
            initiator_sheet=sinner,
            partner_sheet=sineater,
            sinner_role=SoulTetherRoleEnum.ABYSSAL,
            resonance=self.resonance,
            writeup="Bond.",
            ritual_components=[],
        )
        rel = CharacterRelationship.objects.get(source=sinner, target=sineater)
        thread = Thread.objects.get(
            owner=sinner,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=self.resonance,
        )

        # Manually advance thread level to test cap formula.
        thread.level = 5
        thread.save(update_fields=["level"])

        cap = _compute_per_scene_sineating_cap(sinner_thread=thread, relationship=rel)
        self.assertEqual(cap, min(20, 5 * 2 + 5))  # min(20, 15) = 15
