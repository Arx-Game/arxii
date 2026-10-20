"""Which techniques a newly known codex entry opens (#4501), on the shapes authored rows take.

``techniques_opened_by`` answers "what would ``learn_technique`` accept now": the gift held with
room under its cap, no meter or technique already, every other prerequisite met, never an
ultimate, never an inactive requirement.
"""

from django.test import TestCase

from world.achievements.discovery import is_cg_catalog_content
from world.character_sheets.factories import CharacterSheetFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import BeginningsCodexGrantFactory, CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.codex.services import (
    announce_opened_techniques,
    entry_gates_technique,
    techniques_opened_by,
)
from world.magic.constants import GiftKind, TargetKind
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import TechniqueProgress, Thread
from world.narrative.models import NarrativeMessageDelivery
from world.progression.factories import CodexKnowledgeRequirementFactory
from world.progression.models import TechniqueKnownRequirement
from world.roster.factories import RosterEntryFactory


def know(sheet, entry) -> None:
    """The entry is KNOWN to the sheet's character (the state the classifier is asked in)."""
    roster_entry = RosterEntryFactory(character_sheet=sheet)
    CharacterCodexKnowledge.objects.create(
        roster_entry=roster_entry, entry=entry, status=CodexKnowledgeStatus.KNOWN
    )


class TechniquesOpenedByTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.entry = CodexEntryFactory()
        self.technique = TechniqueFactory(gift=self.gift)
        CodexKnowledgeRequirementFactory(
            codex_entry=self.entry, path=None, technique=self.technique
        )
        know(self.sheet, self.entry)

    def _hold_the_gift(self, level: int = 10) -> None:
        CharacterGiftFactory(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=level,
        )

    def test_a_technique_the_character_could_learn_is_opened(self) -> None:
        self._hold_the_gift()
        self.assertEqual(techniques_opened_by(self.sheet, self.entry), [self.technique])

    def test_without_the_gift_nothing_opens(self) -> None:
        self.assertEqual(techniques_opened_by(self.sheet, self.entry), [])

    def test_a_technique_already_known_or_in_training_is_not_announced_again(self) -> None:
        self._hold_the_gift()
        TechniqueProgress.objects.create(
            character_sheet=self.sheet, technique=self.technique, total_required=40
        )
        self.assertEqual(techniques_opened_by(self.sheet, self.entry), [])

        TechniqueProgress.objects.all().delete()
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        self.assertEqual(techniques_opened_by(self.sheet, self.entry), [])

    def test_a_character_at_the_gift_cap_is_not_told_it_opens(self) -> None:
        self._hold_the_gift(level=1)
        for _ in range(3):
            CharacterTechniqueFactory(
                character=self.sheet, technique=TechniqueFactory(gift=self.gift)
            )
        self.assertEqual(techniques_opened_by(self.sheet, self.entry), [])

    def test_an_unmet_other_prerequisite_keeps_it_closed(self) -> None:
        self._hold_the_gift()
        TechniqueKnownRequirement.objects.create(
            technique=self.technique, required_technique=TechniqueFactory(gift=self.gift)
        )
        self.assertEqual(techniques_opened_by(self.sheet, self.entry), [])

    def test_an_inactive_requirement_is_not_a_gate(self) -> None:
        self._hold_the_gift()
        other = CodexEntryFactory()
        CodexKnowledgeRequirementFactory(
            codex_entry=other,
            path=None,
            technique=TechniqueFactory(gift=self.gift),
            is_active=False,
        )
        self.assertFalse(entry_gates_technique(other))
        self.assertEqual(techniques_opened_by(self.sheet, other), [])

    def test_an_entry_that_gates_only_an_ultimate_gates_nothing(self) -> None:
        self._hold_the_gift()
        other = CodexEntryFactory()
        CodexKnowledgeRequirementFactory(
            codex_entry=other,
            path=None,
            technique=TechniqueFactory(gift=self.gift, is_ultimate=True),
        )
        self.assertFalse(entry_gates_technique(other))
        self.assertEqual(techniques_opened_by(self.sheet, other), [])

    def test_a_path_requirement_on_the_same_entry_is_not_a_technique_gate(self) -> None:
        other = CodexEntryFactory()
        CodexKnowledgeRequirementFactory(codex_entry=other)  # a Path row (factory default)
        self.assertFalse(entry_gates_technique(other))


class OpenedTechniqueNoticeTests(TestCase):
    def _gated_entry(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory(kind=GiftKind.MINOR)
        CharacterGiftFactory(character=sheet, gift=gift)
        Thread.objects.create(
            owner=sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.GIFT,
            target_gift=gift,
            level=10,
        )
        entry = CodexEntryFactory()
        CodexKnowledgeRequirementFactory(
            codex_entry=entry, path=None, technique=TechniqueFactory(gift=gift)
        )
        know(sheet, entry)
        return sheet, entry

    def _notices(self, sheet) -> int:
        return NarrativeMessageDelivery.objects.filter(recipient_character_sheet=sheet).count()

    def test_a_lore_entry_that_opens_a_technique_sends_the_notice(self) -> None:
        sheet, entry = self._gated_entry()
        announce_opened_techniques(sheet, entry)
        self.assertEqual(self._notices(sheet), 1)

    def test_a_common_knowledge_entry_stays_quiet(self) -> None:
        """Content a character gets at creation never sends the notice (#2899's rule)."""
        sheet, entry = self._gated_entry()
        BeginningsCodexGrantFactory(entry=entry)
        self.assertTrue(is_cg_catalog_content(entry))
        announce_opened_techniques(sheet, entry)
        self.assertEqual(self._notices(sheet), 0)
