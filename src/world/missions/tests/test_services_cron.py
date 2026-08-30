"""Tests for ``apply_mission_reward_batch`` (Phase 5b.2).

The cron walks unapplied :class:`MissionRewardQueue` rows and tries to grant
each one downstream. One POST_CRON sink remains stub-sealed; the other is
now a real grant (#1737):

  * ``LEGEND_POINTS`` — the LP grant entry point requires a richer line
    shape (persona walk + LegendSourceType + title) than Phase 5b.1's queue
    rows carry; the helper raises ``NotImplementedError`` with a
    DESIGN §13.3 reference. Cron catches, populates ``failure_reason``,
    leaves ``applied=False``. Still stub-sealed — out of scope for #1737.
  * ``RESONANCE`` — implemented (#1737): resolves the line recipient's
    ``CharacterSheet`` and calls the real ``grant_resonance()`` with
    ``source=GainSource.MISSION_REWARD``. A row with a valid recipient +
    resonance now succeeds and flips ``applied=True``.

A defensive ``MissionRewardRoutingError`` arm catches any other
``(kind, sink)`` pair that shouldn't be on the queue at all (should never
fire since ``apply_deed_rewards`` only enqueues the two POST_CRON sinks).

Per-row :func:`transaction.atomic` keeps a fault on row N from corrupting
row N-1's or row N+1's state. Idempotency for LEGEND_POINTS still holds
because no such row ever flips to ``applied=True``. Idempotency for
RESONANCE holds because a granted row flips ``applied=True`` and the
batch only ever selects ``applied=False`` rows, so a second run can't
double-grant it.
"""

from dataclasses import FrozenInstanceError

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionDeedRewardLineFactory,
    MissionRewardQueueFactory,
)
from world.missions.models import MissionRewardQueue
from world.missions.services.cron import apply_mission_reward_batch
from world.missions.types import RewardBatchResult


class ApplyMissionRewardBatchEmptyTests(TestCase):
    """The batch returns empty tuples when no unapplied rows exist."""

    def test_empty_queue_returns_empty_result(self) -> None:
        result = apply_mission_reward_batch()
        self.assertEqual(result.applied, ())
        self.assertEqual(result.failed, ())

    def test_only_applied_rows_returns_empty_result(self) -> None:
        actor = CharacterSheetFactory(character__db_key="OnlyAppliedActor").character
        deed = MissionDeedRecordFactory(actor=actor.sheet_data)
        line = MissionDeedRewardLineFactory(
            deed=deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=5,
        )
        MissionRewardQueueFactory(line=line, applied=True)

        result = apply_mission_reward_batch()
        self.assertEqual(result.applied, ())
        self.assertEqual(result.failed, ())


class ApplyMissionRewardBatchLegendPointsTests(TestCase):
    """LP queue rows pay priced Legend and flip applied (#3468).

    Replaces ApplyMissionRewardBatchLegendPointsStubSealTests, which asserted
    the sealed state — a row that failed every pass with a DESIGN §13.3 trace
    and never paid. That was the bug, not the contract.
    """

    def _row(self, *, risk_tier: int, amount: int, level: int = 3, band_max: int = 3):
        from world.classes.factories import CharacterClassLevelFactory

        actor = CharacterSheetFactory(
            character__db_key=f"LpActor{risk_tier}{amount}{level}{band_max}"
        )
        CharacterClassLevelFactory(character=actor, level=level, is_primary=True)
        deed = MissionDeedRecordFactory(actor=actor)
        # level_band_max is the THREAT LEVEL — the character level the mission
        # was written for. risk_tier is how dangerous it is. Different scales.
        deed.instance.template.risk_tier = risk_tier
        deed.instance.template.level_band_min = max(1, band_max - 1)
        deed.instance.template.level_band_max = band_max
        deed.instance.template.save(update_fields=["risk_tier", "level_band_min", "level_band_max"])
        line = MissionDeedRewardLineFactory(
            deed=deed,
            recipient=actor,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=amount,
        )
        return MissionRewardQueueFactory(line=line), actor

    def test_dangerous_mission_mints_a_deed_stamped_at_station(self) -> None:
        from world.societies.models import LegendEntry

        row, actor = self._row(risk_tier=5, amount=5_000, level=3)
        result = apply_mission_reward_batch()

        self.assertEqual(len(result.applied), 1)
        row.refresh_from_db()
        self.assertTrue(row.applied)
        self.assertIsNotNone(row.applied_at)
        entry = LegendEntry.objects.get(persona=actor.primary_persona)
        # Station is min(level 3, tier 5) = 3.
        self.assertEqual(entry.earned_at_level, 3)
        self.assertGreater(entry.base_value, 0)

    def test_declared_amount_caps_the_priced_value(self) -> None:
        """line.amount is the author's ceiling, not the payout (ADR-0249)."""
        from world.societies.models import LegendEntry

        row, actor = self._row(risk_tier=5, amount=7, level=3)
        apply_mission_reward_batch()
        row.refresh_from_db()
        self.assertTrue(row.applied)
        entry = LegendEntry.objects.get(persona=actor.primary_persona)
        self.assertEqual(entry.base_value, 7)

    def test_safe_mission_applies_the_row_and_mints_nothing(self) -> None:
        """The regression guard for this whole issue.

        A tier-1 mission is below the Legend floor, so it pays nothing. The row
        must still flip applied — "correctly priced to zero" is a settled
        outcome, not a fault. Leaving it unapplied would recreate the bug
        #3468 fixed, in a new disguise: a row failing forever, silently.
        """
        from world.societies.models import LegendEntry

        row, actor = self._row(risk_tier=1, amount=5_000, level=3)
        result = apply_mission_reward_batch()

        self.assertEqual(len(result.applied), 1)
        self.assertEqual(result.failed, ())
        row.refresh_from_db()
        self.assertTrue(row.applied)
        self.assertFalse(LegendEntry.objects.filter(persona=actor.primary_persona).exists())

    def test_overlevelled_earner_applies_the_row_and_mints_nothing(self) -> None:
        """Same rule from the other direction: a tier-4 run is no danger at 20."""
        from world.societies.models import LegendEntry

        # Mission banded for level 4; the earner is level 20. compute_effective_risk
        # decays HIGH far below the floor at that gap, so they earn nothing.
        row, actor = self._row(risk_tier=4, amount=5_000, level=20, band_max=4)
        apply_mission_reward_batch()
        row.refresh_from_db()
        self.assertTrue(row.applied)
        self.assertFalse(LegendEntry.objects.filter(persona=actor.primary_persona).exists())

    def test_lp_row_count_unchanged(self) -> None:
        self._row(risk_tier=5, amount=25)
        before = MissionRewardQueue.objects.count()
        apply_mission_reward_batch()
        self.assertEqual(MissionRewardQueue.objects.count(), before)


class ApplyMissionRewardBatchMixedQueueTests(TestCase):
    """Mixed queue: applied rows are skipped; only unapplied rows are touched.

    "Mixed" also covers mixed per-row *outcomes* now that RESONANCE grants
    for real (#1737): the LP row fails (stub-sealed) while the RESONANCE
    row — given a recipient with a linked CharacterSheet + a real Resonance
    — succeeds. Both are still processed (i.e. "touched"); only the
    pre-applied row is skipped.
    """

    def setUp(self) -> None:
        from world.magic.factories import ResonanceFactory

        sheet = CharacterSheetFactory(character__db_key="MixedBatchActor")
        self.actor = sheet.character
        self.deed = MissionDeedRecordFactory(actor=self.actor.sheet_data)
        self.lp_line = MissionDeedRewardLineFactory(
            deed=self.deed,
            recipient=self.actor.sheet_data,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=10,
        )
        self.resonance = ResonanceFactory()
        self.resonance_line = MissionDeedRewardLineFactory(
            deed=self.deed,
            recipient=self.actor.sheet_data,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            resonance=self.resonance,
            amount=2,
        )
        self.applied_line = MissionDeedRewardLineFactory(
            deed=self.deed,
            recipient=self.actor.sheet_data,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=1,
        )
        self.lp_row = MissionRewardQueueFactory(line=self.lp_line)
        self.resonance_row = MissionRewardQueueFactory(line=self.resonance_line)
        # Pre-applied row that the batch must not touch.
        self.applied_row = MissionRewardQueueFactory(
            line=self.applied_line,
            applied=True,
        )
        self.applied_row.failure_reason = "preserved"
        self.applied_row.save()

    def test_batch_touches_only_unapplied_rows(self) -> None:
        result = apply_mission_reward_batch()
        touched_ids = {row.pk for row in result.applied} | {row.pk for row in result.failed}
        self.assertEqual(touched_ids, {self.lp_row.pk, self.resonance_row.pk})
        # #3468: both sinks now succeed. LP used to stub-seal into result.failed;
        # a tier-1 mission prices its Legend to zero, which is a SETTLED outcome
        # and applies the row rather than failing it.
        self.assertEqual(result.failed, ())
        self.assertEqual(
            {row.pk for row in result.applied}, {self.lp_row.pk, self.resonance_row.pk}
        )

    def test_pre_applied_row_is_not_reprocessed(self) -> None:
        apply_mission_reward_batch()
        self.applied_row.refresh_from_db()
        self.assertTrue(self.applied_row.applied)
        # Untouched — its prior failure_reason is preserved verbatim.
        self.assertEqual(self.applied_row.failure_reason, "preserved")


class ApplyMissionRewardBatchIdempotencyTests(TestCase):
    """Running the batch twice produces the same state.

    LEGEND_POINTS stays stub-sealed, so no LP row ever flips to
    ``applied=True``; both runs re-select and re-fail it the same way.
    RESONANCE now grants for real (#1737), so its idempotency guarantee is
    different: the row flips to ``applied=True`` on the first run and the
    ``applied=False`` filter then excludes it from the second run entirely
    — it is not reprocessed and the resonance is not double-granted.
    """

    def setUp(self) -> None:
        from world.magic.factories import ResonanceFactory
        from world.magic.models import CharacterResonance

        self._CharacterResonance = CharacterResonance

        sheet = CharacterSheetFactory(character__db_key="IdempotentBatchActor")
        self.actor = sheet.character
        self.deed = MissionDeedRecordFactory(actor=self.actor.sheet_data)
        self.lp_line = MissionDeedRewardLineFactory(
            deed=self.deed,
            recipient=self.actor.sheet_data,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=10,
        )
        self.resonance = ResonanceFactory()
        self.resonance_line = MissionDeedRewardLineFactory(
            deed=self.deed,
            recipient=self.actor.sheet_data,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            resonance=self.resonance,
            amount=2,
        )
        self.lp_row = MissionRewardQueueFactory(line=self.lp_line)
        self.resonance_row = MissionRewardQueueFactory(line=self.resonance_line)

    def test_double_run_applies_both_sinks_once(self) -> None:
        """#3468: idempotency is now uniform. LP rows used to never flip.

        Before, an LP row was re-selected and re-failed on every pass forever,
        which is what made the missing payout invisible.
        """
        apply_mission_reward_batch()
        apply_mission_reward_batch()
        self.lp_row.refresh_from_db()
        self.resonance_row.refresh_from_db()
        self.assertTrue(self.lp_row.applied)
        self.assertTrue(self.resonance_row.applied)

    def test_double_run_does_not_duplicate_rows(self) -> None:
        before = MissionRewardQueue.objects.count()
        apply_mission_reward_batch()
        apply_mission_reward_batch()
        self.assertEqual(MissionRewardQueue.objects.count(), before)

    def test_double_run_does_not_double_grant_resonance(self) -> None:
        apply_mission_reward_batch()
        apply_mission_reward_batch()
        cr = self._CharacterResonance.objects.get(
            character_sheet=self.resonance_line.recipient,
            resonance=self.resonance,
        )
        self.assertEqual(cr.balance, 2)
        self.assertEqual(cr.lifetime_earned, 2)


class ApplyMissionRewardBatchPerRowAtomicityTests(TestCase):
    """A fault on one row does not corrupt the state of other rows."""

    def setUp(self) -> None:
        self.actor = CharacterSheetFactory(character__db_key="AtomicBatchActor").character
        self.deed = MissionDeedRecordFactory(actor=self.actor.sheet_data)
        self.line_a = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=1,
        )
        self.line_b = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=2,
        )
        self.line_c = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=3,
        )
        # Queue rows in pk order so the middle one corresponds to line_b.
        self.row_a = MissionRewardQueueFactory(line=self.line_a)
        self.row_b = MissionRewardQueueFactory(line=self.line_b)
        self.row_c = MissionRewardQueueFactory(line=self.line_c)

    def test_unexpected_exception_on_middle_row_does_not_block_others(self) -> None:
        from world.missions.services import cron as cron_module

        original = cron_module._grant_legend_points
        call_count = {"n": 0}
        boom_pk = self.row_b.pk
        boom_msg = "boom-on-row-b"

        def faulty(row):  # type: ignore[no-untyped-def]
            # ``row`` is a MissionRewardQueue (the helper parameter is now
            # consistently named ``row`` across the cron helpers), not the
            # deed reward line — ``row.line_id`` is the FK to the underlying
            # MissionDeedRewardLine row we want to target.
            call_count["n"] += 1
            if row.line_id == self.line_b.pk:
                raise RuntimeError(boom_msg)
            return original(row)

        try:
            cron_module._grant_legend_points = faulty
            result = apply_mission_reward_batch()
        finally:
            cron_module._grant_legend_points = original

        # #3468: only the row that actually raised fails. A and C used to fail
        # too, because every LP row raised the stub-seal NotImplementedError —
        # which meant this test proved per-row atomicity using three failures
        # where only one was a real fault. Now it proves the sharper thing: a
        # genuine exception on the middle row does not block its neighbours.
        failed_pks = {row.pk for row in result.failed}
        self.assertEqual(failed_pks, {boom_pk})
        self.assertEqual({row.pk for row in result.applied}, {self.row_a.pk, self.row_c.pk})

        # Per-row atomicity: A and C applied cleanly on either side of B's
        # raise, and only B carries a failure reason.
        self.row_a.refresh_from_db()
        self.row_b.refresh_from_db()
        self.row_c.refresh_from_db()
        self.assertTrue(self.row_a.applied)
        self.assertFalse(self.row_b.applied)
        self.assertTrue(self.row_c.applied)
        self.assertEqual(self.row_a.failure_reason, "")
        self.assertEqual(self.row_c.failure_reason, "")
        self.assertIn(boom_msg, self.row_b.failure_reason)


class ApplyMissionRewardBatchResonanceGrantTests(TestCase):
    """Resonance grant applies successfully and updates CharacterResonance."""

    def test_grant_resonance_applies_and_flips_queue_row(self) -> None:
        from world.magic.factories import ResonanceFactory
        from world.magic.models import CharacterResonance

        sheet = CharacterSheetFactory(character__db_key="ResonanceGrantActor")
        actor = sheet.character
        deed = MissionDeedRecordFactory(actor=actor.sheet_data)
        resonance = ResonanceFactory()
        line = MissionDeedRewardLineFactory(
            deed=deed,
            recipient=actor.sheet_data,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            resonance=resonance,
            amount=25,
        )
        row = MissionRewardQueueFactory(line=line)

        result = apply_mission_reward_batch()

        row.refresh_from_db()
        self.assertTrue(row.applied)
        self.assertEqual(row.failure_reason, "")
        cr = CharacterResonance.objects.get(character_sheet=line.recipient, resonance=resonance)
        self.assertEqual(cr.balance, 25)
        self.assertEqual(cr.lifetime_earned, 25)
        self.assertIn(row, result.applied)


class ApplyMissionRewardBatchResultShapeTests(TestCase):
    """The result is a frozen :class:`RewardBatchResult` carrying tuples."""

    def test_result_is_frozen_dataclass_with_tuples(self) -> None:
        actor = CharacterSheetFactory(character__db_key="ShapeBatchActor").character
        deed = MissionDeedRecordFactory(actor=actor.sheet_data)
        line = MissionDeedRewardLineFactory(
            deed=deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=1,
        )
        MissionRewardQueueFactory(line=line)

        result = apply_mission_reward_batch()
        self.assertIsInstance(result, RewardBatchResult)
        self.assertIsInstance(result.applied, tuple)
        self.assertIsInstance(result.failed, tuple)
        with self.assertRaises(FrozenInstanceError):
            result.applied = ()  # type: ignore[misc]
