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

    from actions.models.consequence_pools import ConsequencePool
    from actions.types import WeightedConsequence
    from world.checks.models import CheckType, Consequence
    from world.checks.types import CheckResult, ResolutionContext


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


def select_consequence_from_result(
    character: ObjectDB,
    check_result: CheckResult,
    consequences: list[WeightedConsequence],
) -> PendingResolution:
    """Select a consequence using an existing check result.

    Same tier filtering, weighted selection, and character loss filtering
    as select_consequence(), but skips perform_check() — reuses the
    provided result. Used for context pools that share the main action's roll.

    WeightedConsequence exposes .weight, .character_loss, .outcome_tier
    attributes so select_weighted() and filter_character_loss() work via
    duck-typed getattr().
    """
    from world.checks.models import Consequence as ConsequenceModel  # noqa: PLC0415

    outcome = check_result.outcome
    tier_consequences = [c for c in consequences if c.outcome_tier == outcome]

    if tier_consequences:
        selected = select_weighted(tier_consequences)
        selected = filter_character_loss(character, selected, tier_consequences)
    else:
        selected = ConsequenceModel(
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

    Unwraps WeightedConsequence to the underlying Consequence model
    when the selected_consequence comes from a pool-based resolution.
    """
    from actions.types import WeightedConsequence  # noqa: PLC0415
    from world.mechanics.effect_handlers import apply_all_effects  # noqa: PLC0415

    consequence = pending.selected_consequence
    if isinstance(consequence, WeightedConsequence):
        consequence = consequence.consequence

    return apply_all_effects(consequence, context)


def apply_pool_deterministically(
    *,
    pool: ConsequencePool,
    context: ResolutionContext,
) -> list[AppliedEffect]:
    """Run every Consequence in the pool (including inherited parent rows
    where not excluded). No weighted selection — deterministic application
    used by Story-beat outcome resolution. Returns the flattened list of
    applied effects for caller introspection / tests / audit.

    Walks parent pool first (in declaration order, skipping is_excluded rows
    from the child), then child pool entries. This mirrors how
    select_consequence handles inheritance.
    """
    from world.mechanics.effect_handlers import apply_all_effects  # noqa: PLC0415

    consequences = resolve_pool_consequences(pool)
    applied: list[AppliedEffect] = []
    for c in consequences:
        applied.extend(apply_all_effects(c, context))
    return applied


def resolve_pool_consequences(pool: ConsequencePool) -> list[Consequence]:
    """Walk pool + parent, honoring is_excluded child entries. Returns the
    flat list of Consequence rows to fire (in declaration order: parent first).

    Public alias for beat resolution wiring and other callers that need to
    inspect the pool's full consequence list without firing effects.
    """
    own_entries = list(pool.entries.select_related("consequence"))
    if pool.parent_id is None:
        return [e.consequence for e in own_entries if not e.is_excluded]

    excluded_ids = {e.consequence_id for e in own_entries if e.is_excluded}
    parent_consequences = [
        e.consequence
        for e in pool.parent.entries.select_related("consequence")
        if e.consequence_id not in excluded_ids
    ]
    own_included = [e.consequence for e in own_entries if not e.is_excluded]
    return parent_consequences + own_included


# Private alias preserved for backward compatibility.
_resolve_pool_consequences = resolve_pool_consequences
