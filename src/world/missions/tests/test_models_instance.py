"""Tests for the runtime mission models (Phase 2, Task 2.4).

Covers MissionInstance (no state blob — current_node + snapshots + deeds is
the only state), MissionParticipant (exactly one contract holder, unique
per character), MissionNodeSnapshot existence, and MissionDeedRecord with
its structured child reward lines (NOT a dict).
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.missions.constants import (
    DeedRewardKind,
    DeedRewardSink,
    MissionStatus,
    OptionKind,
    OptionSource,
)
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionDeedRewardLineFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionNodeSnapshotFactory,
    MissionOptionFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import (
    MissionDeedRewardLine,
    MissionInstance,
    MissionNodeSnapshot,
)


class MissionInstanceTests(TestCase):
    """Instance round-trip + the no-state-blob invariant."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="inst-tmpl")
        cls.entry = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.instance = MissionInstanceFactory(
            template=cls.template,
            current_node=cls.entry,
        )

    def test_instance_round_trips(self) -> None:
        fetched = MissionInstance.objects.get(pk=self.instance.pk)
        self.assertEqual(fetched.template, self.template)
        self.assertEqual(fetched.current_node, self.entry)
        self.assertEqual(fetched.status, MissionStatus.ACTIVE)
        self.assertIsNotNone(fetched.started_at)
        self.assertIsNone(fetched.completed_at)

    def test_instance_has_no_state_blob_field(self) -> None:
        # Design §7: state is current_node + snapshots + deeds only. Guard
        # against a future state/scratch/variable JSON field regression.
        field_names = {f.name for f in MissionInstance._meta.get_fields()}
        for forbidden in ("state", "scratch", "variables", "data", "blob"):
            self.assertNotIn(forbidden, field_names)

    def test_current_node_set_null_on_node_delete(self) -> None:
        instance_pk = self.instance.pk
        self.entry.delete()
        # SET_NULL nulls the column at the DB level; read the persisted
        # value directly (SharedMemoryModel's identity map would otherwise
        # hand back the cached in-memory FK).
        current_node_id = (
            MissionInstance.objects.filter(pk=instance_pk)
            .values_list("current_node_id", flat=True)
            .first()
        )
        self.assertIsNone(current_node_id)


class MissionParticipantTests(TestCase):
    """Exactly one contract holder; (instance, character) unique."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.instance = MissionInstanceFactory(template__slug="part-tmpl")
        cls.char_a = CharacterFactory(db_key="Holder")
        cls.char_b = CharacterFactory(db_key="Tagalong")
        cls.holder = MissionParticipantFactory(
            instance=cls.instance,
            character=cls.char_a,
            is_contract_holder=True,
        )

    def test_participant_round_trips(self) -> None:
        self.assertTrue(self.holder.is_contract_holder)
        self.assertEqual(self.holder.character, self.char_a)

    def test_second_contract_holder_rejected(self) -> None:
        second = MissionParticipantFactory.build(
            instance=self.instance,
            character=self.char_b,
            is_contract_holder=True,
        )
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_non_holder_participant_allowed(self) -> None:
        part = MissionParticipantFactory(
            instance=self.instance,
            character=self.char_b,
            is_contract_holder=False,
        )
        part.full_clean()
        self.assertFalse(part.is_contract_holder)

    def test_duplicate_instance_character_rejected(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            MissionParticipantFactory(
                instance=self.instance,
                character=self.char_a,
            )


class MissionNodeSnapshotTests(TestCase):
    """A snapshot row can exist per (instance, node, participant)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="snap-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.instance = MissionInstanceFactory(template=cls.template, current_node=cls.node)
        cls.participant = MissionParticipantFactory(
            instance=cls.instance,
            is_contract_holder=True,
        )

    def test_snapshot_exists_per_instance_node_participant(self) -> None:
        snap = MissionNodeSnapshotFactory(
            instance=self.instance,
            node=self.node,
            participant=self.participant,
        )
        fetched = MissionNodeSnapshot.objects.get(pk=snap.pk)
        self.assertEqual(fetched.instance, self.instance)
        self.assertEqual(fetched.node, self.node)
        self.assertEqual(fetched.participant, self.participant)
        self.assertIsNotNone(fetched.taken_at)


class MissionDeedRecordTests(TestCase):
    """Deed records carry structured reward lines, never a dict."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = MissionTemplateFactory(slug="deed-tmpl")
        cls.node = MissionNodeFactory(template=cls.template, key="entry", is_entry=True)
        cls.instance = MissionInstanceFactory(template=cls.template, current_node=cls.node)
        cls.actor = CharacterFactory(db_key="Actor")
        cls.option = MissionOptionFactory(
            node=cls.node,
            order=0,
            option_kind=OptionKind.BRANCH,
            source_kind=OptionSource.AUTHORED,
        )

    def test_branch_deed_has_null_outcome(self) -> None:
        deed = MissionDeedRecordFactory(
            instance=self.instance,
            actor=self.actor,
            node=self.node,
            option=self.option,
            outcome=None,
        )
        self.assertIsNone(deed.outcome)
        self.assertEqual(deed.actor, self.actor)

    def test_deed_reward_lines_are_structured_rows_not_dict(self) -> None:
        deed = MissionDeedRecordFactory(
            instance=self.instance,
            actor=self.actor,
            node=self.node,
            option=self.option,
        )
        money = MissionDeedRewardLineFactory(
            deed=deed,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.MONEY,
            amount=250,
        )
        rumor = MissionDeedRewardLineFactory(
            deed=deed,
            kind=DeedRewardKind.PROPAGATION,
            sink=DeedRewardSink.RUMOR,
            amount=None,
            ref="heist-rumor",
        )
        lines = MissionDeedRewardLine.objects.filter(deed=deed)
        self.assertEqual(lines.count(), 2)
        self.assertEqual(money.amount, 250)
        self.assertEqual(rumor.sink, DeedRewardSink.RUMOR)
        self.assertEqual(rumor.ref, "heist-rumor")
        # The reward summary is a relation of typed rows, not a JSON blob.
        self.assertFalse(hasattr(deed, "reward_summary"))
