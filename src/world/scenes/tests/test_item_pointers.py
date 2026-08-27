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
from world.items.services.org_vault import deposit_item_to_vault
from world.roster.factories import RosterEntryFactory
from world.scenes.boon_services import character_has_item_pointer, pointer_known_items_for_target
from world.scenes.factories import PersonaFactory
from world.secrets.factories import SecretFactory, SecretKnowledgeFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory


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

    def test_template_level_codex_entry_matches_any_instance_of_the_kind(self) -> None:
        """#2540 slice 3 Task 1 review fold-in: the CLUE pin-semantics pair, mirrored
        for CODEX — a template-only KNOWN entry (no instance pinned) matches ANY
        sibling instance of that template."""
        other_item = ItemInstanceFactory(template=self.template)
        entry = CodexEntryFactory(subject_item_template=self.template, subject_item_instance=None)
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        self.assertTrue(character_has_item_pointer(sheet=self.sheet, item=other_item))

    def test_instance_pinned_codex_entry_does_not_match_a_sibling_instance(self) -> None:
        """#2540 slice 3 Task 1 review fold-in: the CLUE pin-semantics pair, mirrored
        for CODEX — an instance-pinned KNOWN entry names ONLY that instance."""
        other_item = ItemInstanceFactory(template=self.template)
        entry = CodexEntryFactory(
            subject_item_template=self.template, subject_item_instance=self.item
        )
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=entry,
            status=CodexKnowledgeStatus.KNOWN,
        )
        self.assertFalse(character_has_item_pointer(sheet=self.sheet, item=other_item))
        self.assertTrue(character_has_item_pointer(sheet=self.sheet, item=self.item))

    def test_true_via_known_secret(self) -> None:
        secret = SecretFactory(subject_item_template=self.template)
        SecretKnowledgeFactory(roster_entry=self.roster_entry, secret=secret)
        self.assertTrue(character_has_item_pointer(sheet=self.sheet, item=self.item))

    def test_template_level_secret_matches_any_instance_of_the_kind(self) -> None:
        """#2540 slice 3 Task 1 review fold-in: the CLUE pin-semantics pair, mirrored
        for SECRET — a template-only secret (no instance pinned) matches ANY sibling
        instance of that template."""
        other_item = ItemInstanceFactory(template=self.template)
        secret = SecretFactory(subject_item_template=self.template, subject_item_instance=None)
        SecretKnowledgeFactory(roster_entry=self.roster_entry, secret=secret)
        self.assertTrue(character_has_item_pointer(sheet=self.sheet, item=other_item))

    def test_instance_pinned_secret_does_not_match_a_sibling_instance(self) -> None:
        """#2540 slice 3 Task 1 review fold-in: the CLUE pin-semantics pair, mirrored
        for SECRET — an instance-pinned secret names ONLY that instance."""
        other_item = ItemInstanceFactory(template=self.template)
        secret = SecretFactory(subject_item_template=self.template, subject_item_instance=self.item)
        SecretKnowledgeFactory(roster_entry=self.roster_entry, secret=secret)
        self.assertFalse(character_has_item_pointer(sheet=self.sheet, item=other_item))
        self.assertTrue(character_has_item_pointer(sheet=self.sheet, item=self.item))


class PointerKnownItemsForTargetTests(TestCase):
    """The boon-options display seam (#2540 slice 3): ``pointer_known_items_for_target``."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.asker_roster_entry = RosterEntryFactory()
        cls.asker_sheet = cls.asker_roster_entry.character_sheet
        cls.target = PersonaFactory()
        cls.template = ItemTemplateFactory()

    def test_empty_with_no_asker_pointers(self) -> None:
        ItemInstanceFactory(
            template=self.template, holder_character_sheet=self.target.character_sheet
        )
        self.assertEqual(
            pointer_known_items_for_target(
                asker_sheet=self.asker_sheet, target_persona=self.target
            ),
            [],
        )

    def test_held_item_the_asker_has_a_pointer_to(self) -> None:
        item = ItemInstanceFactory(
            template=self.template, holder_character_sheet=self.target.character_sheet
        )
        grant_item_pointer_clue(self.asker_roster_entry, item)
        options = pointer_known_items_for_target(
            asker_sheet=self.asker_sheet, target_persona=self.target
        )
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].item_instance_id, item.pk)
        self.assertEqual(options[0].source, "held")

    def test_never_lists_a_held_item_the_asker_has_no_pointer_to(self) -> None:
        """NEVER a browse of the target's actual holdings — a pointer is the only window."""
        ItemInstanceFactory(
            template=self.template, holder_character_sheet=self.target.character_sheet
        )
        self.assertEqual(
            pointer_known_items_for_target(
                asker_sheet=self.asker_sheet, target_persona=self.target
            ),
            [],
        )

    def test_template_only_pointer_matches_any_held_instance(self) -> None:
        pinned_item = ItemInstanceFactory(template=self.template)
        held_item = ItemInstanceFactory(
            template=self.template, holder_character_sheet=self.target.character_sheet
        )
        grant_item_pointer_clue(self.asker_roster_entry, pinned_item)  # template-only pointer
        options = pointer_known_items_for_target(
            asker_sheet=self.asker_sheet, target_persona=self.target
        )
        self.assertEqual([o.item_instance_id for o in options], [held_item.pk])

    def test_vault_item_the_asker_has_a_pointer_to_and_target_can_access(self) -> None:
        org = OrganizationFactory()
        OrganizationMembershipFactory(persona=self.target, organization=org, rank=1)
        item = ItemInstanceFactory(
            template=self.template, holder_character_sheet=self.target.character_sheet
        )
        deposit_item_to_vault(organization=org, persona=self.target, item_instance=item)
        grant_item_pointer_clue(self.asker_roster_entry, item)
        options = pointer_known_items_for_target(
            asker_sheet=self.asker_sheet, target_persona=self.target
        )
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].item_instance_id, item.pk)
        self.assertEqual(options[0].source, "vault")

    def test_never_lists_a_vault_item_the_target_cannot_withdraw(self) -> None:
        """The target's own authority still gates the vault side (rank too low)."""
        org = OrganizationFactory()
        depositor = PersonaFactory()
        OrganizationMembershipFactory(persona=depositor, organization=org, rank=1)
        OrganizationMembershipFactory(persona=self.target, organization=org, rank=5)  # too low
        item = ItemInstanceFactory(
            template=self.template, holder_character_sheet=depositor.character_sheet
        )
        deposit_item_to_vault(organization=org, persona=depositor, item_instance=item)
        grant_item_pointer_clue(self.asker_roster_entry, item)
        self.assertEqual(
            pointer_known_items_for_target(
                asker_sheet=self.asker_sheet, target_persona=self.target
            ),
            [],
        )
