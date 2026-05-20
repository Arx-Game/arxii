"""Tests for ``apply_mission_reward_batch`` (Phase 5b.2).

The cron walks unapplied :class:`MissionRewardQueue` rows and tries to grant
each one downstream. Phase 5b.2 stub-seals both POST_CRON sinks:

  * ``LEGEND_POINTS`` — the LP grant entry point requires a richer line
    shape (persona walk + LegendSourceType + title) than Phase 5b.1's queue
    rows carry; the helper raises ``NotImplementedError`` with a
    DESIGN §13.3 reference. Cron catches, populates ``failure_reason``,
    leaves ``applied=False``.
  * ``RESONANCE`` — the resonance grant requires a Resonance FK plus a
    ``MISSION_REWARD`` ``GainSource`` value that does not yet exist; same
    stub-seal pattern as LP.

A defensive ``MissionRewardRoutingError`` arm catches any other
``(kind, sink)`` pair that shouldn't be on the queue at all (should never
fire since ``apply_deed_rewards`` only enqueues the two POST_CRON sinks).

Per-row :func:`transaction.atomic` keeps a fault on row N from corrupting
row N-1's or row N+1's state. Idempotency holds because no row gets
flipped to ``applied=True`` in 5b.2 — every run touches the same set.
"""

from dataclasses import FrozenInstanceError

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
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
        actor = CharacterFactory(db_key="OnlyAppliedActor")
        deed = MissionDeedRecordFactory(actor=actor)
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


class ApplyMissionRewardBatchLegendPointsStubSealTests(TestCase):
    """LP queue rows stub-seal: applied=False, failure_reason references DESIGN §13.3."""

    def setUp(self) -> None:
        self.actor = CharacterFactory(db_key="LpBatchActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)
        self.line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=25,
        )
        self.row = MissionRewardQueueFactory(line=self.line)

    def test_lp_row_remains_unapplied_after_batch(self) -> None:
        result = apply_mission_reward_batch()
        self.assertEqual(result.applied, ())
        self.assertEqual(len(result.failed), 1)
        self.row.refresh_from_db()
        self.assertFalse(self.row.applied)
        self.assertIsNone(self.row.applied_at)

    def test_lp_failure_reason_mentions_design_and_lp(self) -> None:
        apply_mission_reward_batch()
        self.row.refresh_from_db()
        self.assertIn("DESIGN", self.row.failure_reason)
        self.assertIn("13.3", self.row.failure_reason)
        self.assertIn("LP", self.row.failure_reason)

    def test_lp_row_count_unchanged(self) -> None:
        before = MissionRewardQueue.objects.count()
        apply_mission_reward_batch()
        self.assertEqual(MissionRewardQueue.objects.count(), before)


class ApplyMissionRewardBatchResonanceStubSealTests(TestCase):
    """Resonance queue rows stub-seal with the same pattern as LP."""

    def setUp(self) -> None:
        self.actor = CharacterFactory(db_key="ResonanceBatchActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)
        self.line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=8,
        )
        self.row = MissionRewardQueueFactory(line=self.line)

    def test_resonance_row_remains_unapplied(self) -> None:
        result = apply_mission_reward_batch()
        self.assertEqual(result.applied, ())
        self.assertEqual(len(result.failed), 1)
        self.row.refresh_from_db()
        self.assertFalse(self.row.applied)
        self.assertIsNone(self.row.applied_at)

    def test_resonance_failure_reason_mentions_design_and_resonance(self) -> None:
        apply_mission_reward_batch()
        self.row.refresh_from_db()
        self.assertIn("DESIGN", self.row.failure_reason)
        self.assertIn("13.3", self.row.failure_reason)
        self.assertIn("Resonance", self.row.failure_reason)


class ApplyMissionRewardBatchMixedQueueTests(TestCase):
    """Mixed queue: applied rows are skipped; only unapplied rows are touched."""

    def setUp(self) -> None:
        self.actor = CharacterFactory(db_key="MixedBatchActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)
        self.lp_line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=10,
        )
        self.resonance_line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=2,
        )
        self.applied_line = MissionDeedRewardLineFactory(
            deed=self.deed,
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
        failed_ids = {row.pk for row in result.failed}
        self.assertEqual(failed_ids, {self.lp_row.pk, self.resonance_row.pk})

    def test_pre_applied_row_is_not_reprocessed(self) -> None:
        apply_mission_reward_batch()
        self.applied_row.refresh_from_db()
        self.assertTrue(self.applied_row.applied)
        # Untouched — its prior failure_reason is preserved verbatim.
        self.assertEqual(self.applied_row.failure_reason, "preserved")


class ApplyMissionRewardBatchIdempotencyTests(TestCase):
    """Running the batch twice produces the same state.

    Since no row ever flips to ``applied=True`` in 5b.2, both runs touch
    the same rows; ``applied`` stays False and ``failure_reason`` stays
    populated. The state is stable across runs.
    """

    def setUp(self) -> None:
        self.actor = CharacterFactory(db_key="IdempotentBatchActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)
        self.lp_line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=10,
        )
        self.resonance_line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=2,
        )
        self.lp_row = MissionRewardQueueFactory(line=self.lp_line)
        self.resonance_row = MissionRewardQueueFactory(line=self.resonance_line)

    def test_double_run_keeps_applied_false(self) -> None:
        apply_mission_reward_batch()
        apply_mission_reward_batch()
        self.lp_row.refresh_from_db()
        self.resonance_row.refresh_from_db()
        self.assertFalse(self.lp_row.applied)
        self.assertFalse(self.resonance_row.applied)

    def test_double_run_does_not_duplicate_rows(self) -> None:
        before = MissionRewardQueue.objects.count()
        apply_mission_reward_batch()
        apply_mission_reward_batch()
        self.assertEqual(MissionRewardQueue.objects.count(), before)


class ApplyMissionRewardBatchPerRowAtomicityTests(TestCase):
    """A fault on one row does not corrupt the state of other rows."""

    def setUp(self) -> None:
        self.actor = CharacterFactory(db_key="AtomicBatchActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)
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

        def faulty(queue_row):  # type: ignore[no-untyped-def]
            # ``queue_row`` is a MissionRewardQueue (the helper signature),
            # not the deed reward line — ``queue_row.line_id`` is the FK to
            # the underlying MissionDeedRewardLine row we want to target.
            call_count["n"] += 1
            if queue_row.line_id == self.line_b.pk:
                raise RuntimeError(boom_msg)
            return original(queue_row)

        try:
            cron_module._grant_legend_points = faulty
            result = apply_mission_reward_batch()
        finally:
            cron_module._grant_legend_points = original

        # All three should appear in result.failed (each was caught).
        failed_pks = {row.pk for row in result.failed}
        self.assertEqual(failed_pks, {self.row_a.pk, boom_pk, self.row_c.pk})

        # Per-row atomicity: rows A and C have a DESIGN-flavoured failure
        # reason; row B has the RuntimeError surfaced as its failure reason.
        self.row_a.refresh_from_db()
        self.row_b.refresh_from_db()
        self.row_c.refresh_from_db()
        self.assertFalse(self.row_a.applied)
        self.assertFalse(self.row_b.applied)
        self.assertFalse(self.row_c.applied)
        self.assertIn("DESIGN", self.row_a.failure_reason)
        self.assertIn("DESIGN", self.row_c.failure_reason)
        self.assertIn(boom_msg, self.row_b.failure_reason)


class ApplyMissionRewardBatchResultShapeTests(TestCase):
    """The result is a frozen :class:`RewardBatchResult` carrying tuples."""

    def test_result_is_frozen_dataclass_with_tuples(self) -> None:
        actor = CharacterFactory(db_key="ShapeBatchActor")
        deed = MissionDeedRecordFactory(actor=actor)
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
