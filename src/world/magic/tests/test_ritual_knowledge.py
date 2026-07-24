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


class ReconcileRitualKnowledgeTests(TestCase):
    """Tests for reconcile_ritual_knowledge service."""

    def test_reconcile_creates_knowledge_row_for_path_grant(self):
        """Character with path should have knowledge row created for path grants."""
        from world.progression.factories import CharacterPathHistoryFactory

        roster_entry = RosterEntryFactory()
        path = PathFactory()
        ritual = RitualFactory()

        # Grant ritual for this path
        PathRitualGrant.objects.create(path=path, ritual=ritual)

        # Assign path to character via CharacterPathHistory
        CharacterPathHistoryFactory(
            character=roster_entry.character_sheet,
            path=path,
        )

        from world.magic.services.ritual_knowledge import reconcile_ritual_knowledge

        reconcile_ritual_knowledge(roster_entry)

        # Verify knowledge row was created
        self.assertTrue(
            CharacterRitualKnowledge.objects.filter(
                roster_entry=roster_entry,
                ritual=ritual,
                learned_from__isnull=True,
            ).exists()
        )

    def test_reconcile_creates_knowledge_row_for_tradition_grant(self):
        """Character with tradition should have knowledge row created for tradition grants."""
        from world.magic.factories import CharacterTraditionFactory

        roster_entry = RosterEntryFactory()
        tradition = TraditionFactory()
        ritual = RitualFactory()

        # Grant ritual for this tradition
        TraditionRitualGrant.objects.create(tradition=tradition, ritual=ritual)

        # Assign tradition to character
        CharacterTraditionFactory(
            character=roster_entry.character_sheet,
            tradition=tradition,
        )

        from world.magic.services.ritual_knowledge import reconcile_ritual_knowledge

        reconcile_ritual_knowledge(roster_entry)

        # Verify knowledge row was created
        self.assertTrue(
            CharacterRitualKnowledge.objects.filter(
                roster_entry=roster_entry,
                ritual=ritual,
                learned_from__isnull=True,
            ).exists()
        )

    def test_reconcile_creates_knowledge_row_for_distinction_grant(self):
        """Character with distinction should have knowledge row created for distinction grants."""
        from world.distinctions.factories import CharacterDistinctionFactory

        roster_entry = RosterEntryFactory()
        distinction = DistinctionFactory()
        ritual = RitualFactory()

        # Grant ritual for this distinction
        DistinctionRitualGrant.objects.create(distinction=distinction, ritual=ritual)

        # Assign distinction to character
        CharacterDistinctionFactory(
            character=roster_entry.character_sheet,
            distinction=distinction,
        )

        from world.magic.services.ritual_knowledge import reconcile_ritual_knowledge

        reconcile_ritual_knowledge(roster_entry)

        # Verify knowledge row was created
        self.assertTrue(
            CharacterRitualKnowledge.objects.filter(
                roster_entry=roster_entry,
                ritual=ritual,
                learned_from__isnull=True,
            ).exists()
        )

    def test_reconcile_creates_knowledge_row_for_known_codex_entries(self):
        """Character who knows codex entries should have knowledge rows for codex grants."""
        from world.codex.constants import CodexKnowledgeStatus
        from world.codex.factories import CodexEntryFactory
        from world.codex.models import CharacterCodexKnowledge

        roster_entry = RosterEntryFactory()
        codex_entry = CodexEntryFactory()
        ritual = RitualFactory()

        # Grant ritual for this codex entry
        CodexEntryRitualGrant.objects.create(codex_entry=codex_entry, ritual=ritual)

        # Character knows this codex entry
        CharacterCodexKnowledge.objects.create(
            roster_entry=roster_entry,
            entry=codex_entry,
            status=CodexKnowledgeStatus.KNOWN,
        )

        from world.magic.services.ritual_knowledge import reconcile_ritual_knowledge

        reconcile_ritual_knowledge(roster_entry)

        # Verify knowledge row was created
        self.assertTrue(
            CharacterRitualKnowledge.objects.filter(
                roster_entry=roster_entry,
                ritual=ritual,
                learned_from__isnull=True,
            ).exists()
        )

    def test_reconcile_idempotent(self):
        """Calling reconcile twice should not create duplicate knowledge rows."""
        from world.progression.factories import CharacterPathHistoryFactory

        roster_entry = RosterEntryFactory()
        path = PathFactory()
        ritual = RitualFactory()

        PathRitualGrant.objects.create(path=path, ritual=ritual)
        CharacterPathHistoryFactory(
            character=roster_entry.character_sheet,
            path=path,
        )

        from world.magic.services.ritual_knowledge import reconcile_ritual_knowledge

        reconcile_ritual_knowledge(roster_entry)
        count_after_first = CharacterRitualKnowledge.objects.filter(
            roster_entry=roster_entry,
            ritual=ritual,
        ).count()

        reconcile_ritual_knowledge(roster_entry)
        count_after_second = CharacterRitualKnowledge.objects.filter(
            roster_entry=roster_entry,
            ritual=ritual,
        ).count()

        self.assertEqual(count_after_first, 1)
        self.assertEqual(count_after_second, 1)

    def test_reconcile_does_not_overwrite_taught_rows(self):
        """Knowledge rows with learned_from should not be replaced."""
        from world.progression.factories import CharacterPathHistoryFactory

        roster_entry = RosterEntryFactory()
        path = PathFactory()
        ritual = RitualFactory()
        teacher_tenure = RosterTenureFactory()

        # Create knowledge row with a teacher
        CharacterRitualKnowledge.objects.create(
            roster_entry=roster_entry,
            ritual=ritual,
            learned_from=teacher_tenure,
        )

        # Create grant for this path
        PathRitualGrant.objects.create(path=path, ritual=ritual)
        CharacterPathHistoryFactory(
            character=roster_entry.character_sheet,
            path=path,
        )

        from world.magic.services.ritual_knowledge import reconcile_ritual_knowledge

        reconcile_ritual_knowledge(roster_entry)

        # Verify the teacher attribution is preserved
        knowledge = CharacterRitualKnowledge.objects.get(
            roster_entry=roster_entry,
            ritual=ritual,
        )
        self.assertEqual(knowledge.learned_from, teacher_tenure)

    def test_reconcile_handles_no_grants(self):
        """Reconciliation should handle character with no qualifying grants."""
        roster_entry = RosterEntryFactory()

        from world.magic.services.ritual_knowledge import reconcile_ritual_knowledge

        # Should not raise an error
        reconcile_ritual_knowledge(roster_entry)

        # Verify no spurious knowledge rows created
        count = CharacterRitualKnowledge.objects.filter(
            roster_entry=roster_entry,
        ).count()
        self.assertEqual(count, 0)
