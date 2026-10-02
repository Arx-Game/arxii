"""Tests for GiftHeldRequirement and TechniqueKnownRequirement (#4097).

GiftHeldRequirement: named gift mode is lineage-aware via resolve_owned_gift
(a held descendant gift reaching the named gift satisfies it); blank-gift mode
is satisfied by holding any gift at all. TechniqueKnownRequirement: a flat
"already knows this technique" prerequisite gate.

Path-entry wiring through check_requirements_for_path is proven in Task 3 once
GiftHeldRequirement joins that evaluator's hardcoded hand list (see
reference-requirement-types-hardcoded-list) — not here.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.progression.models import (
    ClassLevelUnlock,
    GiftHeldRequirement,
    TechniqueKnownRequirement,
)


class GiftHeldRequirementTests(TestCase):
    """Named-gift (lineage-aware) and blank-gift (any held gift) behaviour."""

    @classmethod
    def setUpTestData(cls):
        character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=character_class, target_level=3
        )

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_named_gift_unmet_without_it(self) -> None:
        gift = GiftFactory()
        req = GiftHeldRequirement.objects.create(class_level_unlock=self.unlock, gift=gift)

        met, message = req.is_met_by_character(self.character)

        assert met is False
        assert gift.name in message

    def test_named_gift_met_holding_it_directly(self) -> None:
        gift = GiftFactory()
        CharacterGiftFactory(character=self.sheet, gift=gift)
        req = GiftHeldRequirement.objects.create(class_level_unlock=self.unlock, gift=gift)

        met, message = req.is_met_by_character(self.character)

        assert met is True
        assert gift.name in message

    def test_named_gift_met_holding_a_child_gift(self) -> None:
        parent_gift = GiftFactory()
        child_gift = GiftFactory(parent=parent_gift)
        CharacterGiftFactory(character=self.sheet, gift=child_gift)
        req = GiftHeldRequirement.objects.create(class_level_unlock=self.unlock, gift=parent_gift)

        met, message = req.is_met_by_character(self.character)

        assert met is True
        assert parent_gift.name in message

    def test_blank_gift_unmet_holding_no_gift(self) -> None:
        req = GiftHeldRequirement.objects.create(class_level_unlock=self.unlock, gift=None)

        met, _message = req.is_met_by_character(self.character)

        assert met is False

    def test_blank_gift_met_holding_any_gift(self) -> None:
        gift = GiftFactory()
        CharacterGiftFactory(character=self.sheet, gift=gift)
        req = GiftHeldRequirement.objects.create(class_level_unlock=self.unlock, gift=None)

        met, _message = req.is_met_by_character(self.character)

        assert met is True


class TechniqueKnownRequirementTests(TestCase):
    """Flat "already knows this technique" prerequisite gate."""

    @classmethod
    def setUpTestData(cls):
        character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=character_class, target_level=3
        )

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_unmet_without_the_technique(self) -> None:
        technique = TechniqueFactory()
        req = TechniqueKnownRequirement.objects.create(
            class_level_unlock=self.unlock, required_technique=technique
        )

        met, message = req.is_met_by_character(self.character)

        assert met is False
        assert technique.name in message

    def test_met_knowing_the_technique(self) -> None:
        technique = TechniqueFactory()
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        req = TechniqueKnownRequirement.objects.create(
            class_level_unlock=self.unlock, required_technique=technique
        )

        met, message = req.is_met_by_character(self.character)

        assert met is True
        assert technique.name in message
