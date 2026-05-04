"""Service tests for accept_soul_tether (Spec B §12, Phase 4).

Tests cover:
    4.1  AffinityGateError on Abyssal-primary Sineater or Celestial-primary Sinner
    4.2  NoSoulTetherUnlockError when Sinner lacks RELATIONSHIP_CAPSTONE ThreadWeavingUnlock
    4.3  Happy-path formation (capstone + flags + thread + condition + triggers)
    4.4  Idempotency — duplicate formation raises SoulTetherFormationError
    4.5  Multi-tether — second tether to different Sineater reuses ConditionInstance
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from flows.models.triggers import Trigger
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.models import ConditionInstance
from world.magic.constants import SoulTetherRole, TargetKind
from world.magic.exceptions import (
    AffinityGateError,
    NoSoulTetherUnlockError,
    SoulTetherFormationError,
)
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
    wire_soul_tether_content,
)
from world.magic.models import Thread
from world.magic.services.soul_tether import accept_soul_tether
from world.magic.types.soul_tether import SoulTetherRole as SoulTetherRoleEnum
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
