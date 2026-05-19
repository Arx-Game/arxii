"""Tests for the Phase-5a journal_for service.

``journal_for(character)`` returns a list of typed
:class:`world.missions.types.JournalEntry` rows — one per mission the
character has joined. We assert structural shape (no bare dicts; deeds
filtered to the actor; deterministic order by instance pk).
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.missions.constants import MissionStatus
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionGiverFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.services.journal import journal_for
from world.missions.services.run import accept_mission, share_mission
from world.missions.types import JournalDeed, JournalEntry


def _make_character(level: int = 1) -> "object":
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    if level > 0:
        CharacterClassLevelFactory(
            character=character,
            character_class=CharacterClassFactory(),
            level=level,
        )
        sheet.invalidate_class_level_cache()
    return character


class JournalForTests(TestCase):
    """Returns one JournalEntry per participation, with structured deeds."""

    def setUp(self) -> None:
        self.giver = MissionGiverFactory()
        self.template = MissionTemplateFactory(slug="journal-t", name="Journal Mission")
        self.entry_node = MissionNodeFactory(template=self.template, key="entry", is_entry=True)
        self.giver.templates.add(self.template)
        self.holder = _make_character()

    def test_holder_sees_their_run(self) -> None:
        instance = accept_mission(self.giver, self.template, self.holder)
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
        instance = accept_mission(self.giver, self.template, self.holder)
        sharee = _make_character()
        share_mission(instance, sharee)

        entries = journal_for(sharee)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0].is_contract_holder)
        self.assertEqual(entries[0].instance_id, instance.pk)

    def test_deeds_filtered_to_actor(self) -> None:
        instance = accept_mission(self.giver, self.template, self.holder)
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
        instance_a = accept_mission(self.giver, self.template, self.holder)
        t2 = MissionTemplateFactory(slug="journal-t2", name="Second")
        MissionNodeFactory(template=t2, key="entry", is_entry=True)
        giver2 = MissionGiverFactory(name="Other Giver")
        giver2.templates.add(t2)
        instance_b = accept_mission(giver2, t2, self.holder)

        entries = journal_for(self.holder)
        ids = [e.instance_id for e in entries]
        self.assertEqual(ids, sorted(ids))
        self.assertIn(instance_a.pk, ids)
        self.assertIn(instance_b.pk, ids)

    def test_no_participation_returns_empty_list(self) -> None:
        other = _make_character()
        self.assertEqual(journal_for(other), [])
