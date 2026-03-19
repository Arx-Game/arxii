"""Challenge resolution service functions."""

from typing import TYPE_CHECKING

from world.checks.models import Consequence
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
    ChallengeTemplateConsequence,
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

    # 3. Select consequence and resolution metadata
    consequence, resolution_type = _select_consequence(
        approach, template, check_result.outcome, character
    )

    # 4. Apply effects
    applied_effects = apply_all_effects(consequence, character, challenge_instance)

    # 5. Determine resolution type and update challenge state
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
        Consequence.objects.filter(
            challenge_template_consequences__challenge_template=template,
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
) -> tuple[Consequence, str]:
    """
    Select a consequence for the given outcome tier.

    Priority: approach-level consequences override template-level for the same tier.
    Falls back to a synthetic unsaved consequence if no tier matches.

    Returns (consequence, resolution_type) tuple.
    """
    # Check approach-level consequences first
    approach_consequences = list(
        ApproachConsequence.objects.filter(
            approach=approach,
            consequence__outcome_tier=outcome,
        ).select_related("consequence")
    )
    if approach_consequences:
        selected = select_weighted([ac.consequence for ac in approach_consequences])
        # Get resolution_type from ApproachConsequence through model
        ac = next(ac for ac in approach_consequences if ac.consequence_id == selected.pk)
        resolution_type = ac.resolution_type or ResolutionType.PERSONAL
        return selected, resolution_type

    # Fall back to template-level consequences
    template_links = list(
        ChallengeTemplateConsequence.objects.filter(
            challenge_template=template,
            consequence__outcome_tier=outcome,
        ).select_related("consequence")
    )
    if template_links:
        consequences = [link.consequence for link in template_links]
        selected = select_weighted(consequences)
        selected = filter_character_loss(character, selected, consequences)
        # Get resolution_type from through model
        link = next(link for link in template_links if link.consequence_id == selected.pk)
        return selected, link.resolution_type

    # No consequences for this tier — synthetic fallback
    fallback = Consequence(
        outcome_tier=outcome,
        label=str(outcome.name),
        weight=1,
        character_loss=False,
    )
    return fallback, ResolutionType.PERSONAL
