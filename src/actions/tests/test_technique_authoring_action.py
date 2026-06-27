"""TDD tests for AuthorTechniqueAction (#1496).

Step 1: write failing tests before implementing the action.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.technique_authoring import AuthorTechniqueAction
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterGiftFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueStyleFactory,
)
from world.magic.models import (
    CharacterTechnique,
    Technique,
    TechniqueTierBudget,
)
from world.magic.services.technique_builder import get_technique_budget_config
from world.magic.types.technique_builder import TechniqueDesignInput


def _design(gift_id: int, style_id: int, effect_type_id: int, **over) -> TechniqueDesignInput:
    """Build a minimal within-budget Tier-1 design."""
    base = {
        "name": "Test Spell",
        "description": "A test spell.",
        "gift_id": gift_id,
        "style_id": style_id,
        "effect_type_id": effect_type_id,
        "action_category": "physical",
        "tier": 1,
        "intensity": 1,
        "control": 1,
        "anima_cost": 1,
        "level": 1,
    }
    base.update(over)
    return TechniqueDesignInput(**base)


class AuthorTechniqueActionSuccessTests(TestCase):
    """Player-path: gifted character authors a within-budget technique."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()
        CharacterGiftFactory(character=cls.sheet, gift=cls.gift)
        # Ensure Tier-1 budget exists with a permissive cap.
        TechniqueTierBudget.objects.get_or_create(
            tier=1,
            defaults={"power_budget": 100, "representative_level": 1, "label": "Tier 1"},
        )
        # Ensure the budget config singleton exists.
        get_technique_budget_config()

    def _actor(self):
        return self.sheet.character

    # ------------------------------------------------------------------
    # Success path
    # ------------------------------------------------------------------

    def test_success_returns_true(self) -> None:
        design = _design(self.gift.pk, self.style.pk, self.effect_type.pk)
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design)
        self.assertTrue(result.success, result.message)

    def test_success_carries_technique_in_data(self) -> None:
        design = _design(self.gift.pk, self.style.pk, self.effect_type.pk, name="Ember")
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design)
        self.assertTrue(result.success, result.message)
        technique = result.data.get("technique")
        self.assertIsNotNone(technique)
        self.assertIsInstance(technique, Technique)

    def test_success_carries_breakdown_in_data(self) -> None:
        design = _design(self.gift.pk, self.style.pk, self.effect_type.pk)
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design)
        self.assertTrue(result.success, result.message)
        self.assertIn("breakdown", result.data)

    def test_success_message_includes_technique_name(self) -> None:
        design = _design(self.gift.pk, self.style.pk, self.effect_type.pk, name="Inferno Surge")
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design)
        self.assertTrue(result.success, result.message)
        self.assertIn("Inferno Surge", result.message)

    def test_technique_row_created(self) -> None:
        design = _design(self.gift.pk, self.style.pk, self.effect_type.pk)
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design)
        self.assertTrue(result.success, result.message)
        tech = result.data["technique"]
        self.assertTrue(Technique.objects.filter(pk=tech.pk).exists())

    def test_character_technique_row_created(self) -> None:
        design = _design(self.gift.pk, self.style.pk, self.effect_type.pk)
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design)
        self.assertTrue(result.success, result.message)
        tech = result.data["technique"]
        self.assertTrue(
            CharacterTechnique.objects.filter(character=self.sheet, technique=tech).exists()
        )

    # ------------------------------------------------------------------
    # Over-budget failure path
    # ------------------------------------------------------------------

    def test_over_budget_returns_false(self) -> None:
        # intensity=100 costs 100 intensity_unit_cost (default=1) = 100 power;
        # default Tier-1 budget is 100 here, but control=1 makes total 101.
        # Use a tiny budget override instead.
        TechniqueTierBudget.objects.update_or_create(
            tier=1, defaults={"power_budget": 1, "representative_level": 1, "label": "Tier 1"}
        )
        design = _design(self.gift.pk, self.style.pk, self.effect_type.pk, intensity=10, control=10)
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design)
        # Restore before assertion so teardown is clean.
        TechniqueTierBudget.objects.update_or_create(
            tier=1, defaults={"power_budget": 100, "representative_level": 1, "label": "Tier 1"}
        )
        self.assertFalse(result.success)

    def test_over_budget_creates_no_rows(self) -> None:
        TechniqueTierBudget.objects.update_or_create(
            tier=1, defaults={"power_budget": 1, "representative_level": 1, "label": "Tier 1"}
        )
        design = _design(self.gift.pk, self.style.pk, self.effect_type.pk, intensity=10, control=10)
        before = Technique.objects.count()
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design)
        TechniqueTierBudget.objects.update_or_create(
            tier=1, defaults={"power_budget": 100, "representative_level": 1, "label": "Tier 1"}
        )
        self.assertFalse(result.success)
        self.assertEqual(Technique.objects.count(), before)

    # ------------------------------------------------------------------
    # Gift not owned
    # ------------------------------------------------------------------

    def test_gift_not_owned_returns_false(self) -> None:
        other_gift = GiftFactory()
        design = _design(other_gift.pk, self.style.pk, self.effect_type.pk)
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design)
        self.assertFalse(result.success)
        self.assertTrue(result.message)

    def test_gift_not_owned_creates_no_rows(self) -> None:
        other_gift = GiftFactory()
        design = _design(other_gift.pk, self.style.pk, self.effect_type.pk)
        before = Technique.objects.count()
        AuthorTechniqueAction().run(actor=self._actor(), design=design)
        self.assertEqual(Technique.objects.count(), before)


class AuthorTechniqueActionStaffTests(TestCase):
    """Staff path (as_staff=True): no gift ownership check, budget advisory."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()
        # Deliberately do NOT add a CharacterGift — staff bypasses ownership.
        TechniqueTierBudget.objects.get_or_create(
            tier=1,
            defaults={"power_budget": 100, "representative_level": 1, "label": "Tier 1"},
        )
        get_technique_budget_config()

    def _actor(self):
        return self.sheet.character

    def test_staff_author_succeeds_without_gift_ownership(self) -> None:
        design = _design(self.gift.pk, self.style.pk, self.effect_type.pk)
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design, as_staff=True)
        self.assertTrue(result.success, result.message)

    def test_staff_author_creates_technique_no_character_technique(self) -> None:
        design = _design(self.gift.pk, self.style.pk, self.effect_type.pk)
        result = AuthorTechniqueAction().run(actor=self._actor(), design=design, as_staff=True)
        self.assertTrue(result.success, result.message)
        tech = result.data["technique"]
        self.assertTrue(Technique.objects.filter(pk=tech.pk).exists())
        # Staff path does NOT bind a CharacterTechnique.
        self.assertFalse(
            CharacterTechnique.objects.filter(character=self.sheet, technique=tech).exists()
        )
