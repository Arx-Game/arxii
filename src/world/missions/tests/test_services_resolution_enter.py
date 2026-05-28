"""Tests for ``enter_node`` (Phase 3, Task 3.2).

Entering a node writes one snapshot per participant and advances the run's
position. Evaluation cadence is once per entry — the snapshot rows are the
record (re-entering writes another row).
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionNodeSnapshot
from world.missions.services import enter_node


class EnterNodeTests(TestCase):
    """Snapshot-per-participant-per-entry; current_node advanced."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(name="enter-tmpl")
        cls.instance = MissionInstanceFactory(template=cls.template)
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.next_node = MissionNodeFactory(template=cls.template, key="next")
        cls.participant = MissionParticipantFactory(
            instance=cls.instance,
            character=CharacterFactory(),
            is_contract_holder=True,
        )

    def test_entering_a_node_writes_one_snapshot_and_sets_current(self) -> None:
        enter_node(self.instance, self.entry)
        snaps = MissionNodeSnapshot.objects.filter(instance=self.instance)
        self.assertEqual(snaps.count(), 1)
        snap = snaps.get()
        self.assertEqual(snap.node, self.entry)
        self.assertEqual(snap.participant, self.participant)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.entry)

    def test_re_entering_writes_a_second_snapshot_row(self) -> None:
        enter_node(self.instance, self.entry)
        enter_node(self.instance, self.next_node)
        per_participant = MissionNodeSnapshot.objects.filter(
            instance=self.instance,
            participant=self.participant,
        )
        self.assertEqual(per_participant.count(), 2)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_node, self.next_node)

    def test_one_snapshot_per_participant(self) -> None:
        MissionParticipantFactory(
            instance=self.instance,
            character=CharacterFactory(),
            is_contract_holder=False,
        )
        enter_node(self.instance, self.entry)
        self.assertEqual(
            MissionNodeSnapshot.objects.filter(instance=self.instance).count(),
            2,
        )
