"""Expand a challenge into challenge-contributed options for a character.

A ``MissionOption`` with ``source_kind=CHALLENGE`` references one
``mechanics.ChallengeTemplate`` (authored in the challenge tool, referenced
here). The challenge's ``ChallengeApproach``es become options — one per
approach the acting character qualifies for, plus every ``is_default``
approach (offered to everyone). The challenge is consumed as authored
*data*: missions never call ``resolve_challenge`` (findings doc Q2 —
data-source integration). Of the ``ChallengeTemplate`` fields only
``severity`` rides along, as the approach rolls' difficulty (design §8.4 Q4).

Capability ownership is **not** re-implemented here. It is decided by
``world.conditions.services.get_capability_value`` — the single definition
of "does this acting character own capability X" (the Phase-0
``has_capability`` predicate resolver wraps the same call).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.conditions.services import get_capability_value
from world.mechanics.models import ChallengeApproach, ChallengeTemplate
from world.missions.types import ChallengeOption

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def challenge_options_for_character(
    challenge: ChallengeTemplate,
    character: ObjectDB,
) -> list[ChallengeOption]:
    """Surface the options ``challenge`` contributes for ``character``.

    For each ``ChallengeApproach`` of ``challenge``, build one
    :class:`~world.missions.types.ChallengeOption` when the acting
    ``character`` qualifies — they hold the approach's
    ``Application.capability`` (per
    ``conditions.services.get_capability_value``) — or the approach is
    ``is_default`` (offered to everyone). Approaches the character neither
    qualifies for nor that are ``is_default`` are excluded; the result is
    legitimately empty when the challenge defines no default and the
    character qualifies for none of its approaches.

    Args:
        challenge: The challenge attached to a CHALLENGE-sourced option.
        character: The acting character (an ``ObjectDB``).

    Returns:
        Challenge options in a deterministic order (approach pk). Empty when
        nothing qualifies.
    """
    options: list[ChallengeOption] = []
    approaches = (
        ChallengeApproach.objects.filter(challenge_template=challenge)
        .select_related("application__capability", "check_type")
        .order_by("pk")
    )
    for approach in approaches:
        # approach.application.capability is the live CapabilityType
        # instance (select_related'd above) — call the underlying service
        # directly rather than re-looking-up by name.
        qualifies = (
            approach.is_default
            or get_capability_value(character, approach.application.capability) > 0
        )
        if not qualifies:
            continue
        options.append(
            ChallengeOption(
                approach=approach,
                check_type=approach.check_type,
                auto_succeeds=approach.auto_succeeds,
                difficulty=challenge.severity,
                owner=character,
            )
        )
    return options
