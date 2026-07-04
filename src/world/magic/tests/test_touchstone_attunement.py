"""Tests for attune_touchstone() (#707)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.ritual import PerformRitualAction
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.magic.exceptions import RitualComponentError
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory, ResonanceTierFactory
from world.magic.seeds_touchstones import ATTUNEMENT_RITUAL_NAME, ensure_attunement_ritual
from world.magic.services.touchstones import attune_touchstone


class AttuneTouchstoneTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory(name="Praedari")
        self.tier = ResonanceTierFactory(name="Faint", tier_level=1)
        self.template = ItemTemplateFactory(tied_resonance=self.resonance, resonance_tier=self.tier)

    def test_attunes_item_the_performer_holds_and_has_claimed_resonance_for(self) -> None:
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        instance = ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)
        result = attune_touchstone(character_sheet=self.sheet, ritual=None, item_instance=instance)
        result.refresh_from_db()
        assert result.attuned_to_character_sheet_id == self.sheet.pk
        assert result.attuned_at is not None

    def test_rejects_non_resonance_tied_item(self) -> None:
        plain_template = ItemTemplateFactory()
        instance = ItemInstanceFactory(template=plain_template, holder_character_sheet=self.sheet)
        with self.assertRaises(RitualComponentError):
            attune_touchstone(character_sheet=self.sheet, ritual=None, item_instance=instance)

    def test_rejects_when_performer_does_not_hold_item(self) -> None:
        other_sheet = CharacterSheetFactory()
        instance = ItemInstanceFactory(template=self.template, holder_character_sheet=other_sheet)
        with self.assertRaises(RitualComponentError):
            attune_touchstone(character_sheet=self.sheet, ritual=None, item_instance=instance)

    def test_rejects_already_attuned_item(self) -> None:
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        instance = ItemInstanceFactory(
            template=self.template,
            holder_character_sheet=self.sheet,
            attuned_to_character_sheet=self.sheet,
        )
        with self.assertRaises(RitualComponentError):
            attune_touchstone(character_sheet=self.sheet, ritual=None, item_instance=instance)

    def test_rejects_unclaimed_resonance(self) -> None:
        instance = ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)
        with self.assertRaises(RitualComponentError):
            attune_touchstone(character_sheet=self.sheet, ritual=None, item_instance=instance)


class PerformRitualActionAttunementIntegrationTests(TestCase):
    """Proves the SERVICE dispatch branch actually drives attune_touchstone() (#707).

    Task 6's reviewer flagged that no test in this plan dispatches a real
    "Rite of Attunement" Ritual row through PerformRitualAction end-to-end —
    only attune_touchstone() called directly, unit-style. This closes that gap.
    """

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.character.sheet_data = self.sheet
        self.resonance = ResonanceFactory(name="Praedari")
        self.tier = ResonanceTierFactory(name="Faint", tier_level=1)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)
        self.template = ItemTemplateFactory(tied_resonance=self.resonance, resonance_tier=self.tier)
        self.instance = ItemInstanceFactory(
            template=self.template, holder_character_sheet=self.sheet
        )

    def test_service_dispatch_drives_attune_touchstone_end_to_end(self) -> None:
        ritual = ensure_attunement_ritual()
        assert ritual.name == ATTUNEMENT_RITUAL_NAME

        action = PerformRitualAction()
        result = action.execute(self.character, ritual=ritual, item_instance=self.instance)

        assert result.success
        updated = ItemInstance.objects.get(pk=self.instance.pk)
        assert updated.attuned_to_character_sheet_id == self.sheet.pk
        assert updated.attuned_at is not None
