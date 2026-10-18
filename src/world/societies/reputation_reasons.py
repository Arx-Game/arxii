"""Reason lines for an organization's reputation changes (#4448, #4339).

A player reads *why* an organization thinks as it does as one line per recorded change,
built from the cause and the staff-authored copy for it (``OrganizationReputationReasonLine``).
The line shows the tier after the change and, where the cause cites a deed or a story, its
title. It never carries a number, and for an exposed or disproved secret it never names the
secret or whoever spread it: learning that takes a check, like any hidden information.
"""

from __future__ import annotations

from collections.abc import Sequence
import re

from world.societies.constants import (
    REASON_LINE_CAUSES,
    REASON_LINE_PLACEHOLDER,
    REASON_LINES_SHOWN,
    OrganizationReputationCause,
)
from world.societies.models import (
    OrganizationReputationEvent,
    OrganizationReputationReasonLine,
)
from world.societies.types import ReputationTier

_TOKEN = re.compile(r"\{(tier|title|organization)\}")


def _tier_name(tier_value: str) -> str:
    return ReputationTier(tier_value).display_name


def _cited_title(event: OrganizationReputationEvent) -> str:
    """The deed or story title a change cites; blank when the cause cites none."""
    if event.legend_entry_id:
        return event.legend_entry.title
    if event.mission_deed_id:
        return event.mission_deed.instance.template.name
    if event.stake_resolution_id:
        return event.stake_resolution.stake.beat.episode.chapter.story.title
    return ""


def copy_by_cause() -> dict[str, str]:
    """The authored reason-line text per cause, blank rows left out."""
    return {
        line.cause: line.text
        for line in OrganizationReputationReasonLine.objects.all()
        if line.text.strip()
    }


def reason_line(event: OrganizationReputationEvent, copy: dict[str, str]) -> str:
    """One reason line for one recorded change."""
    tier = _tier_name(event.tier_after)
    if event.cause == OrganizationReputationCause.LEADER_DECLARATION:
        return f"{tier}: {event.standing_declaration.citation}"
    if event.cause not in REASON_LINE_CAUSES:
        return tier
    template = copy.get(event.cause)
    if template is None:
        return f"{tier} {REASON_LINE_PLACEHOLDER}"
    values = {
        "tier": tier,
        "title": _cited_title(event),
        "organization": (
            event.source_event.reputation.organization.name if event.source_event_id else ""
        ),
    }
    return _TOKEN.sub(lambda match: values[match.group(1)], template)


def reason_lines_by_reputation(reputation_ids: Sequence[int]) -> dict[int, list[str]]:
    """The newest reason lines (as many as are shown) for each of the given reputations.

    One query for all of them, newest first, so a sheet with many organizations does not
    pay a query each.
    """
    lines: dict[int, list[str]] = {pk: [] for pk in reputation_ids}
    if lines:
        _fill_reason_lines(lines)
    return lines


def _fill_reason_lines(lines: dict[int, list[str]]) -> None:
    """Write each reputation's newest reason lines into ``lines`` (keys are the pks)."""
    copy = copy_by_cause()
    events = OrganizationReputationEvent.objects.filter(
        reputation_id__in=list(lines)
    ).select_related(
        "legend_entry",
        "mission_deed__instance__template",
        "stake_resolution__stake__beat__episode__chapter__story",
        "standing_declaration",
        "source_event__reputation__organization",
    )
    for event in events:
        shown = lines[event.reputation_id]
        if len(shown) < REASON_LINES_SHOWN:
            shown.append(reason_line(event, copy))
