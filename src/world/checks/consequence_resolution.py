"""Generic consequence resolution pipeline.

Decoupled from challenges — any system can map check results to
weighted consequences using select_consequence() + apply_resolution().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.checks.models import Consequence
from world.checks.outcome_utils import filter_character_loss, select_weighted
from world.checks.services import perform_check
from world.checks.types import PendingResolution
from world.mechanics.types import AppliedEffect

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.checks.types import ResolutionContext


def select_consequence(
    character: ObjectDB,
    check_type: CheckType,
    target_difficulty: int,
    consequences: list[Consequence],
    extra_modifiers: int = 0,
) -> PendingResolution:
    """Perform a check and select a consequence from the pool.

    Does NOT apply any effects. Returns an intermediate result that can be
    inspected, modified (future: rerolled), or applied.

    The caller assembles the consequence list — this function does not know
    about challenge templates, approaches, or any domain-specific structure.
    It always applies character loss filtering.
    """
    check_result = perform_check(character, check_type, target_difficulty, extra_modifiers)

    outcome = check_result.outcome
    tier_consequences = [c for c in consequences if c.outcome_tier == outcome]

    if tier_consequences:
        selected = select_weighted(tier_consequences)
        selected = filter_character_loss(character, selected, tier_consequences)
    else:
        selected = Consequence(
            outcome_tier=outcome,
            label=str(outcome.name) if outcome else "Unknown",
            weight=1,
            character_loss=False,
        )

    return PendingResolution(
        check_result=check_result,
        selected_consequence=selected,
    )


def apply_resolution(
    pending: PendingResolution,
    context: ResolutionContext,
) -> list[AppliedEffect]:
    """Apply all effects from the selected consequence.

    Uses the ResolutionContext for target resolution and provenance.
    Returns empty list for unsaved (fallback) consequences.
    """
    from world.mechanics.effect_handlers import apply_all_effects  # noqa: PLC0415

    return apply_all_effects(pending.selected_consequence, context)
