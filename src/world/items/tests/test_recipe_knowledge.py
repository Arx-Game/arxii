"""Recipe knowledge — gating, granting, teaching (#2242)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.crafting.constants import CraftingRecipeKind
from world.items.crafting.knowledge import (
    character_knows_recipe,
    grant_recipe_knowledge,
    teach_recipe,
)
from world.items.crafting.models import CharacterRecipeKnowledge, CraftingRecipe
from world.items.exceptions import RecipeNotKnown


def _gated_recipe(name="Secret Pattern"):
    return CraftingRecipe.objects.create(
        name=name, kind=CraftingRecipeKind.FACET_ATTACH, requires_knowledge=True
    )


def _open_recipe(name="Common Pattern"):
    return CraftingRecipe.objects.create(
        name=name, kind=CraftingRecipeKind.FACET_ATTACH, requires_knowledge=False
    )


class RecipeKnowledgeTests(TestCase):
    def test_open_recipe_is_known_to_everyone(self):
        self.assertTrue(character_knows_recipe(CharacterSheetFactory(), _open_recipe()))

    def test_gated_recipe_is_unknown_without_a_row(self):
        self.assertFalse(character_knows_recipe(CharacterSheetFactory(), _gated_recipe()))

    def test_grant_makes_a_gated_recipe_known(self):
        sheet = CharacterSheetFactory()
        recipe = _gated_recipe()
        grant_recipe_knowledge(sheet, recipe)
        self.assertTrue(character_knows_recipe(sheet, recipe))

    def test_grant_is_idempotent(self):
        sheet = CharacterSheetFactory()
        recipe = _gated_recipe()
        grant_recipe_knowledge(sheet, recipe)
        grant_recipe_knowledge(sheet, recipe)
        self.assertEqual(
            CharacterRecipeKnowledge.objects.filter(character_sheet=sheet, recipe=recipe).count(), 1
        )

    def test_teaching_requires_the_teacher_to_know_it(self):
        recipe = _gated_recipe()
        with self.assertRaises(RecipeNotKnown):
            teach_recipe(
                teacher_sheet=CharacterSheetFactory(),
                learner_sheet=CharacterSheetFactory(),
                recipe=recipe,
            )

    def test_teaching_grants_the_learner(self):
        teacher = CharacterSheetFactory()
        learner = CharacterSheetFactory()
        recipe = _gated_recipe()
        grant_recipe_knowledge(teacher, recipe)
        teach_recipe(teacher_sheet=teacher, learner_sheet=learner, recipe=recipe)
        self.assertTrue(character_knows_recipe(learner, recipe))
