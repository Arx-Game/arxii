"""Tests for ItemRequirement: dual match-mode constraint + possession checks (#1859)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
    ResonanceTierFactory,
)
from world.progression.models import ClassLevelUnlock, ItemRequirement
from world.progression.services.spends import (
    check_requirements_for_unlock,
    get_available_unlocks_for_character,
)


class ItemRequirementConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )

    def test_template_mode_row(self) -> None:
        template = ItemTemplateFactory()
        req = ItemRequirement.objects.create(class_level_unlock=self.unlock, item_template=template)
        assert req.item_template_id == template.pk
        assert req.min_touchstone_tier_id is None

    def test_touchstone_mode_row(self) -> None:
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, min_touchstone_tier=tier
        )
        assert req.item_template_id is None
        assert req.min_touchstone_tier_id == tier.pk

    def test_neither_set_is_rejected(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemRequirement.objects.create(class_level_unlock=self.unlock)

    def test_both_set_is_rejected(self) -> None:
        template = ItemTemplateFactory()
        tier = ResonanceTierFactory(name="Faint", tier_level=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemRequirement.objects.create(
                class_level_unlock=self.unlock,
                item_template=template,
                min_touchstone_tier=tier,
            )


class ItemRequirementTemplateModePossessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.template = ItemTemplateFactory()

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_missing_item_fails(self) -> None:
        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, item_template=self.template, quantity=1
        )
        met, message = req.is_met_by_character(self.character)
        assert met is False
        assert "Need 1x" in message

    def test_single_matching_instance_satisfies(self) -> None:
        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, item_template=self.template, quantity=1
        )
        ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)
        met, message = req.is_met_by_character(self.character)
        assert met is True
        assert "Has 1x" in message

    def test_quantity_aggregates_across_stacks(self) -> None:
        """Two separate stacks of 1 satisfy a quantity=2 requirement."""
        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, item_template=self.template, quantity=2
        )
        ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet, quantity=1)
        ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet, quantity=1)
        met, _message = req.is_met_by_character(self.character)
        assert met is True

    def test_destroyed_instance_does_not_count(self) -> None:
        from django.utils import timezone

        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, item_template=self.template, quantity=1
        )
        ItemInstanceFactory(
            template=self.template,
            holder_character_sheet=self.sheet,
            destroyed_at=timezone.now(),
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is False

    def test_wrong_holder_does_not_count(self) -> None:
        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, item_template=self.template, quantity=1
        )
        other_character = CharacterFactory()
        other_sheet = CharacterSheetFactory(character=other_character)
        ItemInstanceFactory(template=self.template, holder_character_sheet=other_sheet)
        met, _message = req.is_met_by_character(self.character)
        assert met is False


class ItemRequirementTouchstoneModePossessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.praedari = ResonanceFactory(name="Praedari_1859")
        cls.copperi = ResonanceFactory(name="Copperi_1859")
        cls.tier1 = ResonanceTierFactory(name="Faint_1859", tier_level=1)
        cls.tier2 = ResonanceTierFactory(name="Resonant_1859", tier_level=2)

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)

    def _touchstone(self, *, resonance, tier, attuned_to=None, holder=None):
        template = ItemTemplateFactory(tied_resonance=resonance, resonance_tier=tier)
        return ItemInstanceFactory(
            template=template,
            attuned_to_character_sheet=attuned_to,
            holder_character_sheet=holder,
        )

    def test_attuned_matching_resonance_satisfies(self) -> None:
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.praedari)
        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, min_touchstone_tier=self.tier1
        )
        self._touchstone(
            resonance=self.praedari, tier=self.tier1, attuned_to=self.sheet, holder=self.sheet
        )
        met, message = req.is_met_by_character(self.character)
        assert met is True
        assert "Has touchstone" in message

    def test_higher_tier_satisfies_lower_requirement(self) -> None:
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.praedari)
        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, min_touchstone_tier=self.tier1
        )
        self._touchstone(
            resonance=self.praedari, tier=self.tier2, attuned_to=self.sheet, holder=self.sheet
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is True

    def test_unattuned_instance_does_not_satisfy(self) -> None:
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.praedari)
        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, min_touchstone_tier=self.tier1
        )
        self._touchstone(resonance=self.praedari, tier=self.tier1, holder=self.sheet)
        met, message = req.is_met_by_character(self.character)
        assert met is False
        assert "Need an attuned touchstone" in message

    def test_unclaimed_resonance_does_not_satisfy(self) -> None:
        """No CharacterResonance for copperi -> a copperi touchstone can't match."""
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.praedari)
        req = ItemRequirement.objects.create(
            class_level_unlock=self.unlock, min_touchstone_tier=self.tier1
        )
        self._touchstone(
            resonance=self.copperi, tier=self.tier1, attuned_to=self.sheet, holder=self.sheet
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is False


class ItemRequirementWiringTests(TestCase):
    """Proves ItemRequirement reaches check_requirements_for_unlock's real callers."""

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.template = ItemTemplateFactory()
        ItemRequirement.objects.create(
            class_level_unlock=cls.unlock, item_template=cls.template, quantity=1
        )

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)
        CharacterClassLevelFactory(
            character=self.character,
            character_class=self.character_class,
            level=3,
            is_primary=True,
        )

    def test_check_requirements_for_unlock_blocks_without_item(self) -> None:
        met, failed = check_requirements_for_unlock(self.character, self.unlock)
        assert met is False
        assert any("Need 1x" in msg for msg in failed)

    def test_check_requirements_for_unlock_passes_with_item(self) -> None:
        ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)
        met, failed = check_requirements_for_unlock(self.character, self.unlock)
        assert met is True
        assert failed == []

    def test_get_available_unlocks_surfaces_locked_reason(self) -> None:
        result = get_available_unlocks_for_character(self.character)
        locked_entry = next(
            e
            for e in result["locked"]
            if e["unlock"].character_class_id == self.character_class.pk
            and e["unlock"].target_level == 4
        )
        assert any("Need 1x" in msg for msg in locked_entry["failed_requirements"])
