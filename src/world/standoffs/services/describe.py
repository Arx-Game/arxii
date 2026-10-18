"""What a reader may be told about the things a read has uncovered."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import CauseKind
from world.standoffs.constants import RevealKind
from world.standoffs.models import StandoffAngleShare
from world.standoffs.services.faction_rules import faction_rule_matches
from world.standoffs.services.profile import group_cause, group_drives

if TYPE_CHECKING:
    from collections.abc import Iterable

    from world.character_sheets.models import CharacterSheet
    from world.standoffs.models import StandoffConfig, StandoffGroup, StandoffReveal

HIDDEN_FACTION_RULE_LINE = "Something about one of you matters to them."


def describe_reveals(
    group: StandoffGroup,
    reveals: Iterable[StandoffReveal],
    reader: CharacterSheet,
    *,
    matching_rule_ids: set[int] | None = None,
    shared_rule_ids: set[int] | None = None,
) -> list[str]:
    """One line per revealed thing, as ``reader`` may know it.

    A faction rule's revealed text goes only to a reader it applies to, or once someone
    has shared that angle; otherwise the reader learns only that someone's history matters.
    A caller that already holds the reader's matched rule ids and the group's shared rule
    ids passes them in to skip the lookups.
    """
    matching = (
        matching_rule_ids
        if matching_rule_ids is not None
        else {match.rule.pk for match in faction_rule_matches(group, reader)}
    )
    shared = (
        shared_rule_ids
        if shared_rule_ids is not None
        else set(
            StandoffAngleShare.objects.filter(group=group).values_list("faction_rule_id", flat=True)
        )
    )
    lines: list[str] = []
    for reveal in reveals:
        line = _describe_reveal(group, reveal, matching, shared)
        if line is not None:
            lines.append(line)
    return lines


def _describe_reveal(
    group: StandoffGroup,
    reveal: StandoffReveal,
    matching: set[int],
    shared: set[int],
) -> str | None:
    """Return the reader-safe line for one reveal, if it has one."""
    if reveal.kind == RevealKind.CAUSE:
        cause, _margin = group_cause(group)
        return None if cause == CauseKind.NONE else f"Cause: {CauseKind(cause).label}."
    if reveal.kind == RevealKind.DRIVE and reveal.drive is not None:
        strengths = {drive.property_id: drive.strength_label for drive in group_drives(group)}
        label = strengths.get(reveal.drive_id)
        if label is None:
            return None
        return f"Drive: {reveal.drive.name} ({label})."
    if reveal.kind == RevealKind.FACTION_RULE and reveal.faction_rule is not None:
        rule = reveal.faction_rule
        if rule.pk in matching or rule.pk in shared:
            return rule.revealed_text or HIDDEN_FACTION_RULE_LINE
        return HIDDEN_FACTION_RULE_LINE
    return None


#: How many actions the config preview walks a Hunger group through.
PREVIEW_HUNGER_ACTIONS = 3


def config_preview(config: StandoffConfig) -> list[str]:
    """What the cause numbers do over a few actions, in plain words (the config admin rail)."""
    step = config.hunger_margin_step
    widened = step * PREVIEW_HUNGER_ACTIONS
    patience = config.territory_patience
    territory = f"A Territory group fires after action {patience}."
    if patience > 1:
        territory = (
            f"A Territory group warns after action {patience - 1}, fires after action {patience}."
        )
    return [
        (
            "A Hunger group with margin 0 needs the party to outweigh it now; after "
            f"{PREVIEW_HUNGER_ACTIONS} unfed actions, by {widened} percent."
        ),
        territory,
        "Listed on Game Tuning as Required content.",
    ]
