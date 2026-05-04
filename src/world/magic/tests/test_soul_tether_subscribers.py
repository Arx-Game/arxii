"""Tests for the CORRUPTION_ACCRUING redirect subscriber (Spec B §5, Phase 6).

Each test class exercises the full reactive dispatch path:
    accrue_corruption() → emit_event(CORRUPTION_ACCRUING) → trigger pipeline
    → soul_tether_redirect_handler() → payload.amount mutated
    → accrue_corruption short-circuits or falls through with reduced amount.

For the pipeline to fire, the Sinner must be located in a room (emit_event
is gated on `location is not None`).  The helper `_place_in_room()` satisfies
this requirement.

Prerequisites per test:
- `wire_soul_tether_content()` seeds TriggerDefinition rows + Rituals.
- `accept_soul_tether(...)` installs Trigger rows on the Sinner's ObjectDB.
- A Corruption ConditionTemplate for the test resonance (so accrual has
  somewhere to land if it falls through).
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    AffinityFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    CorruptionConditionTemplateFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
    wire_soul_tether_content,
)
from world.magic.models import Thread
from world.magic.models.aura import CharacterResonance
from world.magic.services.corruption import accrue_corruption
from world.magic.services.soul_tether import accept_soul_tether
from world.magic.types.corruption import CorruptionSource
from world.magic.types.soul_tether import SoulTetherRole as SoulTetherRoleEnum
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
)

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _create_room(key: str = "TestRoom") -> ObjectDB:
    """Return a bare ObjectDB room for event dispatch."""
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _place_in_room(sheet: object, room: ObjectDB) -> None:
    """Move the character's ObjectDB into *room* so emit_event fires."""
    char = sheet.character  # type: ignore[union-attr]
    char.location = room
    char.save()


def _set_primary_affinity_abyssal(sheet: object) -> None:
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


def _set_primary_affinity_primal(sheet: object) -> None:
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
    unlock = ThreadWeavingUnlockFactory(
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        unlock_track=track,
        unlock_trait=None,
    )
    return CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock)


def _make_eligible_pair(track: object | None = None) -> tuple:
    """Return (sinner_sheet, sineater_sheet) satisfying all affinity + unlock gates."""
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
    rel = CharacterRelationshipFactory(source=source, target=target, is_pending=False)
    CharacterRelationshipFactory(source=target, target=source, is_pending=False)
    return rel


def _form_tether(sinner: object, sineater: object, resonance: object) -> object:
    """Form a soul tether between sinner and sineater for *resonance*."""
    return accept_soul_tether(
        initiator_sheet=sinner,
        partner_sheet=sineater,
        sinner_role=SoulTetherRoleEnum.ABYSSAL,
        resonance=resonance,
        writeup="Test bond.",
        ritual_components=[],
    )


def _sinner_thread(sinner: object, resonance: object) -> Thread:
    """Return the Sinner's RELATIONSHIP_CAPSTONE Thread for *resonance*."""
    return Thread.objects.get(
        owner=sinner,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        resonance=resonance,
        retired_at__isnull=True,
    )


def _sinner_corruption_current(sinner: object, resonance: object) -> int:
    """Return the Sinner's corruption_current for *resonance*, 0 if absent."""
    try:
        cr = CharacterResonance.objects.get(character_sheet=sinner, resonance=resonance)
        return cr.corruption_current
    except CharacterResonance.DoesNotExist:
        return 0


# ---------------------------------------------------------------------------
# 6.1  Full absorption (Hollow capacity ≥ accrual)
# ---------------------------------------------------------------------------


class FullAbsorptionTests(TestCase):
    """Hollow absorbs the full accrual — Sinner's corruption_current stays at 0."""

    def setUp(self) -> None:
        self.room = _create_room("Room_FullAbsorb")
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        # Corruption ConditionTemplate required so accrue_corruption has a template
        CorruptionConditionTemplateFactory(corruption_resonance=self.resonance)

        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)
        _form_tether(self.sinner, self.sineater, self.resonance)

        # Pre-seed a CharacterResonance so corruption_current is trackable.
        CharacterResonanceFactory(
            character_sheet=self.sinner,
            resonance=self.resonance,
            corruption_current=0,
        )

        # Place sinner in a room so emit_event fires.
        _place_in_room(self.sinner, self.room)

        # Charge the Hollow with enough capacity to absorb 5 units.
        self.thread = _sinner_thread(self.sinner, self.resonance)
        self.thread.hollow_current = 10
        self.thread.save()

    def test_full_absorption_no_sinner_accrual(self) -> None:
        """Accrual of 5 with Hollow=10 → Sinner gets 0, Hollow drains by 5."""
        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.resonance,
            amount=5,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.assertEqual(_sinner_corruption_current(self.sinner, self.resonance), 0)

    def test_full_absorption_hollow_drains(self) -> None:
        """Hollow should be reduced from 10 to 5 after absorbing 5 units."""
        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.resonance,
            amount=5,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.hollow_current, 5)

    def test_exact_absorption_hollow_reaches_zero(self) -> None:
        """Hollow exactly matches accrual (10 == 10) → Hollow drains to 0, no overflow."""
        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.resonance,
            amount=10,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.hollow_current, 0)
        self.assertEqual(_sinner_corruption_current(self.sinner, self.resonance), 0)


# ---------------------------------------------------------------------------
# 6.2  Partial absorption (Hollow exhausts mid-accrual)
# ---------------------------------------------------------------------------


class PartialAbsorptionTests(TestCase):
    """Hollow absorbs what it can; overflow falls through to Sinner."""

    def setUp(self) -> None:
        self.room = _create_room("Room_PartialAbsorb")
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        CorruptionConditionTemplateFactory(corruption_resonance=self.resonance)

        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)
        _form_tether(self.sinner, self.sineater, self.resonance)

        CharacterResonanceFactory(
            character_sheet=self.sinner,
            resonance=self.resonance,
            corruption_current=0,
        )
        _place_in_room(self.sinner, self.room)

        # Hollow capacity: 3 (less than the 7-unit accrual).
        self.thread = _sinner_thread(self.sinner, self.resonance)
        self.thread.hollow_current = 3
        self.thread.save()

    def test_partial_absorption_hollow_drained_to_zero(self) -> None:
        """Hollow (3) fully depleted absorbing 7-unit accrual."""
        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.resonance,
            amount=7,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.hollow_current, 0)

    def test_partial_absorption_sinner_accrues_overflow(self) -> None:
        """Sinner receives the overflow (7 - 3 = 4 units)."""
        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.resonance,
            amount=7,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.assertEqual(_sinner_corruption_current(self.sinner, self.resonance), 4)

    def test_empty_hollow_full_passthrough(self) -> None:
        """Empty Hollow (0) → full accrual falls through to Sinner."""
        self.thread.hollow_current = 0
        self.thread.save()

        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.resonance,
            amount=5,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.assertEqual(_sinner_corruption_current(self.sinner, self.resonance), 5)
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.hollow_current, 0)


# ---------------------------------------------------------------------------
# 6.3  No-tether passthrough
# ---------------------------------------------------------------------------


class NoTetherPassthroughTests(TestCase):
    """Sinner has no active tether → accrual proceeds normally (no absorption)."""

    def setUp(self) -> None:
        self.room = _create_room("Room_NoTether")
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        CorruptionConditionTemplateFactory(corruption_resonance=self.resonance)

        # Sinner without a tether — just a standalone character.
        wire_soul_tether_content()  # Seeds TriggerDefinition rows (but no Trigger installed).
        self.sinner = CharacterSheetFactory()
        _set_primary_affinity_abyssal(self.sinner)

        CharacterResonanceFactory(
            character_sheet=self.sinner,
            resonance=self.resonance,
            corruption_current=0,
        )
        _place_in_room(self.sinner, self.room)

    def test_no_tether_accrues_normally(self) -> None:
        """Without a tether, corruption accrues in full to the Sinner."""
        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.resonance,
            amount=5,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.assertEqual(_sinner_corruption_current(self.sinner, self.resonance), 5)

    def test_no_tether_no_threads_to_drain(self) -> None:
        """No RELATIONSHIP_CAPSTONE Thread exists — no drain occurs."""
        threads = Thread.objects.filter(
            owner=self.sinner,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        )
        self.assertEqual(threads.count(), 0)


# ---------------------------------------------------------------------------
# 6.4  Multi-tether priority order
# ---------------------------------------------------------------------------


class MultiTetherPriorityTests(TestCase):
    """Sinner has 2 tethers; highest-level Thread drains first."""

    def setUp(self) -> None:
        self.room = _create_room("Room_MultiTether")
        self.track1 = RelationshipTrackFactory()
        self.track2 = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        CorruptionConditionTemplateFactory(corruption_resonance=self.resonance)

        wire_soul_tether_content()
        self.sinner = CharacterSheetFactory()
        _set_primary_affinity_abyssal(self.sinner)
        _grant_relationship_track_unlock(self.sinner, self.track1)

        # Sineater 1
        self.sineater1 = CharacterSheetFactory()
        _set_primary_affinity_primal(self.sineater1)
        _make_active_relationship(self.sinner, self.sineater1)
        _form_tether(self.sinner, self.sineater1, self.resonance)

        # Sineater 2 — second tether to a different partner, same resonance.
        self.sineater2 = CharacterSheetFactory()
        _set_primary_affinity_primal(self.sineater2)
        _grant_relationship_track_unlock(self.sinner, self.track2)
        _make_active_relationship(self.sinner, self.sineater2)
        _form_tether(self.sinner, self.sineater2, self.resonance)

        CharacterResonanceFactory(
            character_sheet=self.sinner,
            resonance=self.resonance,
            corruption_current=0,
        )
        _place_in_room(self.sinner, self.room)

        # Give both threads some Hollow; set their levels so we can predict priority.
        self.thread1 = (
            Thread.objects.filter(
                owner=self.sinner,
                target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
                resonance=self.resonance,
            )
            .order_by("pk")
            .first()
        )
        self.thread2 = (
            Thread.objects.filter(
                owner=self.sinner,
                target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
                resonance=self.resonance,
            )
            .order_by("pk")
            .last()
        )

        # Make thread2 the higher-level one so it should drain first.
        self.thread1.level = 1
        self.thread1.hollow_current = 5
        self.thread1.save()
        self.thread2.level = 5
        self.thread2.hollow_current = 5
        self.thread2.save()

    def test_higher_level_thread_drains_first(self) -> None:
        """8-unit accrual: thread2 (level 5, hollow=5) drains first, thread1 drains 3."""
        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.resonance,
            amount=8,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.thread1.refresh_from_db()
        self.thread2.refresh_from_db()

        # thread2 (higher level) drains first → 5 absorbed → remaining 3
        # thread1 drains next → 3 absorbed → 0 remaining
        self.assertEqual(self.thread2.hollow_current, 0)
        self.assertEqual(self.thread1.hollow_current, 2)

    def test_multi_tether_full_absorption_no_sinner_accrual(self) -> None:
        """Both threads together absorb a 6-unit accrual with capacity to spare."""
        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.resonance,
            amount=6,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.assertEqual(_sinner_corruption_current(self.sinner, self.resonance), 0)


# ---------------------------------------------------------------------------
# 6.5  Resonance mismatch
# ---------------------------------------------------------------------------


class ResonanceMismatchTests(TestCase):
    """Sinner's Thread is Primal-resonance but accrual is Abyssal → no absorption."""

    def setUp(self) -> None:
        self.room = _create_room("Room_ResMatch")
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        primal_affinity = AffinityFactory(name="Primal")
        self.abyssal_resonance = ResonanceFactory(affinity=abyssal_affinity)
        self.primal_resonance = ResonanceFactory(affinity=primal_affinity)
        CorruptionConditionTemplateFactory(corruption_resonance=self.abyssal_resonance)

        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)
        # Form tether with PRIMAL resonance Thread on the Sinner.
        _form_tether(self.sinner, self.sineater, self.primal_resonance)

        CharacterResonanceFactory(
            character_sheet=self.sinner,
            resonance=self.abyssal_resonance,
            corruption_current=0,
        )
        _place_in_room(self.sinner, self.room)

        # Set the Primal thread's Hollow high — should not be touched.
        self.primal_thread = Thread.objects.get(
            owner=self.sinner,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            resonance=self.primal_resonance,
            retired_at__isnull=True,
        )
        self.primal_thread.hollow_current = 20
        self.primal_thread.save()

    def test_resonance_mismatch_sinner_accrues_normally(self) -> None:
        """Abyssal accrual with only a Primal thread → full accrual to Sinner."""
        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.abyssal_resonance,
            amount=5,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.assertEqual(_sinner_corruption_current(self.sinner, self.abyssal_resonance), 5)

    def test_resonance_mismatch_primal_thread_untouched(self) -> None:
        """The Primal Thread's hollow_current must remain unchanged."""
        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.abyssal_resonance,
            amount=5,
            source=CorruptionSource.TECHNIQUE_USE,
        )

        self.primal_thread.refresh_from_db()
        self.assertEqual(self.primal_thread.hollow_current, 20)
