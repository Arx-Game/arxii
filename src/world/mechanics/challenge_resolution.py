"""Challenge resolution service functions."""

from typing import TYPE_CHECKING

from world.checks.outcome_utils import (
    build_outcome_display,
    filter_character_loss,
    select_weighted,
)
from world.checks.services import perform_check
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
    # TEMPORARY: For MVP, treated same as PERSONAL (challenge stays active).
    # Future: track bypass duration and re-activate after N rounds.

    # 6. Create record
    CharacterChallengeRecord.objects.create(
        character=character,
        challenge_instance=challenge_instance,
        approach=approach,
        outcome=check_result.outcome,
        consequence=consequence if consequence.pk else None,
    )

    # 7. Build display consequences and return
    all_consequences = list(
        ChallengeConsequence.objects.filter(
            challenge_template=template,
        )
    )
    display_consequences = build_outcome_display(all_consequences, consequence)

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
        selected = select_weighted(approach_consequences)
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
        selected = select_weighted(tier_consequences)
        return filter_character_loss(character, selected, tier_consequences)

    # No consequences for this tier — synthetic fallback
    return ChallengeConsequence(
        challenge_template=template,
        outcome_tier=outcome,
        label=str(outcome.name),
        weight=1,
        character_loss=False,
    )
