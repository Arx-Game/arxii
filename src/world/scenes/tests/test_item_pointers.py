"""Item knowledge pointers (#2540 slice 3, 2026-08-27 exact-pointer ruling).

``character_has_item_pointer`` is the predicate behind a named-item boon ask: it reads
prior knowledge across the three knowledge surfaces (a discovered ITEM-target clue, a
KNOWN codex entry, known secret knowledge), each pointing at either an exact item
instance or "any instance of this template".
"""

from django.test import TestCase

from world.clues.constants import ClueTargetKind
from world.clues.factories import CharacterClueFactory, ClueFactory
from world.clues.models import CharacterClue, Clue
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.roster.factories import RosterEntryFactory
from world.scenes.boon_services import character_has_item_pointer
from world.secrets.factories import SecretFactory, SecretKnowledgeFactory


def grant_item_pointer_clue(roster_entry, item, *, instance_pinned: bool = False) -> CharacterClue:
    """Test helper: acquire an ITEM-target clue naming ``item`` (template or exact)."""
    clue = ClueFactory(
        target_kind=ClueTargetKind.ITEM,
        target_codex_entry=None,
        target_item_template=item.template,
        target_item_instance=item if instance_pinned else None,
    )
    return CharacterClueFactory(roster_entry=roster_entry, clue=clue)


class CharacterHasItemPointerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.roster_entry = RosterEntryFactory()
        cls.sheet = cls.roster_entry.character_sheet
        cls.template = ItemTemplateFactory()
        cls.item = ItemInstanceFactory(template=cls.template)

    def test_false_with_no_knowledge(self) -> None:
        self.assertFalse(character_has_item_pointer(sheet=self.sheet, item=self.item))

    def test_true_via_discovered_clue(self) -> None:
        grant_item_pointer_clue(self.roster_entry, self.item)
        self.assertTrue(character_has_item_pointer(sheet=self.sheet, item=self.item))

    def test_undiscovered_clue_is_false(self) -> None:
        """A clue targeting the item exists, but this roster entry never found it."""
        Clue.objects.create(
            target_kind=ClueTargetKind.ITEM,
            target_item_template=self.template,
            name="Unfound Item Clue",
            description="A clue about this item that nobody has found yet.",
        )
        self.assertFalse(character_has_item_pointer(sheet=self.sheet, item=self.item))

    def test_template_level_clue_matches_any_instance_of_the_kind(self) -> None:
        other_item = ItemInstanceFactory(template=self.template)
        grant_item_pointer_clue(self.roster_entry, self.item)  # template-only pointer
        self.assertTrue(character_has_item_pointer(sheet=self.sheet, item=other_item))

    def test_instance_pinned_clue_does_not_match_a_sibling_instance(self) -> None:
        other_item = ItemInstanceFactory(template=self.template)
        grant_item_pointer_clue(self.roster_entry, self.item, instance_pinned=True)
        self.assertFalse(character_has_item_pointer(sheet=self.sheet, item=other_item))
        self.assertTrue(character_has_item_pointer(sheet=self.sheet, item=self.item))

    def test_true_via_known_codex_entry(self) -> None:
        entry = CodexEntryFactory(subject_item_template=self.template)
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        self.assertTrue(character_has_item_pointer(sheet=self.sheet, item=self.item))

    def test_uncovered_codex_entry_is_false(self) -> None:
        entry = CodexEntryFactory(subject_item_template=self.template)
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.UNCOVERED,
        )
        self.assertFalse(character_has_item_pointer(sheet=self.sheet, item=self.item))

    def test_true_via_known_secret(self) -> None:
        secret = SecretFactory(subject_item_template=self.template)
        SecretKnowledgeFactory(roster_entry=self.roster_entry, secret=secret)
        self.assertTrue(character_has_item_pointer(sheet=self.sheet, item=self.item))
