"""Attempt resolution service functions."""

import random
from typing import TYPE_CHECKING, Optional

from world.attempts.models import AttemptConsequence
from world.attempts.types import AttemptResult, ConsequenceDisplay
from world.checks.services import get_rollmod, perform_check

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.attempts.models import AttemptTemplate
    from world.traits.models import CheckOutcome


def resolve_attempt(
    character: "ObjectDB",
    attempt_template: "AttemptTemplate",
    target_difficulty: int = 0,
    extra_modifiers: int = 0,
) -> AttemptResult:
    """
    Resolve an attempt: run the check, select a consequence, apply loss filtering.

    1. Call perform_check with the template's check_type
    2. Gather consequences for the matching outcome tier
    3. Select a consequence (weighted random)
    4. Apply character loss filtering
    5. Build roulette display payload
    6. Return AttemptResult
    """
    check_result = perform_check(
        character,
        attempt_template.check_type,
        target_difficulty,
        extra_modifiers,
    )

    outcome = check_result.outcome
    all_consequences = list(attempt_template.consequences.select_related("outcome_tier").all())

    # Find consequences matching this outcome tier
    tier_consequences = [c for c in all_consequences if c.outcome_tier == outcome]

    if tier_consequences:
        selected = _select_weighted_consequence(tier_consequences)
        selected = _apply_character_loss_filtering(character, selected, tier_consequences)
    else:
        # No consequences defined for this tier -- create a synthetic one
        selected = _create_fallback_consequence(attempt_template, outcome)

    # Build roulette display payload
    display_list = _build_roulette_display(all_consequences, selected, outcome)

    return AttemptResult(
        attempt_template=attempt_template,
        check_result=check_result,
        consequence=selected,
        all_consequences=display_list,
    )


def _select_weighted_consequence(
    consequences: list[AttemptConsequence],
) -> AttemptConsequence:
    """Select a consequence using weighted random from the list."""
    weights = [c.weight for c in consequences]
    return random.choices(consequences, weights=weights, k=1)[0]  # noqa: S311


def _apply_character_loss_filtering(
    character: "ObjectDB",
    selected: AttemptConsequence,
    tier_consequences: list[AttemptConsequence],
) -> AttemptConsequence:
    """
    If selected consequence has character_loss=True and character has positive rollmod,
    replace with the worst non-loss alternative in this tier.

    If no non-loss alternatives exist, character_loss stands.
    """
    if not selected.character_loss:
        return selected

    rollmod = get_rollmod(character)
    if rollmod <= 0:
        return selected

    # Find non-loss alternatives in this tier
    alternatives = [c for c in tier_consequences if not c.character_loss]
    if not alternatives:
        return selected

    # Select the worst non-loss consequence (highest display_order, then lowest weight)
    alternatives.sort(key=lambda c: (-c.display_order, c.weight))
    return alternatives[0]


def _create_fallback_consequence(
    attempt_template: "AttemptTemplate",
    outcome: Optional["CheckOutcome"],
) -> AttemptConsequence:
    """
    Create an unsaved AttemptConsequence using the outcome name as the label.

    Used when no consequences are defined for a tier -- the generic outcome name
    is shown instead.
    """
    return AttemptConsequence(
        attempt_template=attempt_template,
        outcome_tier=outcome,
        label=str(outcome.name) if outcome else "Unknown",
        weight=1,
        character_loss=False,
    )


def _build_roulette_display(
    all_consequences: list[AttemptConsequence],
    selected: AttemptConsequence,
    outcome: Optional["CheckOutcome"],
) -> list[ConsequenceDisplay]:
    """
    Build the roulette display payload.

    All consequences across all tiers are included. Currently uses real weights
    for segment sizing; cosmetic weight transformation is future work.
    No rollmod or character_loss flags exposed.
    """
    if not all_consequences:
        # Fallback: just show the selected consequence
        return [
            ConsequenceDisplay(
                label=selected.label,
                tier_name=str(outcome.name) if outcome else "Unknown",
                weight=1,
                is_selected=True,
            )
        ]

    display_list = []
    for consequence in all_consequences:
        is_selected = (
            consequence.pk == selected.pk if consequence.pk else consequence.label == selected.label
        )
        display_list.append(
            ConsequenceDisplay(
                label=consequence.label,
                tier_name=str(consequence.outcome_tier.name),
                weight=consequence.weight,
                is_selected=is_selected,
            )
        )

    return display_list
