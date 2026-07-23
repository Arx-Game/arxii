"""Tests for the Phase-5a journal_for service.

``journal_for(character)`` returns a list of typed
:class:`world.missions.types.JournalEntry` rows — one per mission the
character has joined. We assert structural shape (no bare dicts; deeds
filtered to the actor; deterministic order by instance pk).
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.missions.constants import MissionStatus
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.services.journal import journal_for
from world.missions.services.run import share_mission, staff_assign_mission
from world.missions.types import JournalDeed, JournalEntry


def _make_character(level: int = 1) -> "object":
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    if level > 0:
        CharacterClassLevelFactory(
            character=sheet,
            character_class=CharacterClassFactory(),
            level=level,
        )
        sheet.invalidate_class_level_cache()
    return character


class JournalForTests(TestCase):
    """Returns one JournalEntry per participation, with structured deeds."""

    def setUp(self) -> None:
        self.template = MissionTemplateFactory(name="Journal Mission")
        self.entry_node = MissionNodeFactory(template=self.template, key="entry", is_entry=True)
        self.holder = _make_character()

    def test_holder_sees_their_run(self) -> None:
        instance = staff_assign_mission(self.template, self.holder)
        entries = journal_for(self.holder)

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertIsInstance(entry, JournalEntry)
        self.assertEqual(entry.instance_id, instance.pk)
        self.assertEqual(entry.template_name, "Journal Mission")
        self.assertEqual(entry.status, MissionStatus.ACTIVE)
        self.assertEqual(entry.current_node_key, "entry")
        self.assertTrue(entry.is_contract_holder)
        self.assertEqual(entry.deeds, ())

    def test_sharee_sees_run_as_non_holder(self) -> None:
        instance = staff_assign_mission(self.template, self.holder)
        sharee = _make_character()
        share_mission(instance, sharee)

        entries = journal_for(sharee)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].is_contract_holder)
        self.assertEqual(entries[0].instance_id, instance.pk)

    def test_deeds_filtered_to_actor(self) -> None:
        instance = staff_assign_mission(self.template, self.holder)
        sharee = _make_character()
        share_mission(instance, sharee)

        # Two deeds: one by holder, one by sharee.
        option = MissionOptionFactory(node=self.entry_node)
        MissionDeedRecordFactory(
            instance=instance, actor=self.holder, node=self.entry_node, option=option
        )
        MissionDeedRecordFactory(
            instance=instance, actor=sharee, node=self.entry_node, option=option
        )

        holder_entries = journal_for(self.holder)
        sharee_entries = journal_for(sharee)

        # Each character sees only their own deeds.
        self.assertEqual(len(holder_entries[0].deeds), 1)
        self.assertEqual(len(sharee_entries[0].deeds), 1)
        for deed in holder_entries[0].deeds + sharee_entries[0].deeds:
            self.assertIsInstance(deed, JournalDeed)
            self.assertEqual(deed.node_key, "entry")
            self.assertEqual(deed.option_id, option.pk)
            self.assertIsNone(deed.outcome_name)  # BRANCH deed

    def test_deterministic_order_by_instance_id(self) -> None:
        # Two missions in order — entries must come back in instance_id order.
        instance_a = staff_assign_mission(self.template, self.holder)
        t2 = MissionTemplateFactory(name="Second")
        MissionNodeFactory(template=t2, key="entry", is_entry=True)
        instance_b = staff_assign_mission(t2, self.holder)

        entries = journal_for(self.holder)
        ids = [e.instance_id for e in entries]
        self.assertEqual(ids, sorted(ids))
        self.assertIn(instance_a.pk, ids)
        self.assertIn(instance_b.pk, ids)

    def test_no_participation_returns_empty_list(self) -> None:
        other = _make_character()
        self.assertEqual(journal_for(other), [])

    def test_journal_for_query_count_is_constant(self) -> None:
        """Query count is O(1) in number of participations, not O(N).

        Regression guard for the original N+1 shape: the prior implementation
        called ``_deeds_for(instance_id=..., character=...)`` inside the
        per-participation loop, so query count grew with the number of
        missions. The fold pulls all deeds in a single query and groups in
        Python; query count stays bounded.
        """
        # Three missions for the same character, each with a deed.
        templates = []
        instances = []
        for i in range(3):
            template = MissionTemplateFactory(name=f"QC Mission {i}")
            entry_node = MissionNodeFactory(template=template, key="entry", is_entry=True)
            templates.append((template, entry_node))
            instance = staff_assign_mission(template, self.holder)
            option = MissionOptionFactory(node=entry_node)
            MissionDeedRecordFactory(
                instance=instance,
                actor=self.holder,
                node=entry_node,
                option=option,
            )
            instances.append(instance)

        with CaptureQueriesContext(connection) as ctx:
            entries = journal_for(self.holder)

        self.assertEqual(len(entries), 3)
        # Constant query budget: participations + deeds + the three #885
        # compass prefetches (current-node locations M2M, current-node
        # options, option-locations M2M) + the two #2049 additions
        # (pending invites + participant counts) + the #2050 summons query
        # + the #2045 project-grants query + the #2047 tales query.
        # The ceiling tolerates one extra lookup but rules out the N+1 shape
        # — with N=3 a per-participation regression would blow past it
        # (e.g. 5 + 3 per-row lookups).
        self.assertLessEqual(
            len(ctx.captured_queries),
            11,
            f"journal_for issued {len(ctx.captured_queries)} queries for 3 "
            "participations — expected O(1), got O(N).",
        )
