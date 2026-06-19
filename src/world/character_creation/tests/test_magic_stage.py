"""Tests for magic stage validation with cantrip selection."""

from django.test import TestCase

from actions.constants import ActionCategory
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.services import finalize_magic_data
from world.character_creation.validators import compute_magic_errors
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.fatigue.models import FatiguePool
from world.magic.factories import CantripFactory, FacetFactory
from world.magic.models import CharacterAnima, Technique


class MagicFinalizationActionCategoryTest(TestCase):
    """finalize_magic_data derives the technique's action_category from the Path."""

    def test_technique_action_category_derives_from_path(self):
        path = PathFactory(action_category=ActionCategory.MENTAL)
        cantrip = CantripFactory()
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(
            selected_path=path,
            draft_data={"selected_cantrip_id": cantrip.id},
        )
        finalize_magic_data(draft, sheet)
        technique = Technique.objects.get(source_cantrip=cantrip, creator=sheet)
        self.assertEqual(technique.action_category, ActionCategory.MENTAL)


class MagicStageValidationTest(TestCase):
    """Test compute_magic_errors with cantrip-based validation."""

    @classmethod
    def setUpTestData(cls):
        cls.innate_cantrip = CantripFactory(
            name="Danger Sense",
            requires_facet=False,
        )
        cls.manifested_cantrip = CantripFactory(
            name="Elemental Strike",
            requires_facet=True,
            facet_prompt="Choose your element",
        )
        fire = FacetFactory(name="Fire")
        ice = FacetFactory(name="Ice")
        cls.manifested_cantrip.allowed_facets.add(fire, ice)
        cls.fire = fire
        cls.unrelated_facet = FacetFactory(name="Wolf")

    def test_no_cantrip_selected_returns_error(self):
        draft = CharacterDraftFactory()
        errors = compute_magic_errors(draft)
        assert "Select a cantrip" in errors

    def test_innate_cantrip_selected_passes(self):
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": self.innate_cantrip.id},
        )
        errors = compute_magic_errors(draft)
        assert errors == []

    def test_manifested_cantrip_without_facet_fails(self):
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": self.manifested_cantrip.id},
        )
        errors = compute_magic_errors(draft)
        assert any(
            "element" in e.lower() or "facet" in e.lower() or "type" in e.lower() for e in errors
        )

    def test_manifested_cantrip_with_valid_facet_passes(self):
        draft = CharacterDraftFactory(
            draft_data={
                "selected_cantrip_id": self.manifested_cantrip.id,
                "selected_facet_id": self.fire.id,
            },
        )
        errors = compute_magic_errors(draft)
        assert errors == []

    def test_manifested_cantrip_with_invalid_facet_fails(self):
        draft = CharacterDraftFactory(
            draft_data={
                "selected_cantrip_id": self.manifested_cantrip.id,
                "selected_facet_id": self.unrelated_facet.id,
            },
        )
        errors = compute_magic_errors(draft)
        assert len(errors) > 0

    def test_inactive_cantrip_fails(self):
        inactive = CantripFactory(is_active=False)
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": inactive.id},
        )
        errors = compute_magic_errors(draft)
        assert len(errors) > 0


class MagicFinalizationCGSeedingTest(TestCase):
    """finalize_magic_data seeds CharacterAnima and FatiguePool at CG completion (Phase 12)."""

    def _make_draft_and_sheet(self):
        cantrip = CantripFactory()
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(
            draft_data={"selected_cantrip_id": cantrip.id},
        )
        return draft, sheet

    def test_finalize_seeds_character_anima_row(self):
        """finalize_magic_data creates a CharacterAnima row for the new character."""
        draft, sheet = self._make_draft_and_sheet()
        self.assertFalse(
            CharacterAnima.objects.filter(character=sheet.character).exists(),
            "CharacterAnima must not exist before finalize",
        )
        finalize_magic_data(draft, sheet)
        self.assertTrue(
            CharacterAnima.objects.filter(character=sheet.character).exists(),
            "CharacterAnima should be seeded by finalize_magic_data",
        )

    def test_finalize_seeds_fatigue_pool_row(self):
        """finalize_magic_data creates a FatiguePool row for the new character sheet."""
        draft, sheet = self._make_draft_and_sheet()
        self.assertFalse(
            FatiguePool.objects.filter(character_sheet=sheet).exists(),
            "FatiguePool must not exist before finalize",
        )
        finalize_magic_data(draft, sheet)
        self.assertTrue(
            FatiguePool.objects.filter(character_sheet=sheet).exists(),
            "FatiguePool should be seeded by finalize_magic_data",
        )

    def test_finalize_character_anima_defaults(self):
        """Seeded CharacterAnima has sensible defaults (current=10, maximum=10)."""
        draft, sheet = self._make_draft_and_sheet()
        finalize_magic_data(draft, sheet)
        anima = CharacterAnima.objects.get(character=sheet.character)
        self.assertEqual(anima.current, 10)
        self.assertEqual(anima.maximum, 10)

    def test_seeding_is_idempotent_via_get_or_create(self):
        """CharacterAnima and FatiguePool use get_or_create — second call is a no-op."""
        from world.fatigue.services import get_or_create_fatigue_pool

        draft, sheet = self._make_draft_and_sheet()
        finalize_magic_data(draft, sheet)
        # Calling the seeding helpers again must not raise or create duplicates.
        CharacterAnima.objects.get_or_create(
            character=sheet.character,
            defaults={"current": 10, "maximum": 10},
        )
        get_or_create_fatigue_pool(sheet)
        self.assertEqual(CharacterAnima.objects.filter(character=sheet.character).count(), 1)
        self.assertEqual(FatiguePool.objects.filter(character_sheet=sheet).count(), 1)
