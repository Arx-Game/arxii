"""Tests for Soul Tether reactive subscribers (Spec B §5, §8, Phases 6–7).

Phase 6 (CORRUPTION_ACCRUING redirect) — §5:
    accrue_corruption() → emit_event(CORRUPTION_ACCRUING) → trigger pipeline
    → soul_tether_redirect_handler() → payload.amount mutated
    → accrue_corruption short-circuits or falls through with reduced amount.

Phase 7 (CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE prompt) — §8:
    advance_condition_severity() → _perform_advancement_resist_check()
    → emit_event(CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE)
    → trigger pipeline → soul_tether_stage_advance_prompt()
    → offer recorded, Sineater notified (if in scene)
    → resist check fires at original difficulty (synchronous path)
    → resolve_stage_advance_prompt() drains Hollow + adds Strain retroactively.

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
from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import advance_condition_severity
from world.conditions.types import AdvancementResistFailureKind
from world.magic.constants import TargetKind
from world.magic.exceptions import StageAdvanceBonusError
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
from world.magic.services.soul_tether import (
    _pending_stage_advance_offers,
    accept_soul_tether,
    resolve_stage_advance_prompt,
)
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
        sinner_role=SoulTetherRoleEnum.SINNER,
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


# ===========================================================================
# Phase 7 — Stage-advance dramatic prompt (Spec B §8)
# ===========================================================================


def _make_corruption_condition_with_resist(
    resonance: object,
) -> tuple:
    """Return (condition_template, stage1, stage2, check_type) with HOLD_OVERFLOW on stage2.

    Stage1: severity_threshold=5, ADVANCE_AT_THRESHOLD (no resist).
    Stage2: severity_threshold=10, HOLD_OVERFLOW with a resist check.
    Both are Corruption conditions (corruption_resonance set).

    The Corruption template must have corruption_resonance set so that
    soul_tether_stage_advance_prompt correctly identifies it as ours.
    """
    from world.conditions.factories import ConditionCategoryFactory

    check_type = CheckTypeFactory()
    category = ConditionCategoryFactory()
    template = ConditionTemplateFactory(
        has_progression=True,
        corruption_resonance=resonance,
        category=category,
    )
    ConditionStageFactory(
        condition=template,
        stage_order=1,
        name="Sinful",
        severity_threshold=5,
        advancement_resist_failure_kind=AdvancementResistFailureKind.ADVANCE_AT_THRESHOLD,
        resist_check_type=None,
    )
    stage2 = ConditionStageFactory(
        condition=template,
        stage_order=2,
        name="Tainted",
        severity_threshold=10,
        advancement_resist_failure_kind=AdvancementResistFailureKind.HOLD_OVERFLOW,
        resist_check_type=check_type,
        resist_difficulty=15,
    )
    return template, stage2, check_type


def _make_check_result(success_level: int) -> object:
    """Return a mock CheckResult whose success_level returns the given integer."""
    result = MagicMock()
    result.success_level = success_level
    return result


class StageAdvancePromptFiresWhenSineaterInSceneTests(TestCase):
    """7.1 — PROMPT fires when Sineater is in same room as Sinner (Spec B §8.1)."""

    def setUp(self) -> None:
        self.room = _create_room("Room_StagePrompt")
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)

        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)
        _form_tether(self.sinner, self.sineater, self.resonance)

        self.template, self.stage2, self.check_type = _make_corruption_condition_with_resist(
            self.resonance
        )

        # Place Sinner in the room.
        _place_in_room(self.sinner, self.room)
        # Place Sineater in the SAME room.
        _place_in_room(self.sineater, self.room)

        # Pre-charge the Sinner's Thread Hollow.
        self.thread = _sinner_thread(self.sinner, self.resonance)
        self.thread.hollow_current = 5
        self.thread.save()

        # Create a ConditionInstance at stage1 severity to be near the stage2 crossing.
        self.condition_instance = ConditionInstanceFactory(
            condition=self.template,
            target=self.sinner.character,
            current_stage=self.template.stages.get(stage_order=1),
            severity=7,
        )

        # Clear any leftover pending offers before each test.
        _pending_stage_advance_offers.clear()

    def tearDown(self) -> None:
        _pending_stage_advance_offers.clear()

    @patch("world.conditions.services.perform_check")
    def test_prompt_offer_recorded_when_sineater_in_scene(self, mock_check: object) -> None:
        """Advancing severity over stage2 threshold records a StageAdvanceBonusOffer."""
        mock_check.return_value = _make_check_result(success_level=-1)  # Fail = advances

        self.assertEqual(len(_pending_stage_advance_offers), 0)

        advance_condition_severity(self.condition_instance, 5)  # 7+5=12, crosses threshold 10

        # The handler should have recorded one offer.
        self.assertEqual(len(_pending_stage_advance_offers), 1)

    @patch("world.conditions.services.perform_check")
    def test_offer_has_correct_sinner_and_sineater(self, mock_check: object) -> None:
        """The recorded offer references the correct Sinner and Sineater sheets."""
        mock_check.return_value = _make_check_result(success_level=-1)

        advance_condition_severity(self.condition_instance, 5)

        offer = next(iter(_pending_stage_advance_offers.values()))
        self.assertEqual(offer.sinner_sheet, self.sinner)
        self.assertEqual(offer.sineater_sheet, self.sineater)

    @patch("world.conditions.services.perform_check")
    def test_offer_max_hollow_reflects_thread_capacity(self, mock_check: object) -> None:
        """max_hollow_to_spend equals the Sinner's Thread's current hollow_current."""
        mock_check.return_value = _make_check_result(success_level=-1)

        advance_condition_severity(self.condition_instance, 5)

        offer = next(iter(_pending_stage_advance_offers.values()))
        self.assertEqual(offer.max_hollow_to_spend, 5)  # Thread.hollow_current=5

    @patch("world.conditions.services.perform_check")
    def test_sineater_receives_notification(self, mock_check: object) -> None:
        """The Sineater's ObjectDB.msg() is called with the offer details."""
        mock_check.return_value = _make_check_result(success_level=-1)

        with patch.object(self.sineater.character, "msg") as mock_msg:
            advance_condition_severity(self.condition_instance, 5)

        mock_msg.assert_called_once()
        call_text = mock_msg.call_args[0][0]
        self.assertIn("SOUL TETHER", call_text)


class StageAdvancePromptNoSineaterInSceneTests(TestCase):
    """7.4 — No offer fires when no Sineater is in the same room (Spec B §8.1)."""

    def setUp(self) -> None:
        self.room = _create_room("Room_NoSineater")
        self.other_room = _create_room("Room_SineaterElsewhere")
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)

        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)
        _form_tether(self.sinner, self.sineater, self.resonance)

        self.template, self.stage2, self.check_type = _make_corruption_condition_with_resist(
            self.resonance
        )

        # Place Sinner in the room.
        _place_in_room(self.sinner, self.room)
        # Place Sineater in a DIFFERENT room.
        _place_in_room(self.sineater, self.other_room)

        self.condition_instance = ConditionInstanceFactory(
            condition=self.template,
            target=self.sinner.character,
            current_stage=self.template.stages.get(stage_order=1),
            severity=7,
        )

        _pending_stage_advance_offers.clear()

    def tearDown(self) -> None:
        _pending_stage_advance_offers.clear()

    @patch("world.conditions.services.perform_check")
    def test_no_offer_when_sineater_in_different_room(self, mock_check: object) -> None:
        """Sineater in a different room → no offer recorded."""
        mock_check.return_value = _make_check_result(success_level=-1)

        advance_condition_severity(self.condition_instance, 5)

        self.assertEqual(len(_pending_stage_advance_offers), 0)

    @patch("world.conditions.services.perform_check")
    def test_resist_check_proceeds_without_offer(self, mock_check: object) -> None:
        """Check still fires (mock called) even with no Sineater in scene."""
        mock_check.return_value = _make_check_result(success_level=1)  # Pass = HELD

        from world.conditions.types import AdvancementOutcome

        result = advance_condition_severity(self.condition_instance, 5)
        self.assertEqual(result.outcome, AdvancementOutcome.HELD)
        mock_check.assert_called_once()


class StageAdvancePromptNonCorruptionConditionTests(TestCase):
    """7.4 (variant) — Non-Corruption conditions are skipped by the handler."""

    def setUp(self) -> None:
        self.room = _create_room("Room_NonCorruption")
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)

        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)
        _form_tether(self.sinner, self.sineater, self.resonance)

        # Template WITHOUT corruption_resonance — should be ignored by handler.
        check_type = CheckTypeFactory()
        from world.conditions.factories import ConditionCategoryFactory

        category = ConditionCategoryFactory()
        self.template = ConditionTemplateFactory(
            has_progression=True,
            corruption_resonance=None,  # Not a Corruption condition
            category=category,
        )
        ConditionStageFactory(
            condition=self.template,
            stage_order=1,
            name="Generic Stage 1",
            severity_threshold=5,
            advancement_resist_failure_kind=AdvancementResistFailureKind.ADVANCE_AT_THRESHOLD,
            resist_check_type=None,
        )
        ConditionStageFactory(
            condition=self.template,
            stage_order=2,
            name="Generic Stage 2",
            severity_threshold=10,
            advancement_resist_failure_kind=AdvancementResistFailureKind.HOLD_OVERFLOW,
            resist_check_type=check_type,
            resist_difficulty=12,
        )

        _place_in_room(self.sinner, self.room)
        _place_in_room(self.sineater, self.room)

        self.condition_instance = ConditionInstanceFactory(
            condition=self.template,
            target=self.sinner.character,
            current_stage=self.template.stages.get(stage_order=1),
            severity=7,
        )
        _pending_stage_advance_offers.clear()

    def tearDown(self) -> None:
        _pending_stage_advance_offers.clear()

    @patch("world.conditions.services.perform_check")
    def test_non_corruption_condition_skipped(self, mock_check: object) -> None:
        """Handler returns immediately for non-Corruption conditions — no offer recorded."""
        mock_check.return_value = _make_check_result(success_level=-1)

        advance_condition_severity(self.condition_instance, 5)

        self.assertEqual(len(_pending_stage_advance_offers), 0)


@tag("postgres")
class StageAdvanceBonusAcceptTests(TestCase):
    """7.2 — Accept path: resolve_stage_advance_prompt drains Hollow + adds Strain."""

    def setUp(self) -> None:
        self.room = _create_room("Room_BonusAccept")
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)

        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)
        _form_tether(self.sinner, self.sineater, self.resonance)

        self.template, self.stage2, self.check_type = _make_corruption_condition_with_resist(
            self.resonance
        )

        _place_in_room(self.sinner, self.room)
        _place_in_room(self.sineater, self.room)

        self.thread = _sinner_thread(self.sinner, self.resonance)
        self.thread.hollow_current = 8
        self.thread.save()

        self.condition_instance = ConditionInstanceFactory(
            condition=self.template,
            target=self.sinner.character,
            current_stage=self.template.stages.get(stage_order=1),
            severity=7,
        )
        _pending_stage_advance_offers.clear()

    def tearDown(self) -> None:
        _pending_stage_advance_offers.clear()

    def _fire_prompt_and_get_offer_id(self) -> str:
        """Trigger the stage-advance check (mocked to fail) and return the offer_id."""
        with patch("world.conditions.services.perform_check") as mock_check:
            mock_check.return_value = _make_check_result(success_level=-1)
            advance_condition_severity(self.condition_instance, 5)

        self.assertEqual(len(_pending_stage_advance_offers), 1)
        return next(iter(_pending_stage_advance_offers.keys()))

    def test_accept_drains_hollow(self) -> None:
        """Committing 3 units drains Thread.hollow_current by 3."""
        offer_id = self._fire_prompt_and_get_offer_id()

        result = resolve_stage_advance_prompt(offer_id, units_committed=3)

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.hollow_current, 5)  # 8 - 3
        self.assertEqual(result.hollow_drained, 3)
        self.assertFalse(result.declined)

    def test_accept_adds_strain_severity(self) -> None:
        """Committing 3 units adds Strain severity to the Sineater."""
        from world.conditions.models import ConditionInstance

        offer_id = self._fire_prompt_and_get_offer_id()

        # Seed TetherStrain template (normally done by wire_soul_tether_content).
        # wire_soul_tether_content() was called by _make_eligible_pair → already seeded.
        result = resolve_stage_advance_prompt(offer_id, units_committed=3)

        self.assertEqual(result.strain_severity_added, 3)

        # Verify the ConditionInstance was created and has severity.
        strain_instance = ConditionInstance.objects.filter(
            target=self.sineater.character,
            condition__name="Tether Strain",
            resolved_at__isnull=True,
        ).first()
        self.assertIsNotNone(strain_instance)
        self.assertGreater(strain_instance.severity, 0)

    def test_accept_removes_offer_from_registry(self) -> None:
        """After resolution the offer is no longer in the pending registry."""
        offer_id = self._fire_prompt_and_get_offer_id()

        resolve_stage_advance_prompt(offer_id, units_committed=2)

        self.assertNotIn(offer_id, _pending_stage_advance_offers)

    def test_units_clamped_to_max_hollow(self) -> None:
        """Requesting more units than max_hollow_to_spend clamps to available max."""
        offer_id = self._fire_prompt_and_get_offer_id()

        result = resolve_stage_advance_prompt(offer_id, units_committed=100)

        # Max hollow was 8 — should have drained all 8.
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.hollow_current, 0)
        self.assertEqual(result.hollow_drained, 8)


class StageAdvanceBonusDeclineTests(TestCase):
    """7.3 — Decline path: units_committed=0 → no Hollow drain, no Strain, declined=True."""

    def setUp(self) -> None:
        self.room = _create_room("Room_BonusDecline")
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)

        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)
        _form_tether(self.sinner, self.sineater, self.resonance)

        self.template, self.stage2, self.check_type = _make_corruption_condition_with_resist(
            self.resonance
        )

        _place_in_room(self.sinner, self.room)
        _place_in_room(self.sineater, self.room)

        self.thread = _sinner_thread(self.sinner, self.resonance)
        self.thread.hollow_current = 8
        self.thread.save()

        self.condition_instance = ConditionInstanceFactory(
            condition=self.template,
            target=self.sinner.character,
            current_stage=self.template.stages.get(stage_order=1),
            severity=7,
        )
        _pending_stage_advance_offers.clear()

    def tearDown(self) -> None:
        _pending_stage_advance_offers.clear()

    def _fire_and_get_offer_id(self) -> str:
        with patch("world.conditions.services.perform_check") as mock_check:
            mock_check.return_value = _make_check_result(success_level=-1)
            advance_condition_severity(self.condition_instance, 5)
        return next(iter(_pending_stage_advance_offers.keys()))

    def test_decline_no_hollow_drain(self) -> None:
        """units_committed=0 → Thread.hollow_current unchanged."""
        offer_id = self._fire_and_get_offer_id()

        result = resolve_stage_advance_prompt(offer_id, units_committed=0)

        self.thread.refresh_from_db()
        self.assertEqual(self.thread.hollow_current, 8)
        self.assertEqual(result.hollow_drained, 0)
        self.assertTrue(result.declined)

    def test_decline_no_strain(self) -> None:
        """units_committed=0 → no Strain added to Sineater."""
        from world.conditions.models import ConditionInstance

        offer_id = self._fire_and_get_offer_id()

        result = resolve_stage_advance_prompt(offer_id, units_committed=0)

        self.assertEqual(result.strain_severity_added, 0)

        # No TetherStrain ConditionInstance should exist for the Sineater.
        has_strain = ConditionInstance.objects.filter(
            target=self.sineater.character,
            condition__name="Tether Strain",
            resolved_at__isnull=True,
            severity__gt=0,
        ).exists()
        self.assertFalse(has_strain)

    def test_decline_offer_removed_from_registry(self) -> None:
        """Even a decline removes the offer from the pending registry."""
        offer_id = self._fire_and_get_offer_id()

        resolve_stage_advance_prompt(offer_id, units_committed=0)

        self.assertNotIn(offer_id, _pending_stage_advance_offers)


class StageAdvanceBonusUnknownOfferTests(TestCase):
    """Resolving an unknown offer_id raises StageAdvanceBonusError."""

    def test_unknown_offer_id_raises(self) -> None:
        _pending_stage_advance_offers.clear()
        with self.assertRaises(StageAdvanceBonusError):
            resolve_stage_advance_prompt("nonexistent-offer-id", units_committed=1)
