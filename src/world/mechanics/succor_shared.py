"""Domain-agnostic Succor pieces shared by combat and scene rounds (#1744).

Succor is a RoundContext-seam capability, not a combat-only concept (unlike
Interpose, which only fires on the combat DAMAGE_PRE_APPLY path) — its grading
and challenge-name identity belong here, not in world.combat, so world.scenes
doesn't need a one-directional import into world.combat for a domain-agnostic
concept.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.mechanics.types import ChallengeResolutionResult

SUCCOR_CHALLENGE_NAME: str = "Succor"


def apply_succor_outcome(result: ChallengeResolutionResult, partial_protection: int) -> float:
    """Map a graded Succor resolution to a tick-amount multiplier.

    Mirrors world.combat.services.apply_interpose_outcome's clean/partial/fail
    shape, returning a float multiplier instead of mutating a payload in place.
    ``partial_protection`` is the percentage a partial shelter stops (the succorer's
    ``effect_value`` for ``SUCCOR_PARTIAL_PROTECTION``, 0 to 100): a clean block lands
    nothing, a partial lands the rest, a failure lands all of it.
    """
    from world.mechanics.constants import ResolutionType  # noqa: PLC0415

    check_result = result.check_result
    success_level = check_result.success_level if check_result is not None else 0
    is_clean_block = result.resolution_type == ResolutionType.DESTROY or success_level > 0
    if is_clean_block:
        return 0.0
    if success_level == 0:
        return (100 - partial_protection) / 100
    return 1.0
