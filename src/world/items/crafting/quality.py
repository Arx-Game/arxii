"""Skill-gated quality cap clamp and quality resolution.

Provides ``resolve_capped_tier``, which computes a quality score from a check
result, optionally clamps it to the crafter's skill ceiling, and returns the
matching ``QualityTier``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.items.crafting.constants import BASE_MAX_QUALITY_RUNG
from world.items.crafting.models import CraftingSkillCap
from world.items.exceptions import CraftingNotConfigured
from world.items.services.crafting import compute_quality_score

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.types import CheckResult
    from world.items.crafting.models import CraftingRecipe
    from world.items.models import QualityTier
    from world.traits.models import Trait


def thread_count_for_skill(crafter_character: ObjectDB, skill_trait: Trait | None) -> int:
    """Active threads the crafter has woven into ``skill_trait`` (#2878).

    Counts non-retired TRAIT-anchored ``Thread`` rows on the crafter's sheet.
    Each one raises the reachable quality rung (and accent level) by one —
    this is how divine-and-above stays Gifted-only.
    """
    if skill_trait is None:
        return 0
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models.threads import Thread  # noqa: PLC0415

    return Thread.objects.filter(
        owner__character=crafter_character,
        target_kind=TargetKind.TRAIT,
        target_trait=skill_trait,
        retired_at__isnull=True,
    ).count()


def _recipe_specialization_value(crafter_character: ObjectDB, recipe: CraftingRecipe) -> int:
    """The crafter's value in the recipe's specialization, or 0 (#2886).

    Specialization is ADDITIVE with the skill everywhere (Apostate: skill 50 +
    spec 50 ≡ skill 100) — this feeds the cap lookup; the roll gets it via
    the runtime-specialization path in perform_check.
    """
    if recipe.specialization_id is None:
        return 0
    from world.skills.services import get_specialization_value  # noqa: PLC0415

    return get_specialization_value(crafter_character, recipe.specialization)


def _thread_ceiling_clamp(score: int, allowed_rung: int) -> int:
    """Clamp ``score`` to the top of the highest quality rung ≤ ``allowed_rung``.

    Rung = ``QualityTier.sort_order``. No-op when the ladder has no rows above
    the allowed rung (short test ladders, unconfigured deployments) — the cap
    only bites when there is genuinely a tier the crafter cannot reach.
    """
    from world.items.models import QualityTier  # noqa: PLC0415

    beyond = QualityTier.objects.filter(sort_order__gt=allowed_rung).exists()
    if not beyond:
        return score
    ceiling = (
        QualityTier.objects.filter(sort_order__lte=allowed_rung).order_by("-sort_order").first()
    )
    if ceiling is None:
        return score
    return min(score, ceiling.numeric_max)


def resolve_capped_tier(
    *,
    recipe: CraftingRecipe,
    crafter_character: ObjectDB,
    check_result: CheckResult,
    material_grade_bonus: int = 0,
    thread_count: int | None = None,
) -> QualityTier:
    """Compute the quality tier for a crafting outcome, clamped by skill cap.

    1. Compute the raw quality score from the check result using the recipe's
       ``success_level_step`` and ``min_success_level``, plus the staged
       materials' grade term (#2878) — the material's head start toward the
       fixed quality landscape. Divine silk is a master's good day; divine
       plain cloth means the roll covered the whole distance unaided.
    2. Look up the crafter's rank in ``recipe.skill_trait``; find the highest
       ``CraftingSkillCap`` band the crafter qualifies for.
    3. If a cap exists, clamp the score to ``cap.numeric_max``.
    4. Clamp to the thread-capped rung (#2878): base rung
       ``BASE_MAX_QUALITY_RUNG`` plus one per thread woven into the skill.
    5. Resolve the (possibly clamped) score to a ``QualityTier`` and return it.

    Args:
        recipe: The ``CraftingRecipe`` driving this attempt.
        crafter_character: The ``ObjectDB`` whose ``traits`` handler is queried.
        check_result: A ``CheckResult`` (or compatible duck-typed object) exposing
            ``.total_points`` and ``.success_level``.
        material_grade_bonus: Quantity-weighted mean ``material_grade`` of the
            staged materials (0 when the recipe stages none).

    Returns:
        The resolved ``QualityTier`` for this crafting outcome.

    Raises:
        CraftingNotConfigured: No ``QualityTier`` rows are seeded (``for_score``
            returns ``None`` only in an unconfigured deployment).
    """
    from world.items.models import QualityTier  # noqa: PLC0415

    score = (
        compute_quality_score(
            check_result,
            step=recipe.success_level_step,
            min_success_level=recipe.min_success_level,
        )
        + material_grade_bonus
    )

    if recipe.skill_trait is not None:
        skill = crafter_character.traits.get_trait_value(recipe.skill_trait.name)
        skill += _recipe_specialization_value(crafter_character, recipe)
        cap_tier = CraftingSkillCap.for_skill(recipe, skill)
        if cap_tier is not None:
            score = min(score, cap_tier.numeric_max)

    threads = (
        thread_count
        if thread_count is not None
        else thread_count_for_skill(crafter_character, recipe.skill_trait)
    )
    score = _thread_ceiling_clamp(score, BASE_MAX_QUALITY_RUNG + threads)

    tier = QualityTier.for_score(score)
    if tier is None:
        raise CraftingNotConfigured
    return tier
