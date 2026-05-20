"""Tests for ``MissionRewardQueue`` (Phase 5b.1).

The reward queue is the durable hand-off from the engine's emitted
:class:`MissionDeedRewardLine` rows to the deferred-payout cron. One queue
row per emitted line — straight 1:1 routing trace. CASCADE on the parent
deed and on the line (line cascade is informational; the deed cascade is
the primary sweep path because lines also cascade on deed).

Phase 5b.1 only adds the table + routing; the cron that consumes
``applied=False`` rows is Phase 5b.2.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionDeedRewardLineFactory,
    MissionNodeFactory,
    MissionTemplateFactory,
)
from world.missions.models import (
    MissionDeedRewardLine,
    MissionRewardQueue,
)


class MissionRewardQueueShapeTests(TestCase):
    """Model fields, defaults, and the 1:1 line-FK uniqueness invariant."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="queue-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.actor = CharacterFactory(db_key="QueueActor")
        cls.deed = MissionDeedRecordFactory(node=cls.node, actor=cls.actor)

    def test_queue_row_round_trips(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=10,
        )
        queued = MissionRewardQueue.objects.create(
            deed=self.deed,
            line=line,
            kind=line.kind,
            sink=line.sink,
        )
        fetched = MissionRewardQueue.objects.get(pk=queued.pk)
        self.assertEqual(fetched.deed, self.deed)
        self.assertEqual(fetched.line, line)
        self.assertEqual(fetched.kind, DeedRewardKind.POST_CRON)
        self.assertEqual(fetched.sink, DeedRewardSink.LEGEND_POINTS)
        self.assertFalse(fetched.applied)
        self.assertIsNone(fetched.applied_at)
        self.assertEqual(fetched.failure_reason, "")

    def test_queue_row_per_line_is_unique(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=5,
        )
        MissionRewardQueue.objects.create(deed=self.deed, line=line, kind=line.kind, sink=line.sink)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MissionRewardQueue.objects.create(
                deed=self.deed, line=line, kind=line.kind, sink=line.sink
            )

    def test_deed_delete_cascades_to_queue(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=7,
        )
        queued = MissionRewardQueue.objects.create(
            deed=self.deed, line=line, kind=line.kind, sink=line.sink
        )
        self.deed.delete()
        self.assertFalse(MissionRewardQueue.objects.filter(pk=queued.pk).exists())

    def test_line_delete_cascades_to_queue(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=3,
        )
        queued = MissionRewardQueue.objects.create(
            deed=self.deed, line=line, kind=line.kind, sink=line.sink
        )
        MissionDeedRewardLine.objects.filter(pk=line.pk).delete()
        self.assertFalse(MissionRewardQueue.objects.filter(pk=queued.pk).exists())

    def test_queued_rewards_related_name(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=10,
        )
        queued = MissionRewardQueue.objects.create(
            deed=self.deed, line=line, kind=line.kind, sink=line.sink
        )
        self.assertIn(queued, list(self.deed.queued_rewards.all()))

    def test_save_calls_clean(self) -> None:
        # House pattern: save() invokes clean() so authored model-level
        # invariants always run on the real write path, even if clean() has
        # no rules yet. We exercise this by patching clean() and asserting
        # save() calls it.
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.RESONANCE,
            amount=4,
        )
        queued = MissionRewardQueue(deed=self.deed, line=line, kind=line.kind, sink=line.sink)
        called = {"n": 0}

        def _spy_clean() -> None:
            called["n"] += 1

        queued.clean = _spy_clean  # type: ignore[method-assign]
        queued.save()
        self.assertGreaterEqual(called["n"], 1)

        # And clean() raising aborts save (no row written).
        line2 = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.LEGEND_POINTS,
            amount=2,
        )
        queued2 = MissionRewardQueue(deed=self.deed, line=line2, kind=line2.kind, sink=line2.sink)

        def _raise() -> None:
            msg = "nope"
            raise ValidationError(msg)

        queued2.clean = _raise  # type: ignore[method-assign]
        with self.assertRaises(ValidationError):
            queued2.save()
        self.assertIsNone(queued2.pk)
