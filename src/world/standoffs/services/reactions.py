"""Authored reaction lines for standoff presses and terms, banded by success level.

Staff write ``StandoffReactionLine`` rows; no code names a creature or a line. The best line
is the highest ``min_success_level`` at or below the roll, and at an equal floor a line tied
to the group's creature kind beats a generic one (the same banding as ``NPCReactionLine``).
"""

from __future__ import annotations

from world.standoffs.models import StandoffApproach, StandoffReactionLine, StandoffTerms

ACTOR_TOKEN = "<actor>"  # noqa: S105 - template interpolation token, not a secret
GROUP_TOKEN = "<group>"  # noqa: S105 - template interpolation token, not a secret


def best_reaction_line(
    parent: StandoffApproach | StandoffTerms,
    creature_template_id: int,
    success_level: int,
) -> StandoffReactionLine | None:
    """The line that fits this roll, or None when staff authored none that applies."""
    candidates = [
        line
        for line in parent.reaction_lines.filter(min_success_level__lte=success_level)
        if line.creature_template_id in (None, creature_template_id)
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda line: (line.min_success_level, line.creature_template_id is not None),
    )


def reaction_text(
    parent: StandoffApproach | StandoffTerms,
    *,
    creature_template_id: int,
    group_name: str,
    actor_name: str,
    success_level: int,
) -> str | None:
    """The room line for this roll with its placeholders filled, or None to use the plain line.

    ``actor_name`` must be the name the actor presents under, never the character's key.
    """
    line = best_reaction_line(parent, creature_template_id, success_level)
    if line is None:
        return None
    return line.text.replace(ACTOR_TOKEN, actor_name).replace(GROUP_TOKEN, group_name)
