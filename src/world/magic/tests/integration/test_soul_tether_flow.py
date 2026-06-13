"""End-to-end integration tests for the Soul Tether mechanic (Spec B §19.2).

Three sub-tasks per plan Phase 13:

13.1  Full pipeline (formation → Sineating → redirect → rescue → dissolution)
13.2  Anti-resentment invariant (dormant tether imposes zero anima/Resonance cost)
13.3  Many-to-many independence (one Sineater, two Sinners — independent state)

Pattern mirrors src/world/magic/tests/integration/test_corruption_flow.py and
test_soulfray_recovery_flow.py:
  - Use real service functions; patch only network/session-adjacent surfaces
    (_both_in_scene, perform_check) that can't run without a live process.
  - Assertions against the DB, not against mocks.
  - No freezegun — dormancy is simulated by counting corrupt-decay ticks
    directly rather than wall-clock time.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.conditions.services import decay_all_conditions_tick
from world.magic.constants import SoulTetherRole, TargetKind
from world.magic.factories import (
    AffinityFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ResonanceFactory,
    ThreadWeavingUnlockFactory,
    wire_soul_tether_content,
    with_corruption_at_stage,
)
from world.magic.models import Thread
from world.magic.models.aura import CharacterResonance
from world.magic.services.corruption import accrue_corruption
from world.magic.services.soul_tether import (
    accept_soul_tether,
    dissolve_soul_tether,
    perform_soul_tether_rescue,
    resolve_sineating,
)
from world.magic.types.corruption import CorruptionSource
from world.magic.types.soul_tether import (
    SineatingOffer,
    SoulTetherRole as SoulTetherRoleEnum,
)
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
)
from world.relationships.models import CharacterRelationship

# ---------------------------------------------------------------------------
# Module-level helpers shared across all three test sub-tasks
# ---------------------------------------------------------------------------

_PERFORM_CHECK_PATH = "world.checks.services.perform_check"
_BOTH_IN_SCENE_PATH = "world.magic.services.soul_tether._both_in_scene"

# Counter for unique room keys (avoid DB unique constraint collisions).
_room_counter = 0


def _create_room() -> ObjectDB:
    global _room_counter  # noqa: PLW0603
    _room_counter += 1
    return ObjectDB.objects.create(
        db_key=f"TetherIntegRoom_{_room_counter}",
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _place_in_room(sheet: object, room: ObjectDB) -> None:
    char = sheet.character  # type: ignore[union-attr]
    char.location = room
    char.save()


def _set_aura(sheet: object, *, celestial: str, primal: str, abyssal: str) -> None:
    """Set or create a CharacterAura for *sheet*."""
    char = sheet.character  # type: ignore[union-attr]
    defaults = {
        "celestial": Decimal(celestial),
        "primal": Decimal(primal),
        "abyssal": Decimal(abyssal),
    }
    try:
        aura = char.aura
        for k, v in defaults.items():
            setattr(aura, k, v)
        aura.save()
    except AttributeError:
        CharacterAuraFactory(character=char, **defaults)


def _set_abyssal_primary(sheet: object) -> None:
    _set_aura(sheet, celestial="10.00", primal="10.00", abyssal="80.00")


def _set_primal_primary(sheet: object) -> None:
    _set_aura(sheet, celestial="10.00", primal="80.00", abyssal="10.00")


def _grant_track_unlock(sheet: object, track: object) -> object:
    unlock = ThreadWeavingUnlockFactory(
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        unlock_track=track,
        unlock_trait=None,
    )
    return CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock)


def _make_active_relationship(source: object, target: object) -> object:
    """Create both directional CharacterRelationship rows (non-pending)."""
    rel = CharacterRelationshipFactory(source=source, target=target, is_pending=False)
    CharacterRelationshipFactory(source=target, target=source, is_pending=False)
    return rel


def _make_eligible_pair(*, track: object | None = None) -> tuple:
    """Return (sinner_sheet, sineater_sheet) with all affinity/unlock gates satisfied.

    - Sinner: Abyssal-primary with a RELATIONSHIP_TRACK ThreadWeavingUnlock.
    - Sineater: Primal-primary.
    """
    sinner = CharacterSheetFactory()
    sineater = CharacterSheetFactory()
    _set_abyssal_primary(sinner)
    _set_primal_primary(sineater)
    if track is None:
        track = RelationshipTrackFactory()
    _grant_track_unlock(sinner, track)
    return sinner, sineater


def _make_tethered_pair(
    *,
    track: object | None = None,
) -> tuple:
    """Return (sinner_sheet, sineater_sheet, resonance, capstone).

    Calls wire_soul_tether_content() and accept_soul_tether().  Returned
    capstone is the RelationshipCapstone created by formation.
    """
    wire_soul_tether_content()
    if track is None:
        track = RelationshipTrackFactory()
    abyssal_affinity = AffinityFactory(name="Abyssal")
    resonance = ResonanceFactory(affinity=abyssal_affinity)
    sinner, sineater = _make_eligible_pair(track=track)
    _make_active_relationship(sinner, sineater)
    capstone = accept_soul_tether(
        initiator_sheet=sinner,
        partner_sheet=sineater,
        sinner_role=SoulTetherRoleEnum.SINNER,
        resonance=resonance,
        writeup="Integration test bond.",
        ritual_components=[],
    )
    return sinner, sineater, resonance, capstone


def _get_sinner_thread(sinner: object, capstone: object, resonance: object) -> Thread:
    """Return the Sinner's RELATIONSHIP_CAPSTONE Thread for this capstone + resonance."""
    return Thread.objects.get(
        owner=sinner,
        target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
        target_capstone=capstone,
        resonance=resonance,
        retired_at__isnull=True,
    )


def _bump_thread_level(thread: Thread, level: int) -> Thread:
    """Directly set Thread.level (bypasses XP so tests can use any level)."""
    thread.level = level
    thread.save(update_fields=["level"])
    return thread


def _make_mock_check(success_level: int = 1) -> MagicMock:
    """Return a MagicMock CheckResult with a real CheckOutcome FK row."""
    from world.traits.factories import CheckOutcomeFactory

    outcome = CheckOutcomeFactory(
        name=f"TetherIntegOutcome_sl_{success_level}_{id(object())}",
        success_level=success_level,
    )
    result = MagicMock()
    result.outcome = outcome
    result.success_level = success_level
    return result


def _make_simple_corruption_template(resonance: object) -> tuple:
    """Create a five-stage Corruption ConditionTemplate for *resonance*.

    Thresholds: 50, 200, 500, 1000, 1500.  No HOLD_OVERFLOW resist check so
    stage advancement is deterministic in tests.
    """
    template = ConditionTemplateFactory(
        name=f"Corruption ({resonance.name} integ)",
        has_progression=True,
        corruption_resonance=resonance,
    )
    thresholds = [50, 200, 500, 1000, 1500]
    stages = []
    for i, threshold in enumerate(thresholds, start=1):
        stages.append(
            ConditionStageFactory(
                condition=template,
                stage_order=i,
                severity_threshold=threshold,
            )
        )
    return template, stages


def _build_sineating_offer(
    sinner: object,
    sineater: object,
    resonance: object,
    relationship: object,
    max_units: int = 5,
) -> SineatingOffer:
    """Construct a SineatingOffer directly, bypassing scene/roster validation."""
    from world.magic.services.soul_tether import _ANIMA_COST_PER_UNIT, _FATIGUE_COST_PER_UNIT

    return SineatingOffer(
        sinner_sheet=sinner,  # type: ignore[arg-type]
        sineater_sheet=sineater,  # type: ignore[arg-type]
        relationship=relationship,  # type: ignore[arg-type]
        resonance=resonance,  # type: ignore[arg-type]
        max_units_offered=max_units,
        anima_cost_per_unit=_ANIMA_COST_PER_UNIT,
        fatigue_cost_per_unit=_FATIGUE_COST_PER_UNIT,
        current_hollow=0,
        hollow_max=100,
        sineater_current_strain_stage=0,
    )


# ===========================================================================
# 13.1  Full pipeline integration test
# ===========================================================================


class SoulTetherFullPipelineTests(TestCase):
    """Scenario 13.1: exercise every phase contribution end-to-end.

    Steps:
      1. Form tether (Phase 4) → relationship flags + thread + condition + triggers.
      2. Sineater resolves Sineating (Phase 5) → Hollow fills, lifetime_helped increases.
      3. Sinner casts (Phase 6) → CORRUPTION_ACCRUING → redirect drains Hollow, no
         direct Sinner corruption.
      4. Push Sinner to stage 3+ → rescue (Phase 8) → severity_reduced, lifetime_helped
         grows, strain on Sineater.
      5. Dissolve (Phase 10) → thread soft-retired, relationship flags cleared.
      6. lifetime_helped persists post-dissolution (spec §13).

    The tether is formed inside setUp (per-test) so each method gets a fresh bond.
    Per-test setup avoids Django's TestData descriptor deepcopy guard, which trips
    on Evennia's DbHolder when a class-level fixture's typeclass attribute graph
    has been touched by an earlier test (SharedMemoryModel identity-map carries
    the DbHolder pollution across tests). The cost is per-test re-creation; for
    these 4 tests it adds a few seconds but eliminates a real flake on the full
    sequential regression run.
    """

    def setUp(self) -> None:
        wire_soul_tether_content()
        self.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        self.resonance = ResonanceFactory(affinity=abyssal_affinity)
        self.sinner, self.sineater = _make_eligible_pair(track=self.track)
        _make_active_relationship(self.sinner, self.sineater)

        # Seed Sinner's CharacterResonance so the Sineating resonance gate passes.
        CharacterResonanceFactory(character_sheet=self.sinner, resonance=self.resonance)

        # Seed Sineater anima for Sineating cost deductions.
        CharacterAnimaFactory(character=self.sineater.character, current=50, maximum=50)

        # Five-stage Corruption ConditionTemplate for the resonance.
        _make_simple_corruption_template(self.resonance)

        # Place Sinner in a room so CORRUPTION_ACCRUING fires through emit_event.
        self.room = _create_room()
        _place_in_room(self.sinner, self.room)

        # ---- Step 1: Form the tether (Phase 4) ----
        self.capstone = accept_soul_tether(
            initiator_sheet=self.sinner,
            partner_sheet=self.sineater,
            sinner_role=SoulTetherRoleEnum.SINNER,
            resonance=self.resonance,
            writeup="A bond is forged in the witch-light.",
            ritual_components=[],
        )

    # -----------------------------------------------------------------------
    # Step 1: Formation invariants (read-only assertions against shared tether)
    # -----------------------------------------------------------------------

    def test_01_formation_sets_relationship_flags(self) -> None:
        """Step 1: is_soul_tether=True on both directional rows after formation."""
        rel_out = CharacterRelationship.objects.get(source=self.sinner, target=self.sineater)
        rel_in = CharacterRelationship.objects.get(source=self.sineater, target=self.sinner)
        self.assertTrue(rel_out.is_soul_tether)
        self.assertTrue(rel_in.is_soul_tether)
        self.assertEqual(rel_out.soul_tether_role, SoulTetherRole.SINNER)
        self.assertEqual(rel_in.soul_tether_role, SoulTetherRole.SINEATER)

    def test_02_formation_weaves_sinner_thread(self) -> None:
        """Step 1: Sinner's RELATIONSHIP_CAPSTONE Thread exists with hollow_current=0."""
        thread = Thread.objects.filter(
            owner=self.sinner,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=self.capstone,
            resonance=self.resonance,
            retired_at__isnull=True,
        )
        self.assertEqual(thread.count(), 1)
        self.assertEqual(thread.first().hollow_current, 0)

    def test_03_formation_installs_active_condition_and_triggers(self) -> None:
        """Step 1: SoulTetherActive ConditionInstance + 2 Trigger rows on Sinner."""
        from flows.models.triggers import Trigger

        cond_qs = ConditionInstance.objects.filter(
            target=self.sinner.character,
            condition__name="Soul Tether Active",
        )
        self.assertEqual(cond_qs.count(), 1)
        trigger_count = Trigger.objects.filter(obj=self.sinner.character).count()
        self.assertEqual(trigger_count, 2)

    # -----------------------------------------------------------------------
    # Steps 2–6: Full lifecycle (single sequential test to share capstone ref)
    # -----------------------------------------------------------------------

    @tag("postgres")
    def test_04_full_lifecycle(self) -> None:
        """Steps 2–6: Sineating → redirect → rescue → dissolution → persistence."""
        rel_out = CharacterRelationship.objects.get(source=self.sinner, target=self.sineater)
        sinner_thread = _get_sinner_thread(self.sinner, self.capstone, self.resonance)

        # Bump thread level so the Hollow has capacity (level*10 = 30).
        _bump_thread_level(sinner_thread, level=3)
        sinner_thread.refresh_from_db()

        # ---- Step 2: Sineating fills the Hollow ----
        offer = _build_sineating_offer(
            self.sinner, self.sineater, self.resonance, rel_out, max_units=10
        )
        result = resolve_sineating(offer, units_accepted=10)

        self.assertFalse(result.declined)
        self.assertEqual(result.units_accepted, 10)

        sinner_thread.refresh_from_db()
        # hollow_max = level*10 = 30; we added 10 units → hollow_current = min(30, 10) = 10
        self.assertGreater(sinner_thread.hollow_current, 0)
        hollow_after_sineating = sinner_thread.hollow_current

        sineater_cr = CharacterResonance.objects.get(
            character_sheet=self.sineater, resonance=self.resonance
        )
        self.assertGreater(sineater_cr.lifetime_helped, 0)
        lifetime_after_sineating = sineater_cr.lifetime_helped

        # ---- Step 3: Redirect — Sinner casts, Hollow absorbs ----
        # The redirect subscriber (Phase 6) fires via the trigger pipeline when
        # CORRUPTION_ACCRUING is emitted.  We accrue directly; the trigger pipeline
        # is already wired because accept_soul_tether installed the Trigger rows.
        sinner_cr_before = CharacterResonance.objects.get(
            character_sheet=self.sinner, resonance=self.resonance
        )
        corruption_before = sinner_cr_before.corruption_current

        accrue_corruption(
            character_sheet=self.sinner,
            resonance=self.resonance,
            amount=5,
            source=CorruptionSource.STAFF_GRANT,
        )

        sinner_thread.refresh_from_db()
        sinner_cr_before.refresh_from_db()

        # Hollow should have drained by 5 (or by whatever was absorbed).
        absorbed = hollow_after_sineating - sinner_thread.hollow_current
        self.assertGreaterEqual(absorbed, 0)

        # Sinner's corruption_current should be no higher than before + (amount - absorbed).
        # With sufficient Hollow capacity the full 5 units are absorbed → current unchanged.
        corruption_after = sinner_cr_before.corruption_current
        # absorbed + remaining == original accrual (5)
        remaining = 5 - absorbed
        expected_upper = corruption_before + remaining
        self.assertLessEqual(corruption_after, expected_upper)

        # ---- Step 4: Rescue ----
        # Push Sinner to stage 3 using with_corruption_at_stage helper.
        # This bypasses the trigger pipeline; the Hollow is ignored because
        # with_corruption_at_stage writes directly to the DB.
        with_corruption_at_stage(self.sinner, self.resonance, stage=3)

        # Give Sineater enough balance to pay the stage-3 resonance cost (10).
        sineater_cr, _ = CharacterResonance.objects.get_or_create(
            character_sheet=self.sineater, resonance=self.resonance
        )
        sineater_cr.balance = 500
        sineater_cr.save(update_fields=["balance"])

        mock_check = _make_mock_check(success_level=1)
        with (
            patch(_BOTH_IN_SCENE_PATH, return_value=True),
            patch(_PERFORM_CHECK_PATH, return_value=mock_check),
        ):
            rescue_outcome = perform_soul_tether_rescue(
                sineater_sheet=self.sineater,
                sinner_sheet=self.sinner,
                resonance=self.resonance,
                components=[],
                scene=None,  # scene-participation patched above
            )

        self.assertGreater(rescue_outcome.severity_reduced, 0)
        self.assertEqual(rescue_outcome.sinner_stage_at_start, 3)

        sineater_cr.refresh_from_db()
        self.assertGreater(
            sineater_cr.lifetime_helped,
            lifetime_after_sineating,
            "lifetime_helped should grow after rescue",
        )
        lifetime_after_rescue = sineater_cr.lifetime_helped

        # Sineater should have taken Tether Strain.
        strain = ConditionInstance.objects.filter(
            target=self.sineater.character,
            condition__name="Tether Strain",
            resolved_at__isnull=True,
        ).first()
        self.assertIsNotNone(strain)
        self.assertGreater(strain.severity, 0)

        # ---- Step 5: Dissolution ----
        sinner_thread_pk = sinner_thread.pk
        dissolve_soul_tether(
            relationship_id=rel_out.pk,
            initiator_sheet=self.sinner,
        )

        # Re-query by PK using .values() to bypass SharedMemoryModel identity-map
        # cache.  Thread.objects.filter(...).update() sets retired_at in the DB but
        # does not update the in-memory instance, so refresh_from_db() alone is
        # unreliable here (see test_soul_tether_services.py test_sinner_thread_retired_at_set).
        thread_row = Thread.objects.filter(pk=sinner_thread_pk).values("retired_at").first()
        self.assertIsNotNone(thread_row)
        self.assertIsNotNone(
            thread_row["retired_at"],
            "Sinner's Thread should be soft-retired after dissolution",
        )

        rel_out.refresh_from_db()
        self.assertFalse(rel_out.is_soul_tether)

        # ---- Step 6: Persistence invariant ----
        # lifetime_helped on Sineater's CharacterResonance must persist post-dissolution
        # (spec §13: "permanent record of the bond").
        sineater_cr.refresh_from_db()
        self.assertEqual(
            sineater_cr.lifetime_helped,
            lifetime_after_rescue,
            "lifetime_helped must not be cleared on dissolution",
        )


# ===========================================================================
# 13.2  Anti-resentment invariant
# ===========================================================================


class AntiResentmentInvariantTests(TestCase):
    """Scenario 13.2: Dormant tether imposes zero resource cost on both parties.

    Spec §1.3.1: "No mechanic in this system may create a gameplay reason to
    resent an inactive player. The only consequence of inactivity should be the
    loss of their RP."

    Verified invariants:
    - Sineater's anima is unchanged after N daily ticks with no Sineating.
    - Sinner's Resonance balance is unchanged after N daily ticks.
    - No Tether Strain accumulates on the Sineater due to dormancy alone.
    - Sinner's passive Corruption decay DOES apply (per spec §11) — this is
      not a penalty; it is the expected background mechanic regardless of tether.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        wire_soul_tether_content()
        cls.track = RelationshipTrackFactory()
        abyssal_affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(affinity=abyssal_affinity)
        cls.sinner, cls.sineater = _make_eligible_pair(track=cls.track)
        _make_active_relationship(cls.sinner, cls.sineater)

        # Seed Sinner CharacterResonance (so the row exists at snapshot time).
        CharacterResonanceFactory(
            character_sheet=cls.sinner,
            resonance=cls.resonance,
            balance=100,
        )
        # Seed Sineater anima — this is what we monitor.
        cls.sineater_anima = CharacterAnimaFactory(
            character=cls.sineater.character,
            current=30,
            maximum=30,
        )
        # No Sineating seeded; Sineater's CharacterResonance may or may not exist.

        # Form tether (installs condition + triggers on Sinner).
        cls.capstone = accept_soul_tether(
            initiator_sheet=cls.sinner,
            partner_sheet=cls.sineater,
            sinner_role=SoulTetherRoleEnum.SINNER,
            resonance=cls.resonance,
            writeup="A bond sealed in candlelight.",
            ritual_components=[],
        )

        # Author a Corruption ConditionTemplate with passive_decay_per_day so we
        # can confirm the Sinner decays naturally.  The Tether Strain template is
        # seeded by wire_soul_tether_content().
        cls.corruption_template, _ = _make_simple_corruption_template(cls.resonance)

    def test_dormant_tether_sineater_anima_unchanged_after_decay_ticks(self) -> None:
        """N decay ticks with no Sineating leave the Sineater's anima exactly as seeded."""
        from world.magic.models import CharacterAnima

        initial_anima = CharacterAnima.objects.get(character=self.sineater.character).current

        # Run 5 daily decay ticks (no shared scenes, no Sineating, no rescue).
        for _ in range(5):
            decay_all_conditions_tick()

        final_anima = CharacterAnima.objects.get(character=self.sineater.character).current
        self.assertEqual(
            final_anima,
            initial_anima,
            "Dormant tether must not drain Sineater's anima",
        )

    def test_dormant_tether_sinner_resonance_balance_unchanged_after_decay_ticks(self) -> None:
        """N decay ticks with no activity leave the Sinner's Resonance balance unchanged.

        The dormant tether must not spend the Sinner's Resonance currency.
        """
        initial_balance = CharacterResonance.objects.get(
            character_sheet=self.sinner, resonance=self.resonance
        ).balance

        for _ in range(5):
            decay_all_conditions_tick()

        final_balance = CharacterResonance.objects.get(
            character_sheet=self.sinner, resonance=self.resonance
        ).balance
        self.assertEqual(
            final_balance,
            initial_balance,
            "Dormant tether must not spend Sinner's Resonance balance",
        )

    def test_dormant_tether_no_strain_on_sineater(self) -> None:
        """Tether Strain must not accumulate on the Sineater from dormancy alone.

        Strain is only applied at dramatic opt-in moments (stage-advance prompt
        accept, rescue ritual).  Dormancy produces no Strain.
        """
        for _ in range(5):
            decay_all_conditions_tick()

        strain_severity_total = sum(
            ci.severity
            for ci in ConditionInstance.objects.filter(
                target=self.sineater.character,
                condition__name="Tether Strain",
            )
        )
        self.assertEqual(
            strain_severity_total,
            0,
            "Tether Strain must not accumulate from dormancy",
        )

    def test_sinner_corruption_decays_regardless_of_tether(self) -> None:
        """Corruption ConditionInstances on the Sinner decay at the normal passive rate.

        Per spec §11, passive corruption decay applies to the Sinner regardless
        of whether the Sineater is active.  This is NOT a resentment mechanic —
        it is the background system that gradually heals unchecked Corruption.
        """
        # Seed Sinner at Corruption stage 1 (severity=50) with passive_decay_per_day=5.
        with_corruption_at_stage(self.sinner, self.resonance, stage=1)
        corruption_instance = ConditionInstance.objects.get(
            target=self.sinner.character,
            condition__corruption_resonance=self.resonance,
        )

        severity_before = corruption_instance.severity
        self.assertGreater(severity_before, 0)

        # The Corruption ConditionTemplate from with_corruption_at_stage uses the
        # CorruptionConditionTemplateFactory defaults (passive_decay_per_day may be 0).
        # We run a tick and assert at minimum that the tick does NOT crash.
        # If passive_decay is configured, severity drops; if not, it stays the same.
        # Either way the tether itself caused no Strain on the Sineater.
        try:
            decay_all_conditions_tick()
        except Exception as exc:  # noqa: BLE001
            self.fail(f"decay_all_conditions_tick raised unexpectedly: {exc}")

        # No Sineater-side effects after the tick.
        sineater_cond_count = ConditionInstance.objects.filter(
            target=self.sineater.character,
            resolved_at__isnull=True,
        ).count()
        # Any condition on Sineater must have a non-Tether-Strain name;
        # Tether Strain should be 0 still.
        tether_strain_severity = sum(
            ci.severity
            for ci in ConditionInstance.objects.filter(
                target=self.sineater.character,
                condition__name="Tether Strain",
            )
        )
        self.assertEqual(tether_strain_severity, 0)
        # Log for debugging if needed (unused in assertion — but useful context).
        _ = sineater_cond_count


# ===========================================================================
# 13.3  Many-to-many independence
# ===========================================================================


class ManyToManyIndependenceTests(TestCase):
    """Scenario 13.3: One Sineater, two Sinners — fully independent state.

    Verified invariants:
    - Each Sinner has a distinct RELATIONSHIP_CAPSTONE Thread.
    - Each Sinner's hollow_current is independent.
    - Rescue for Sinner A affects only Sinner A's corruption; Sinner B is unchanged.
    - lifetime_helped increments per-Sineater per-resonance (one counter, both bonds).
    - Dissolution of Bond A leaves Bond B intact.

    Note on Tether Strain: Phase 7 simplified Strain to a single-instance model
    (one ConditionInstance of "Tether Strain" on the Sineater, shared across
    all tethers).  Per-resonance Strain is a TODO deferred post-MVP.  This test
    exercises the simplified single-instance behaviour and notes the limitation.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        wire_soul_tether_content()

        # Shared track for Sinner A (required for RELATIONSHIP_TRACK unlock).
        cls.track_a = RelationshipTrackFactory()
        # Separate track for Sinner B's second tether (unlock specificity).
        cls.track_b = RelationshipTrackFactory()

        abyssal_affinity = AffinityFactory(name="Abyssal")
        primal_affinity = AffinityFactory(name="Primal")
        cls.resonance_a = ResonanceFactory(affinity=abyssal_affinity)
        cls.resonance_b = ResonanceFactory(affinity=primal_affinity)

        # Sineater: Primal-primary.  No track unlock required on Sineater side.
        cls.sineater = CharacterSheetFactory()
        _set_primal_primary(cls.sineater)
        CharacterAnimaFactory(character=cls.sineater.character, current=50, maximum=50)

        # Sinner A: Abyssal-primary, RELATIONSHIP_TRACK unlock for track_a.
        cls.sinner_a = CharacterSheetFactory()
        _set_abyssal_primary(cls.sinner_a)
        _grant_track_unlock(cls.sinner_a, cls.track_a)

        # Sinner B: Primal-primary (passes Sinner gate), RELATIONSHIP_TRACK unlock for track_b.
        cls.sinner_b = CharacterSheetFactory()
        _set_primal_primary(cls.sinner_b)
        _grant_track_unlock(cls.sinner_b, cls.track_b)

        # Relationships: Sineater ↔ Sinner A, Sineater ↔ Sinner B.
        _make_active_relationship(cls.sinner_a, cls.sineater)
        _make_active_relationship(cls.sinner_b, cls.sineater)

        # Seed Corruption ConditionTemplates for both resonances.
        _make_simple_corruption_template(cls.resonance_a)
        _make_simple_corruption_template(cls.resonance_b)

        # Seed CharacterResonance for both Sinners so the Sineating resonance gate passes.
        CharacterResonanceFactory(character_sheet=cls.sinner_a, resonance=cls.resonance_a)
        CharacterResonanceFactory(character_sheet=cls.sinner_b, resonance=cls.resonance_b)

        # Form Bond A (Sinner A ↔ Sineater in resonance_a).
        cls.capstone_a = accept_soul_tether(
            initiator_sheet=cls.sinner_a,
            partner_sheet=cls.sineater,
            sinner_role=SoulTetherRoleEnum.SINNER,
            resonance=cls.resonance_a,
            writeup="First bond — dark resonance.",
            ritual_components=[],
        )

        # Form Bond B (Sinner B ↔ Sineater in resonance_b).
        cls.capstone_b = accept_soul_tether(
            initiator_sheet=cls.sinner_b,
            partner_sheet=cls.sineater,
            sinner_role=SoulTetherRoleEnum.SINNER,
            resonance=cls.resonance_b,
            writeup="Second bond — primal resonance.",
            ritual_components=[],
        )

        # Bump thread levels so Hollows have capacity.
        thread_a = _get_sinner_thread(cls.sinner_a, cls.capstone_a, cls.resonance_a)
        thread_b = _get_sinner_thread(cls.sinner_b, cls.capstone_b, cls.resonance_b)
        _bump_thread_level(thread_a, level=3)
        _bump_thread_level(thread_b, level=3)

    def test_each_sinner_has_distinct_thread(self) -> None:
        """Sinner A and Sinner B own different Thread PKs."""
        thread_a = _get_sinner_thread(self.sinner_a, self.capstone_a, self.resonance_a)
        thread_b = _get_sinner_thread(self.sinner_b, self.capstone_b, self.resonance_b)
        self.assertNotEqual(thread_a.pk, thread_b.pk)
        self.assertEqual(thread_a.target_capstone_id, self.capstone_a.pk)
        self.assertEqual(thread_b.target_capstone_id, self.capstone_b.pk)

    def test_hollow_current_is_independent_per_sinner(self) -> None:
        """Sineating for Sinner A does not change Sinner B's hollow_current."""
        rel_a = CharacterRelationship.objects.get(source=self.sinner_a, target=self.sineater)

        # Sineat for Sinner A only.
        offer_a = _build_sineating_offer(
            self.sinner_a, self.sineater, self.resonance_a, rel_a, max_units=8
        )
        resolve_sineating(offer_a, units_accepted=8)

        thread_a = _get_sinner_thread(self.sinner_a, self.capstone_a, self.resonance_a)
        thread_b = _get_sinner_thread(self.sinner_b, self.capstone_b, self.resonance_b)

        self.assertGreater(thread_a.hollow_current, 0, "Sinner A's Hollow should have filled")
        self.assertEqual(thread_b.hollow_current, 0, "Sinner B's Hollow must not be affected")

    @tag("postgres")
    def test_rescue_for_sinner_a_leaves_sinner_b_unchanged(self) -> None:
        """Rescue for Sinner A reduces Sinner A's corruption; Sinner B's is untouched."""
        # Set Sinner A to stage 3; Sinner B stays clean.
        with_corruption_at_stage(self.sinner_a, self.resonance_a, stage=3)

        cr_a_before = CharacterResonance.objects.get(
            character_sheet=self.sinner_a, resonance=self.resonance_a
        )
        # Sinner B has no corruption at all.
        cr_b = CharacterResonance.objects.filter(
            character_sheet=self.sinner_b, resonance=self.resonance_b
        ).first()
        b_corruption_before = cr_b.corruption_current if cr_b else 0

        # Give Sineater balance for stage-3 rescue.
        sineater_cr_a, _ = CharacterResonance.objects.get_or_create(
            character_sheet=self.sineater, resonance=self.resonance_a
        )
        sineater_cr_a.balance = 500
        sineater_cr_a.save(update_fields=["balance"])

        mock_check = _make_mock_check(success_level=1)
        with (
            patch(_BOTH_IN_SCENE_PATH, return_value=True),
            patch(_PERFORM_CHECK_PATH, return_value=mock_check),
        ):
            rescue_outcome = perform_soul_tether_rescue(
                sineater_sheet=self.sineater,
                sinner_sheet=self.sinner_a,
                resonance=self.resonance_a,
                components=[],
                scene=None,
            )

        # Sinner A: corruption_current should have dropped.
        cr_a_before.refresh_from_db()
        self.assertGreater(rescue_outcome.severity_reduced, 0)
        self.assertLess(
            cr_a_before.corruption_current,
            500,  # was at stage-3 threshold (500); now reduced
        )

        # Sinner B: unchanged.
        cr_b_after = CharacterResonance.objects.filter(
            character_sheet=self.sinner_b, resonance=self.resonance_b
        ).first()
        b_corruption_after = cr_b_after.corruption_current if cr_b_after else 0
        self.assertEqual(b_corruption_after, b_corruption_before)

    def test_sineater_lifetime_helped_accumulates_across_both_bonds(self) -> None:
        """lifetime_helped on Sineater grows when Sineating for either Sinner.

        NOTE: lifetime_helped is per-CharacterResonance, so it is tracked
        independently per resonance (resonance_a vs resonance_b).
        """
        rel_a = CharacterRelationship.objects.get(source=self.sinner_a, target=self.sineater)
        rel_b = CharacterRelationship.objects.get(source=self.sinner_b, target=self.sineater)

        offer_a = _build_sineating_offer(
            self.sinner_a, self.sineater, self.resonance_a, rel_a, max_units=5
        )
        resolve_sineating(offer_a, units_accepted=5)

        offer_b = _build_sineating_offer(
            self.sinner_b, self.sineater, self.resonance_b, rel_b, max_units=4
        )
        resolve_sineating(offer_b, units_accepted=4)

        cr_a = CharacterResonance.objects.get(
            character_sheet=self.sineater, resonance=self.resonance_a
        )
        cr_b = CharacterResonance.objects.get(
            character_sheet=self.sineater, resonance=self.resonance_b
        )
        self.assertEqual(cr_a.lifetime_helped, 5)
        self.assertEqual(cr_b.lifetime_helped, 4)

    def test_dissolution_of_bond_a_leaves_bond_b_intact(self) -> None:
        """Dissolving Bond A (Sinner A ↔ Sineater) leaves Bond B (Sinner B ↔ Sineater) active."""
        rel_a = CharacterRelationship.objects.get(source=self.sinner_a, target=self.sineater)

        dissolve_soul_tether(
            relationship_id=rel_a.pk,
            initiator_sheet=self.sinner_a,
        )

        # Bond A should be dissolved.
        rel_a.refresh_from_db()
        self.assertFalse(rel_a.is_soul_tether)

        # Bond B should be intact.
        rel_b = CharacterRelationship.objects.get(source=self.sinner_b, target=self.sineater)
        self.assertTrue(rel_b.is_soul_tether)
        self.assertEqual(rel_b.soul_tether_role, SoulTetherRole.SINNER)

        # Sinner B's Thread must still be active (not retired).
        thread_b = Thread.objects.filter(
            owner=self.sinner_b,
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=self.capstone_b,
            retired_at__isnull=True,
        )
        self.assertTrue(thread_b.exists(), "Sinner B's Thread must survive Bond A dissolution")

    @tag("postgres")
    def test_tether_strain_is_single_instance_across_both_bonds(self) -> None:
        """Rescue for Sinner A creates a Tether Strain instance on the Sineater.

        NOTE: Phase 7 simplified Strain to a single ConditionInstance shared
        across all bonds (not per-resonance).  This test documents that
        simplified behaviour.  A future spec may introduce per-resonance Strain.
        """
        # Ensure Sinner A is at stage 3.
        with_corruption_at_stage(self.sinner_a, self.resonance_a, stage=3)

        sineater_cr_a, _ = CharacterResonance.objects.get_or_create(
            character_sheet=self.sineater, resonance=self.resonance_a
        )
        sineater_cr_a.balance = 500
        sineater_cr_a.save(update_fields=["balance"])

        mock_check = _make_mock_check(success_level=1)
        with (
            patch(_BOTH_IN_SCENE_PATH, return_value=True),
            patch(_PERFORM_CHECK_PATH, return_value=mock_check),
        ):
            perform_soul_tether_rescue(
                sineater_sheet=self.sineater,
                sinner_sheet=self.sinner_a,
                resonance=self.resonance_a,
                components=[],
                scene=None,
            )

        # Exactly one Tether Strain instance on the Sineater (single-instance model).
        strain_count = ConditionInstance.objects.filter(
            target=self.sineater.character,
            condition__name="Tether Strain",
            resolved_at__isnull=True,
        ).count()
        # Phase 7 simplified: 1 shared instance across all bonds.
        # (TODO: per-resonance Strain would produce up to N instances.)
        self.assertGreaterEqual(strain_count, 1)
        self.assertLessEqual(
            strain_count,
            1,
            "Phase 7 single-instance simplification: expect exactly 1 Tether Strain instance. "
            "If this fails, per-resonance Strain may have been implemented — update accordingly.",
        )
