"""Tests for ``apply_deed_rewards`` (Phase 5b.1).

Routes already-emitted :class:`MissionDeedRewardLine` rows on a deed to the
correct downstream by ``(kind, sink)``:

  * IMMEDIATE / MONEY        → money_stub records the call
  * POST_CRON / LEGEND_POINTS → MissionRewardQueue row (applied=False)
  * POST_CRON / RESONANCE     → MissionRewardQueue row (applied=False)
  * PROPAGATION / RUMOR       → rumor_stub raises NotImplementedError
  * PROPAGATION / CRIME_WATCH → crime_watch_stub raises NotImplementedError
  * (*, BEAT)                 → beat_stub records (5b.3 will wire it)
  * Any other (kind, sink)    → MissionRewardRoutingError

The whole apply is transactional: if the rumor/crime-watch stub raises,
queue rows enqueued earlier in the same call must be rolled back. Calling
``apply_deed_rewards`` twice on the same deed is idempotent — one queue row
per line is the invariant (UniqueConstraint(line) + update_or_create).
"""

from dataclasses import FrozenInstanceError

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionDeedRewardLineFactory,
)
from world.missions.integrations import beat_stub, money_stub
from world.missions.models import MissionRewardQueue
from world.missions.services import apply_deed_rewards
from world.missions.services.rewards import MissionRewardRoutingError


class ApplyDeedRewardsQueueingTests(TestCase):
    """POST_CRON lines enqueue onto MissionRewardQueue."""

    def setUp(self) -> None:
        money_stub.clear_calls()
        beat_stub.clear_calls()
        self.actor = CharacterFactory(db_key="QueueApplyActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)

    def test_post_cron_legend_points_enqueues(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=25,
        )
        result = apply_deed_rewards(self.deed)
        self.assertEqual(len(result.enqueued), 1)
        row = result.enqueued[0]
        self.assertEqual(row.line, line)
        self.assertEqual(row.deed, self.deed)
        self.assertEqual(row.kind, DeedRewardKind.POST_CRON)
        self.assertEqual(row.sink, DeedRewardSink.LEGEND_POINTS)
        self.assertFalse(row.applied)
        self.assertEqual(MissionRewardQueue.objects.filter(deed=self.deed).count(), 1)

    def test_post_cron_resonance_enqueues(self) -> None:
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=8,
        )
        result = apply_deed_rewards(self.deed)
        self.assertEqual(len(result.enqueued), 1)
        self.assertEqual(result.enqueued[0].sink, DeedRewardSink.RESONANCE)


class ApplyDeedRewardsStubCallsTests(TestCase):
    """IMMEDIATE/MONEY and BEAT call stub seams (recording, no DB writes)."""

    def setUp(self) -> None:
        money_stub.clear_calls()
        beat_stub.clear_calls()
        self.actor = CharacterFactory(db_key="StubApplyActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)

    def test_immediate_money_calls_money_stub(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=100,
        )
        result = apply_deed_rewards(self.deed)
        self.assertEqual(result.enqueued, ())
        calls = money_stub.get_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].line_id, line.pk)
        self.assertEqual(MissionRewardQueue.objects.filter(deed=self.deed).count(), 0)

    def test_beat_sink_calls_beat_stub_for_each_kind(self) -> None:
        # BEAT can ride on any kind; Phase 5b.1 routes all three at the stub
        # (5b.3 will replace this with real Beat-completion wiring).
        kinds = [
            DeedRewardKind.IMMEDIATE,
            DeedRewardKind.POST_CRON,
            DeedRewardKind.PROPAGATION,
        ]
        for kind in kinds:
            MissionDeedRewardLineFactory(deed=self.deed, kind=kind, sink=DeedRewardSink.BEAT)
        result = apply_deed_rewards(self.deed)
        self.assertEqual(result.enqueued, ())
        self.assertEqual(len(beat_stub.get_calls()), 3)


class ApplyDeedRewardsPropagationFailuresTests(TestCase):
    """RUMOR/CRIME_WATCH stubs raise; the whole apply rolls back."""

    def setUp(self) -> None:
        money_stub.clear_calls()
        beat_stub.clear_calls()
        self.actor = CharacterFactory(db_key="PropApplyActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)

    def test_propagation_rumor_raises_not_implemented(self) -> None:
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.PROPAGATION,
            sink=DeedRewardSink.RUMOR,
            ref="r1",
        )
        with self.assertRaises(NotImplementedError):
            apply_deed_rewards(self.deed)

    def test_propagation_crime_watch_raises_not_implemented(self) -> None:
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.PROPAGATION,
            sink=DeedRewardSink.CRIME_WATCH,
            ref="c1",
        )
        with self.assertRaises(NotImplementedError):
            apply_deed_rewards(self.deed)

    def test_rumor_failure_rolls_back_prior_queue_rows(self) -> None:
        # An ordered apply: a POST_CRON line that would enqueue, then a RUMOR
        # line that raises. The whole call must roll back — no queue rows
        # persisted.
        # Lines are ordered by pk (creation order), so create the queueable
        # line first and the failing line second.
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=10,
        )
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.PROPAGATION,
            sink=DeedRewardSink.RUMOR,
            ref="r2",
        )
        with self.assertRaises(NotImplementedError):
            apply_deed_rewards(self.deed)
        self.assertEqual(MissionRewardQueue.objects.filter(deed=self.deed).count(), 0)


class ApplyDeedRewardsUnsupportedComboTests(TestCase):
    """Author-error (kind, sink) combos raise MissionRewardRoutingError."""

    def setUp(self) -> None:
        money_stub.clear_calls()
        beat_stub.clear_calls()
        self.actor = CharacterFactory(db_key="UnsupportedApplyActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)

    def test_immediate_legend_points_raises_routing_error(self) -> None:
        # LP is POST_CRON-only; IMMEDIATE/LEGEND_POINTS is an author error.
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=1,
        )
        with self.assertRaises(MissionRewardRoutingError):
            apply_deed_rewards(self.deed)

    def test_immediate_resonance_raises_routing_error(self) -> None:
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.RESONANCE,
            amount=1,
        )
        with self.assertRaises(MissionRewardRoutingError):
            apply_deed_rewards(self.deed)

    def test_post_cron_money_raises_routing_error(self) -> None:
        # MONEY is IMMEDIATE-only; POST_CRON/MONEY is an author error.
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.MONEY,
            amount=1,
        )
        with self.assertRaises(MissionRewardRoutingError):
            apply_deed_rewards(self.deed)

    def test_immediate_rumor_raises_routing_error(self) -> None:
        # RUMOR/CRIME_WATCH are PROPAGATION-only.
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.RUMOR,
        )
        with self.assertRaises(MissionRewardRoutingError):
            apply_deed_rewards(self.deed)


class ApplyDeedRewardsIdempotencyTests(TestCase):
    """Calling apply twice produces the same queue rows (no duplicates)."""

    def setUp(self) -> None:
        money_stub.clear_calls()
        beat_stub.clear_calls()
        self.actor = CharacterFactory(db_key="IdempotentApplyActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)

    def test_double_apply_does_not_duplicate_queue_rows(self) -> None:
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=10,
        )
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=4,
        )
        first = apply_deed_rewards(self.deed)
        second = apply_deed_rewards(self.deed)
        self.assertEqual(len(first.enqueued), 2)
        self.assertEqual(len(second.enqueued), 2)
        self.assertEqual(MissionRewardQueue.objects.filter(deed=self.deed).count(), 2)
        # Same line pks both times.
        self.assertEqual(
            sorted(r.line_id for r in first.enqueued),
            sorted(r.line_id for r in second.enqueued),
        )

    def test_double_apply_records_stub_calls_each_time(self) -> None:
        # Stub-call records are NOT idempotent — they fire on each apply
        # (the cron itself is the idempotent layer for queued payouts;
        # immediate sinks are the caller's responsibility to gate). This
        # test pins the contract so 5b.2 knows the seam re-fires.
        MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=50,
        )
        apply_deed_rewards(self.deed)
        apply_deed_rewards(self.deed)
        self.assertEqual(len(money_stub.get_calls()), 2)


class ApplyDeedRewardsResultShapeTests(TestCase):
    """The return is a typed dataclass, never a bare dict."""

    def setUp(self) -> None:
        money_stub.clear_calls()
        beat_stub.clear_calls()

    def test_result_is_frozen_dataclass_with_tuples(self) -> None:
        actor = CharacterFactory(db_key="ShapeActor")
        deed = MissionDeedRecordFactory(actor=actor)
        MissionDeedRewardLineFactory(
            deed=deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=1,
        )
        result = apply_deed_rewards(deed)
        # Tuples, not lists — immutable wire shape.
        self.assertIsInstance(result.enqueued, tuple)
        self.assertIsInstance(result.stub_calls, tuple)
        # And the dataclass is frozen.
        with self.assertRaises(FrozenInstanceError):
            result.enqueued = ()  # type: ignore[misc]
