"""Skill-gated quality cap clamp and quality resolution.

Provides ``resolve_capped_tier``, which computes a quality score from a check
result, optionally clamps it to the crafter's skill ceiling, and returns the
matching ``QualityTier``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.crafting.models import CraftingSkillCap
from world.items.exceptions import CraftingNotConfigured
from world.items.services.crafting import compute_quality_score

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.types import CheckResult
    from world.items.crafting.models import CraftingRecipe
    from world.items.models import QualityTier


def resolve_capped_tier(
    *,
    recipe: CraftingRecipe,
    crafter_character: ObjectDB,
    check_result: CheckResult,
) -> QualityTier:
    """Compute the quality tier for a crafting outcome, clamped by skill cap.

    1. Compute the raw quality score from the check result using the recipe's
       ``success_level_step`` and ``min_success_level``.
    2. Look up the crafter's rank in ``recipe.skill_trait``; find the highest
       ``CraftingSkillCap`` band the crafter qualifies for.
    3. If a cap exists, clamp the score to ``cap.numeric_max``.
    4. Resolve the (possibly clamped) score to a ``QualityTier`` and return it.

    Args:
        recipe: The ``CraftingRecipe`` driving this attempt.
        crafter_character: The ``ObjectDB`` whose ``traits`` handler is queried.
        check_result: A ``CheckResult`` (or compatible duck-typed object) exposing
            ``.total_points`` and ``.success_level``.

    Returns:
        The resolved ``QualityTier`` for this crafting outcome.

    Raises:
        CraftingNotConfigured: No ``QualityTier`` rows are seeded (``for_score``
            returns ``None`` only in an unconfigured deployment).
    """
    from world.items.models import QualityTier as _QualityTier  # noqa: PLC0415

    score = compute_quality_score(
        check_result,
        step=recipe.success_level_step,
        min_success_level=recipe.min_success_level,
    )

    skill = crafter_character.traits.get_trait_value(recipe.skill_trait.name)
    cap = CraftingSkillCap.for_skill(recipe, skill)
    if cap is not None:
        score = min(score, cap.numeric_max)

    tier = _QualityTier.for_score(score)
    if tier is None:
        raise CraftingNotConfigured
    return tier
