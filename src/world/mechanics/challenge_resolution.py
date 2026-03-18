"""Challenge resolution service functions."""

from typing import TYPE_CHECKING

from world.mechanics.models import CharacterChallengeRecord
from world.mechanics.types import (
    ChallengeResolutionError,
    ChallengeResolutionResult,
)

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.mechanics.models import ChallengeApproach, ChallengeInstance
    from world.mechanics.types import CapabilitySource

_ERR_NOT_ACTIVE = "Challenge is not active."
_ERR_NOT_REVEALED = "Challenge has not been revealed."
_ERR_ALREADY_RESOLVED = "Character has already resolved this challenge."
_ERR_WRONG_APPROACH = "Approach does not belong to this challenge's template."
_ERR_NOT_IMPLEMENTED = "Resolution not yet implemented"


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
    raise NotImplementedError(_ERR_NOT_IMPLEMENTED)


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
