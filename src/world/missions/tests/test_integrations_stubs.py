"""Tests for the Phase-5b.1 integration stub-seam modules.

Money and Beat stubs *record* calls (in-memory append) — they're seams
the actual ledger / Beat-completion code will replace. Rumor and
Crime-Watch stubs *raise* NotImplementedError with a DESIGN reference — the
upstream rumor / crime-watch systems do not yet exist, so authoring a
mission that emits those lines must fail loudly during apply.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionDeedRewardLineFactory,
)
from world.missions.integrations import beat_stub, crime_watch_stub, money_stub, rumor_stub


class MoneyStubTests(TestCase):
    """The money stub appends a record; tests own clearing via setUp."""

    def setUp(self) -> None:
        money_stub.clear_calls()
        self.actor = CharacterFactory(db_key="MoneyStubActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)

    def test_deliver_money_records_call(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=42,
        )
        self.assertEqual(money_stub.get_calls(), ())
        money_stub.deliver_money(line)
        calls = money_stub.get_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].line_id, line.pk)
        self.assertEqual(calls[0].amount, 42)
        self.assertEqual(calls[0].recipient_id, line.recipient_id)

    def test_clear_calls_empties_the_log(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=1,
        )
        money_stub.deliver_money(line)
        self.assertEqual(len(money_stub.get_calls()), 1)
        money_stub.clear_calls()
        self.assertEqual(money_stub.get_calls(), ())


class BeatStubTests(TestCase):
    """Beat stub records calls; Phase 5b.3 wires it to BeatCompletion."""

    def setUp(self) -> None:
        beat_stub.clear_calls()
        self.actor = CharacterFactory(db_key="BeatStubActor")
        self.deed = MissionDeedRecordFactory(actor=self.actor)

    def test_propagate_beat_records_call(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.BEAT,
            amount=None,
            ref="beat-anchor",
        )
        self.assertEqual(beat_stub.get_calls(), ())
        beat_stub.propagate_beat(line)
        calls = beat_stub.get_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].line_id, line.pk)
        self.assertEqual(calls[0].ref, "beat-anchor")

    def test_clear_calls_empties_the_log(self) -> None:
        line = MissionDeedRewardLineFactory(
            deed=self.deed,
            kind=DeedRewardKind.POST_CRON,
            sink=DeedRewardSink.BEAT,
        )
        beat_stub.propagate_beat(line)
        self.assertEqual(len(beat_stub.get_calls()), 1)
        beat_stub.clear_calls()
        self.assertEqual(beat_stub.get_calls(), ())


class RumorStubTests(TestCase):
    """Rumor stub MUST hard-fail with a DESIGN message until Phase 6+."""

    def test_propagate_rumor_raises_not_implemented(self) -> None:
        actor = CharacterFactory(db_key="RumorStubActor")
        deed = MissionDeedRecordFactory(actor=actor)
        line = MissionDeedRewardLineFactory(
            deed=deed,
            kind=DeedRewardKind.PROPAGATION,
            sink=DeedRewardSink.RUMOR,
            ref="heist-rumor",
        )
        with self.assertRaises(NotImplementedError) as ctx:
            rumor_stub.propagate_rumor(line)
        # The message must point at the design doc so author confusion is
        # immediately answered.
        self.assertIn("DESIGN", str(ctx.exception))


class CrimeWatchStubTests(TestCase):
    """Crime-watch stub MUST hard-fail with a DESIGN message until Phase 6+."""

    def test_flag_crime_raises_not_implemented(self) -> None:
        actor = CharacterFactory(db_key="CrimeStubActor")
        deed = MissionDeedRecordFactory(actor=actor)
        line = MissionDeedRewardLineFactory(
            deed=deed,
            kind=DeedRewardKind.PROPAGATION,
            sink=DeedRewardSink.CRIME_WATCH,
            ref="bounty-flag",
        )
        with self.assertRaises(NotImplementedError) as ctx:
            crime_watch_stub.flag_crime(line)
        self.assertIn("DESIGN", str(ctx.exception))
