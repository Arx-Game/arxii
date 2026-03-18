"""Challenge resolution service functions."""

import random
from typing import TYPE_CHECKING

from world.checks.services import get_rollmod, perform_check
from world.mechanics.constants import ResolutionType
from world.mechanics.effect_handlers import apply_all_effects
from world.mechanics.models import (
    ApproachConsequence,
    ChallengeConsequence,
    CharacterChallengeRecord,
)
from world.mechanics.types import (
    ChallengeResolutionError,
    ChallengeResolutionResult,
    ConsequenceDisplay,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.mechanics.models import (
        ChallengeApproach,
        ChallengeInstance,
        ChallengeTemplate,
    )
    from world.mechanics.types import CapabilitySource
    from world.traits.models import CheckOutcome

_ERR_NOT_ACTIVE = "Challenge is not active."
_ERR_NOT_REVEALED = "Challenge has not been revealed."
_ERR_ALREADY_RESOLVED = "Character has already resolved this challenge."
_ERR_WRONG_APPROACH = "Approach does not belong to this challenge's template."


def resolve_challenge(
    character: "ObjectDB",
    challenge_instance: "ChallengeInstance",
    approach: "ChallengeApproach",
    capability_source: "CapabilitySource",  # noqa: ARG001 — used in later tasks
) -> ChallengeResolutionResult:
    """
    Resolve a character's action against a challenge.

    1. Validate state
    2. Perform check
    3. Select consequence
    4. Apply effects
    5. Update challenge state
    6. Create record
    7. Return result
    """
    _validate(character, challenge_instance, approach)

    template = challenge_instance.template

    # 2. Perform check
    check_result = perform_check(
        character, approach.check_type, target_difficulty=template.severity
    )

    # 3. Select consequence
    consequence = _select_consequence(approach, template, check_result.outcome, character)

    # 4. Apply effects
    applied_effects = apply_all_effects(consequence, character, challenge_instance)

    # 5. Determine resolution type and update challenge state
    resolution_type = consequence.resolution_type or ResolutionType.PERSONAL
    challenge_deactivated = False
    if resolution_type == ResolutionType.DESTROY:
        challenge_instance.is_active = False
        challenge_instance.save()
        challenge_deactivated = True

    # 6. Create record
    CharacterChallengeRecord.objects.create(
        character=character,
        challenge_instance=challenge_instance,
        approach=approach,
        outcome=check_result.outcome,
        consequence=consequence if consequence.pk else None,
    )

    # 7. Build display consequences and return
    all_consequences = ChallengeConsequence.objects.filter(
        challenge_template=template,
    )
    display_consequences = [
        ConsequenceDisplay(
            label=c.label,
            tier_name=str(c.outcome_tier.name),
            weight=c.weight,
            is_selected=(c.pk == consequence.pk) if consequence.pk else False,
        )
        for c in all_consequences
    ]

    return ChallengeResolutionResult(
        challenge_instance_id=challenge_instance.pk,
        challenge_name=template.name,
        approach_name=approach.display_name,
        check_result=check_result,
        consequence=consequence,
        applied_effects=applied_effects,
        resolution_type=resolution_type,
        challenge_deactivated=challenge_deactivated,
        display_consequences=display_consequences,
    )


def _validate(
    character: "ObjectDB",
    challenge_instance: "ChallengeInstance",
    approach: "ChallengeApproach",
) -> None:
    """Validate that challenge resolution can proceed."""
    if not challenge_instance.is_active:
        raise ChallengeResolutionError(_ERR_NOT_ACTIVE)
    if not challenge_instance.is_revealed:
        raise ChallengeResolutionError(_ERR_NOT_REVEALED)
    if CharacterChallengeRecord.objects.filter(
        character=character,
        challenge_instance=challenge_instance,
    ).exists():
        raise ChallengeResolutionError(_ERR_ALREADY_RESOLVED)
    if approach.challenge_template_id != challenge_instance.template_id:
        raise ChallengeResolutionError(_ERR_WRONG_APPROACH)


def _select_consequence(
    approach: "ChallengeApproach",
    template: "ChallengeTemplate",
    outcome: "CheckOutcome",
    character: "ObjectDB",
) -> ChallengeConsequence:
    """
    Select a consequence for the given outcome tier.

    Priority: approach-level consequences override template-level for the same tier.
    Falls back to a synthetic unsaved consequence if no tier matches.
    """
    # Check approach-level consequences first
    approach_consequences = list(
        ApproachConsequence.objects.filter(
            approach=approach,
            outcome_tier=outcome,
        )
    )
    if approach_consequences:
        selected = _select_weighted_approach(approach_consequences)
        # Convert to ChallengeConsequence for uniform return type
        return ChallengeConsequence(
            challenge_template=template,
            outcome_tier=outcome,
            label=selected.label,
            mechanical_description=selected.mechanical_description,
            weight=selected.weight or 1,
        )

    # Fall back to template-level consequences
    tier_consequences = list(
        ChallengeConsequence.objects.filter(
            challenge_template=template,
            outcome_tier=outcome,
        )
    )
    if tier_consequences:
        selected = _select_weighted(tier_consequences)
        return _apply_character_loss_filtering(character, selected, tier_consequences)

    # No consequences for this tier — synthetic fallback
    return ChallengeConsequence(
        challenge_template=template,
        outcome_tier=outcome,
        label=str(outcome.name),
        weight=1,
        character_loss=False,
    )


def _select_weighted(
    consequences: list[ChallengeConsequence],
) -> ChallengeConsequence:
    """Select a consequence using weighted random from the list."""
    weights = [c.weight for c in consequences]
    return random.choices(consequences, weights=weights, k=1)[0]  # noqa: S311


def _select_weighted_approach(
    consequences: list[ApproachConsequence],
) -> ApproachConsequence:
    """Select an approach consequence using weighted random."""
    weights = [c.weight or 1 for c in consequences]
    return random.choices(consequences, weights=weights, k=1)[0]  # noqa: S311


def _apply_character_loss_filtering(
    character: "ObjectDB",
    selected: ChallengeConsequence,
    tier_consequences: list[ChallengeConsequence],
) -> ChallengeConsequence:
    """
    If selected consequence has character_loss=True and character has positive
    rollmod, replace with the worst non-loss alternative in this tier.

    If no non-loss alternatives exist, character_loss stands.
    """
    if not selected.character_loss:
        return selected

    rollmod = get_rollmod(character)
    if rollmod <= 0:
        return selected

    alternatives = [c for c in tier_consequences if not c.character_loss]
    if not alternatives:
        return selected

    # Select the worst non-loss consequence (lowest weight = least favorable)
    alternatives.sort(key=lambda c: c.weight)
    return alternatives[0]
