"""Tests for CharacterRitualKnowledge and ritual grant tables."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_creation.factories import BeginningsFactory
from world.classes.factories import PathFactory
from world.distinctions.factories import DistinctionFactory
from world.magic.factories import (
    CharacterRitualKnowledgeFactory,
    RitualFactory,
    TraditionFactory,
)
from world.magic.models import (
    CharacterRitualKnowledge,
)
from world.magic.models.grants import (
    BeginningsRitualGrant,
    CodexEntryRitualGrant,
    DistinctionRitualGrant,
    PathRitualGrant,
    TraditionRitualGrant,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class CharacterRitualKnowledgeTests(TestCase):
    def test_create_knowledge_record(self):
        roster_entry = RosterEntryFactory()
        ritual = RitualFactory()
        knowledge = CharacterRitualKnowledge.objects.create(
            roster_entry=roster_entry,
            ritual=ritual,
            learned_from=None,
        )
        self.assertEqual(knowledge.roster_entry, roster_entry)
        self.assertEqual(knowledge.ritual, ritual)
        self.assertIsNone(knowledge.learned_from)
        self.assertIsNotNone(knowledge.learned_at)

    def test_create_knowledge_with_teacher(self):
        roster_entry = RosterEntryFactory()
        ritual = RitualFactory()
        tenure = RosterTenureFactory()
        knowledge = CharacterRitualKnowledge.objects.create(
            roster_entry=roster_entry,
            ritual=ritual,
            learned_from=tenure,
        )
        self.assertEqual(knowledge.learned_from, tenure)

    def test_unique_together(self):
        roster_entry = RosterEntryFactory()
        ritual = RitualFactory()
        CharacterRitualKnowledge.objects.create(roster_entry=roster_entry, ritual=ritual)
        with self.assertRaises(IntegrityError):
            CharacterRitualKnowledge.objects.create(roster_entry=roster_entry, ritual=ritual)

    def test_factory_creates_valid_record(self):
        knowledge = CharacterRitualKnowledgeFactory()
        self.assertIsNotNone(knowledge.pk)
        self.assertIsNotNone(knowledge.roster_entry)
        self.assertIsNotNone(knowledge.ritual)
        self.assertIsNotNone(knowledge.learned_at)


class RitualGrantTests(TestCase):
    def test_beginnings_grant_uniqueness(self):
        beginnings = BeginningsFactory()
        ritual = RitualFactory()
        BeginningsRitualGrant.objects.create(beginnings=beginnings, ritual=ritual)
        with self.assertRaises(IntegrityError):
            BeginningsRitualGrant.objects.create(beginnings=beginnings, ritual=ritual)

    def test_path_grant_uniqueness(self):
        path = PathFactory()
        ritual = RitualFactory()
        PathRitualGrant.objects.create(path=path, ritual=ritual)
        with self.assertRaises(IntegrityError):
            PathRitualGrant.objects.create(path=path, ritual=ritual)

    def test_distinction_grant_uniqueness(self):
        distinction = DistinctionFactory()
        ritual = RitualFactory()
        DistinctionRitualGrant.objects.create(distinction=distinction, ritual=ritual)
        with self.assertRaises(IntegrityError):
            DistinctionRitualGrant.objects.create(distinction=distinction, ritual=ritual)

    def test_tradition_grant_uniqueness(self):
        tradition = TraditionFactory()
        ritual = RitualFactory()
        TraditionRitualGrant.objects.create(tradition=tradition, ritual=ritual)
        with self.assertRaises(IntegrityError):
            TraditionRitualGrant.objects.create(tradition=tradition, ritual=ritual)

    def test_codex_entry_grant_uniqueness(self):
        from world.codex.factories import CodexEntryFactory

        codex_entry = CodexEntryFactory()
        ritual = RitualFactory()
        CodexEntryRitualGrant.objects.create(codex_entry=codex_entry, ritual=ritual)
        with self.assertRaises(IntegrityError):
            CodexEntryRitualGrant.objects.create(codex_entry=codex_entry, ritual=ritual)

    def test_same_ritual_different_sources_allowed(self):
        """Same ritual can be granted from different source types independently."""
        ritual = RitualFactory()
        beginnings = BeginningsFactory()
        path = PathFactory()
        g1 = BeginningsRitualGrant.objects.create(beginnings=beginnings, ritual=ritual)
        g2 = PathRitualGrant.objects.create(path=path, ritual=ritual)
        self.assertIsNotNone(g1.pk)
        self.assertIsNotNone(g2.pk)
