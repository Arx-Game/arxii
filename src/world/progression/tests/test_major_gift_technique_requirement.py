"""Tests for MajorGiftTechniqueRequirement — level-2 gate (#2440 ruling 4).

Level 2 requires knowing >= 3 techniques of the character's MAJOR gift. This is
a COUNT gate, not completeness — minor-gift techniques never count. The registry
wiring test proves the type actually evaluates through
``check_requirements_for_unlock`` (the requirement-type list in
``spends.py:159`` is hardcoded; an omitted entry is silently inert — see
``reference-requirement-types-hardcoded-list``).
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory
from world.magic.constants import GiftKind
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.progression.models import ClassLevelUnlock, MajorGiftTechniqueRequirement
from world.progression.services.spends import check_requirements_for_unlock


class MajorGiftTechniqueRequirementGiftFieldTests(TestCase):
    """``gift`` is scoped to MAJOR gifts only in the field definition (#4097 fix round 2)."""

    def test_limit_choices_to_scopes_to_major_gifts(self) -> None:
        field = MajorGiftTechniqueRequirement._meta.get_field("gift")
        assert field.get_limit_choices_to() == {"kind": GiftKind.MAJOR}


class MajorGiftTechniqueRequirementTests(TestCase):
    """Direct model-level is_met_by_character checks."""

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=2
        )

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)
        self.major_gift = GiftFactory(kind=GiftKind.MAJOR)
        self.minor_gift = GiftFactory(kind=GiftKind.MINOR)
        CharacterGiftFactory(character=self.sheet, gift=self.major_gift)

    def _grant_major_techniques(self, count: int) -> None:
        for _ in range(count):
            technique = TechniqueFactory(gift=self.major_gift)
            CharacterTechniqueFactory(character=self.sheet, technique=technique)

    def test_below_threshold_is_unmet(self) -> None:
        self._grant_major_techniques(2)
        req = MajorGiftTechniqueRequirement.objects.create(
            class_level_unlock=self.unlock, minimum_techniques=3
        )

        met, message = req.is_met_by_character(self.character)

        assert met is False
        assert "Need 3" in message

    def test_at_threshold_is_met(self) -> None:
        self._grant_major_techniques(3)
        req = MajorGiftTechniqueRequirement.objects.create(
            class_level_unlock=self.unlock, minimum_techniques=3
        )

        met, message = req.is_met_by_character(self.character)

        assert met is True
        assert "Knows 3" in message

    def test_minor_gift_techniques_do_not_count(self) -> None:
        # 3 techniques of the MINOR gift — none of the MAJOR gift.
        for _ in range(3):
            technique = TechniqueFactory(gift=self.minor_gift)
            CharacterTechniqueFactory(character=self.sheet, technique=technique)
        req = MajorGiftTechniqueRequirement.objects.create(
            class_level_unlock=self.unlock, minimum_techniques=3
        )

        met, message = req.is_met_by_character(self.character)

        assert met is False
        assert "have 0" in message

    def test_no_major_gift_is_unmet(self) -> None:
        # Character with no CharacterGift row at all (overrides setUp's grant
        # by using a fresh sheet).
        other_character = CharacterFactory()
        CharacterSheetFactory(character=other_character)
        req = MajorGiftTechniqueRequirement.objects.create(
            class_level_unlock=self.unlock, minimum_techniques=3
        )

        met, message = req.is_met_by_character(other_character)

        assert met is False
        assert "no major gift" in message

    def test_blank_gift_two_major_gifts_the_one_reaching_threshold_counts(self) -> None:
        # self.major_gift (from setUp) holds 2; a second major gift holds 3.
        self._grant_major_techniques(2)
        second_major_gift = GiftFactory(kind=GiftKind.MAJOR)
        CharacterGiftFactory(character=self.sheet, gift=second_major_gift)
        for _ in range(3):
            technique = TechniqueFactory(gift=second_major_gift)
            CharacterTechniqueFactory(character=self.sheet, technique=technique)
        req = MajorGiftTechniqueRequirement.objects.create(
            class_level_unlock=self.unlock, minimum_techniques=3
        )

        met, message = req.is_met_by_character(self.character)

        assert met is True
        assert "Knows 3" in message

    def test_blank_gift_two_major_gifts_neither_reaching_threshold_never_summed(self) -> None:
        # self.major_gift (from setUp) holds 2; a second major gift also holds
        # 2 — the combined total (4) must never satisfy the gate.
        self._grant_major_techniques(2)
        second_major_gift = GiftFactory(kind=GiftKind.MAJOR)
        CharacterGiftFactory(character=self.sheet, gift=second_major_gift)
        for _ in range(2):
            technique = TechniqueFactory(gift=second_major_gift)
            CharacterTechniqueFactory(character=self.sheet, technique=technique)
        req = MajorGiftTechniqueRequirement.objects.create(
            class_level_unlock=self.unlock, minimum_techniques=3
        )

        met, _message = req.is_met_by_character(self.character)

        assert met is False

    def test_blank_gift_tie_message_is_deterministic_by_gift_name(self) -> None:
        """A tied-count failure message names the alphabetically-first gift (#4097 fix
        round 2) — not whichever row the DB returns first with no explicit ordering."""
        gift_z = GiftFactory(kind=GiftKind.MAJOR, name="Zephyrwing")
        gift_a = GiftFactory(kind=GiftKind.MAJOR, name="Aldermoth")
        other_sheet = CharacterSheetFactory()
        other_character = other_sheet.character
        # Attach in reverse-alpha order to prove the result doesn't ride
        # insertion/query-default ordering.
        CharacterGiftFactory(character=other_sheet, gift=gift_z)
        CharacterGiftFactory(character=other_sheet, gift=gift_a)
        for gift in (gift_a, gift_z):
            technique = TechniqueFactory(gift=gift)
            CharacterTechniqueFactory(character=other_sheet, technique=technique)
        req = MajorGiftTechniqueRequirement.objects.create(
            class_level_unlock=self.unlock, minimum_techniques=3
        )

        met, message = req.is_met_by_character(other_character)

        assert met is False
        assert "Aldermoth" in message
        assert "Zephyrwing" not in message

    def test_named_gift_only_that_gift_counts(self) -> None:
        # self.major_gift holds 2; a second major gift holds 5. Naming
        # self.major_gift means only its 2 count.
        self._grant_major_techniques(2)
        other_major_gift = GiftFactory(kind=GiftKind.MAJOR)
        CharacterGiftFactory(character=self.sheet, gift=other_major_gift)
        for _ in range(5):
            technique = TechniqueFactory(gift=other_major_gift)
            CharacterTechniqueFactory(character=self.sheet, technique=technique)
        req = MajorGiftTechniqueRequirement.objects.create(
            class_level_unlock=self.unlock,
            minimum_techniques=3,
            gift=self.major_gift,
        )

        met, message = req.is_met_by_character(self.character)

        assert met is False
        assert "have 2" in message

    def test_named_ancestor_gift_counts_via_held_descendant_lineage(self) -> None:
        """A held descendant gift reaches a named ancestor gift's techniques (#2891, #4097).

        ``resolve_owned_gift`` returns the held descendant when the named gift
        is reached only through its lineage; ``count_techniques_for_gift`` then
        counts the held gift's own techniques plus every ancestor's — so naming
        the ancestor here must still count techniques of the (unheld) ancestor
        itself, since they are learned against the descendant's single thread.
        """
        umbrella = GiftFactory(kind=GiftKind.MAJOR)
        descendant = GiftFactory(kind=GiftKind.MAJOR, parent=umbrella)
        CharacterGiftFactory(character=self.sheet, gift=descendant)
        for _ in range(3):
            technique = TechniqueFactory(gift=umbrella)
            CharacterTechniqueFactory(character=self.sheet, technique=technique)
        req = MajorGiftTechniqueRequirement.objects.create(
            class_level_unlock=self.unlock,
            minimum_techniques=3,
            gift=umbrella,
        )

        met, message = req.is_met_by_character(self.character)

        assert met is True
        assert "Knows 3" in message


class MajorGiftTechniqueRequirementRegistryWiringTests(TestCase):
    """Proves the type is actually wired into the hardcoded requirement_types list.

    An omitted entry in ``spends.py``'s ``requirement_types`` list is silently
    inert (the requirement row would simply never be evaluated) — this test
    goes through the real gate (``check_requirements_for_unlock``), not the
    model method directly, so a future accidental removal from the registry
    fails this test.
    """

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=2
        )
        MajorGiftTechniqueRequirement.objects.create(
            class_level_unlock=cls.unlock, minimum_techniques=3
        )

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)
        self.major_gift = GiftFactory(kind=GiftKind.MAJOR)
        CharacterGiftFactory(character=self.sheet, gift=self.major_gift)

    def test_fails_at_two_techniques(self) -> None:
        for _ in range(2):
            technique = TechniqueFactory(gift=self.major_gift)
            CharacterTechniqueFactory(character=self.sheet, technique=technique)

        met, failed = check_requirements_for_unlock(self.character, self.unlock)

        assert met is False
        assert any("Need 3" in msg for msg in failed)

    def test_passes_at_three_techniques(self) -> None:
        for _ in range(3):
            technique = TechniqueFactory(gift=self.major_gift)
            CharacterTechniqueFactory(character=self.sheet, technique=technique)

        met, failed = check_requirements_for_unlock(self.character, self.unlock)

        assert met is True
        assert failed == []
