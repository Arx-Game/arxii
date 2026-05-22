"""Expand a node's attached challenges into challenge-contributed options.

A ``MissionNode`` may attach one or more ``mechanics.ChallengeTemplate``s
(authored in the challenge tool, referenced here). Each attached challenge's
``ChallengeApproach``es become options on the node — one per approach the
acting character qualifies for, plus every ``is_default`` approach (offered
to everyone). The challenge is consumed as authored *data*: missions never
call ``resolve_challenge`` (findings doc Q2 — data-source integration). Of
the ``ChallengeTemplate`` fields only ``severity`` rides along, as the
approach rolls' difficulty (design §8.4 Q4).

Capability ownership is **not** re-implemented here. It is decided by the
Phase-0 ``_resolve_has_capability`` resolver in ``world.missions.predicates``
— the single definition of "does this acting character own capability X".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.mechanics.models import ChallengeApproach
from world.missions.predicates import _resolve_has_capability
from world.missions.types import ChallengeOption

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionNode


def challenge_options_for_character(
    node: MissionNode,
    character: ObjectDB,
) -> list[ChallengeOption]:
    """Surface the challenge-contributed options ``character`` gets at ``node``.

    For each ``ChallengeApproach`` of every challenge attached to ``node``,
    build one :class:`~world.missions.types.ChallengeOption` when the acting
    ``character`` qualifies — they hold the approach's
    ``Application.capability``, or the approach is ``is_default`` (offered to
    everyone). Approaches the character neither qualifies for nor that are
    ``is_default`` are excluded; the result is legitimately empty when an
    attached challenge defines no default and the character qualifies for
    none of its approaches.

    Args:
        node: The mission node whose attached challenges are expanded.
        character: The acting character (an ``ObjectDB``).

    Returns:
        Challenge options in a deterministic order (challenge pk, then
        approach pk). Empty when nothing qualifies.
    """
    options: list[ChallengeOption] = []
    for challenge in sorted(node.attached_challenges_cached, key=lambda c: c.pk):
        approaches = (
            ChallengeApproach.objects.filter(challenge_template=challenge)
            .select_related("application__capability", "check_type")
            .order_by("pk")
        )
        for approach in approaches:
            qualifies = approach.is_default or _resolve_has_capability(
                character, name=approach.application.capability.name
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
