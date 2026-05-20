"""Tests for the Phase-5b.3 ``on_mission_complete_for_beat`` stub-record service.

See :mod:`world.missions.services.beat` for the deferred product-level
design questions. 5b.3 only verifies the trigger-record shape and the
free-vs-beat-bound branching; no BeatCompletion is created, no stories
service is called.
"""

from django.test import TestCase

from world.missions.factories import MissionInstanceFactory, MissionTemplateFactory
from world.missions.services import beat as beat_service, on_mission_complete_for_beat
from world.stories.factories import BeatFactory


class OnMissionCompleteForBeatTests(TestCase):
    """Stub-record shape: free → None; beat-bound → record."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="beat-svc-tmpl")

    def setUp(self) -> None:
        beat_service.clear_triggers()

    def test_free_mission_returns_none_and_records_nothing(self) -> None:
        instance = MissionInstanceFactory(template=self.template, source_beat=None)
        self.assertIsNone(instance.source_beat_id)

        result = on_mission_complete_for_beat(instance)

        self.assertIsNone(result)
        self.assertEqual(beat_service.get_triggers(), ())

    def test_beat_bound_mission_returns_record_and_logs_trigger(self) -> None:
        beat = BeatFactory()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)

        result = on_mission_complete_for_beat(instance)

        self.assertIsNotNone(result)
        self.assertEqual(result.instance_pk, instance.pk)
        self.assertEqual(result.beat_pk, beat.pk)
        self.assertIsNotNone(result.triggered_at)

        triggers = beat_service.get_triggers()
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0], result)

    def test_clear_triggers_resets_state(self) -> None:
        beat = BeatFactory()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)

        on_mission_complete_for_beat(instance)
        self.assertEqual(len(beat_service.get_triggers()), 1)

        beat_service.clear_triggers()
        self.assertEqual(beat_service.get_triggers(), ())

    def test_double_call_records_two_triggers_not_idempotent(self) -> None:
        # Matches beat_stub's append-on-every-call shape — the stub is a
        # call log, not a state machine. The future engine (which actually
        # flips the Beat) will own idempotency at that layer.
        beat = BeatFactory()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)

        first = on_mission_complete_for_beat(instance)
        second = on_mission_complete_for_beat(instance)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(len(beat_service.get_triggers()), 2)
        # The two records carry the same (instance, beat) pks — the only
        # variance is ``triggered_at``.
        self.assertEqual(first.instance_pk, second.instance_pk)
        self.assertEqual(first.beat_pk, second.beat_pk)

    def test_get_triggers_returns_immutable_tuple(self) -> None:
        # Mirrors beat_stub.get_calls()'s tuple-not-list contract.
        beat = BeatFactory()
        instance = MissionInstanceFactory(template=self.template, source_beat=beat)
        on_mission_complete_for_beat(instance)
        triggers = beat_service.get_triggers()
        self.assertIsInstance(triggers, tuple)
