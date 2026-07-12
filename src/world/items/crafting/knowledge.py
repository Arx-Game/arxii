"""Recipe knowledge — who may craft or browse a gated recipe (#2242).

By default a recipe is *open* (``requires_knowledge=False``): anyone with the
skill, materials, and station can make it. A recipe flagged
``requires_knowledge`` is a *pattern* — only a character who has learned it (a
``CharacterRecipeKnowledge`` row) may browse or craft it. Acquisition seams:
``teach_recipe`` (an information economy — who knows the alaricite pattern) and
``grant_recipe_knowledge`` (GM award / a future discovery hook off the clue loop).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.exceptions import RecipeNotKnown

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.items.crafting.models import CharacterRecipeKnowledge, CraftingRecipe


def character_knows_recipe(character_sheet: CharacterSheet, recipe: CraftingRecipe) -> bool:
    """Whether ``character_sheet`` may craft/browse ``recipe`` (#2242).

    Open recipes are known to everyone; a gated recipe needs a knowledge row.
    """
    if not recipe.requires_knowledge:
        return True
    from world.items.crafting.models import CharacterRecipeKnowledge  # noqa: PLC0415

    return CharacterRecipeKnowledge.objects.filter(
        character_sheet=character_sheet, recipe=recipe
    ).exists()


def grant_recipe_knowledge(
    character_sheet: CharacterSheet, recipe: CraftingRecipe
) -> CharacterRecipeKnowledge:
    """Teach ``character_sheet`` a recipe (GM grant / discovery seam). Idempotent."""
    from world.items.crafting.models import CharacterRecipeKnowledge  # noqa: PLC0415

    knowledge, _ = CharacterRecipeKnowledge.objects.get_or_create(
        character_sheet=character_sheet, recipe=recipe
    )
    return knowledge


def teach_recipe(
    *, teacher_sheet: CharacterSheet, learner_sheet: CharacterSheet, recipe: CraftingRecipe
) -> CharacterRecipeKnowledge:
    """One character teaches another a recipe they know (#2242).

    The teacher must know the recipe (an open recipe counts as known); the learner
    gains ``CharacterRecipeKnowledge``. Raises ``RecipeNotKnown`` otherwise.
    """
    if not character_knows_recipe(teacher_sheet, recipe):
        msg = "You can't teach a recipe you don't know."
        raise RecipeNotKnown(msg)
    return grant_recipe_knowledge(learner_sheet, recipe)
