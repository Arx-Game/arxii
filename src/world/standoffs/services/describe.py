"""What a reader may be told about the things a read has uncovered."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import CauseKind
from world.standoffs.constants import DriveStrength, RevealKind
from world.standoffs.models import StandoffSparkShare
from world.standoffs.services.regard import regard_matches

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.character_sheets.models import CharacterSheet
    from world.standoffs.models import StandoffGroup, StandoffReveal

HIDDEN_REGARD_LINE = "Something about one of you matters to them."


def describe_reveals(
    group: StandoffGroup,
    reveals: Iterable[StandoffReveal],
    reader: CharacterSheet,
    *,
    matching_rule_ids: set[int] | None = None,
    shared_rule_ids: set[int] | None = None,
) -> list[str]:
    """One line per revealed thing, as ``reader`` may know it.

    A regard rule's revealed text goes only to a reader it applies to, or once someone
    has shared that spark; otherwise the reader learns only that someone's history matters.
    A caller that already holds the reader's matched rule ids and the group's shared rule
    ids passes them in to skip the lookups.
    """
    matching = (
        matching_rule_ids
        if matching_rule_ids is not None
        else {match.rule.pk for match in regard_matches(group, reader)}
    )
    shared = (
        shared_rule_ids
        if shared_rule_ids is not None
        else set(
            StandoffSparkShare.objects.filter(group=group).values_list("regard_rule_id", flat=True)
        )
    )
    lines: list[str] = []
    for reveal in reveals:
        if reveal.kind == RevealKind.CAUSE:
            lines.append(f"Cause: {CauseKind(group.creature_template.cause).label}.")
        elif reveal.kind == RevealKind.DRIVE and reveal.drive is not None:
            label = DriveStrength(reveal.drive.strength).label
            lines.append(f"Drive: {reveal.drive.property.name} ({label}).")
        elif reveal.kind == RevealKind.REGARD and reveal.regard_rule is not None:
            rule = reveal.regard_rule
            if rule.pk in matching or rule.pk in shared:
                lines.append(rule.revealed_text or HIDDEN_REGARD_LINE)
            else:
                lines.append(HIDDEN_REGARD_LINE)
    return lines
