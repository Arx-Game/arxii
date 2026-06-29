"""Shared discovery-announcement helpers for the achievements system.

Two entry points:

``announce_achievement`` — sends one NarrativeMessage for an achievement ceremony:
gamewide (all active player sheets) when ``is_first`` else personal (earners only).
The caller supplies both message bodies; the discoverer is never named in the
first-ever body.

``announce_access_change`` — notifies a character about techniques/capabilities
gained or lost from any source, then fires first-ever discovery for each gained item
that carries a non-null ``discovery_achievement`` FK.  Capability handling is
identical regardless of source — never branch on covenant (spec Decision 11).
"""

from world.achievements.constants import AccessChangeSource
from world.achievements.services import grant_achievement


def announce_achievement(
    earners,
    *,
    is_first,
    first_body,
    personal_body,
    category,
):
    """Send the gamewide-vs-personal achievement ceremony message.

    First-ever (``is_first``): gamewide to every active player character sheet,
    using ``first_body`` (which must NOT name the discoverer). Otherwise:
    personal, to ``earners``, using ``personal_body``.
    """
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    if is_first:
        from world.roster.selectors import active_player_character_sheets  # noqa: PLC0415

        recipients = active_player_character_sheets()
        body = first_body
    else:
        recipients = list(earners)
        body = personal_body
    send_narrative_message(recipients=recipients, body=body, category=category, sender_account=None)


def _names(items):
    """Return a comma-separated display string of item names."""
    return ", ".join(getattr(i, "name", str(i)) for i in items)  # noqa: GETATTR_LITERAL


def announce_access_change(character_sheet, *, gained, lost, source):
    """Tell the player about techniques/capabilities gained/lost from any source,
    and fire first-ever Discovery for each gained item that is discoverable.

    ``gained``/``lost``: content instances (Techniques and/or CapabilityTypes),
    mixed, from any mechanism. Capability handling is identical regardless of
    source — never branch on covenant (spec Decision 11).
    """
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    lead = AccessChangeSource(source).label
    parts = []
    if gained:
        parts.append(f"Through {lead}, you can now use: {_names(gained)}.")
    if lost:
        parts.append(f"You can no longer use: {_names(lost)}.")
    if parts:
        send_narrative_message(
            recipients=[character_sheet],
            body=" ".join(parts),
            category=NarrativeCategory.ABILITY,
            sender_account=None,
        )
    for item in gained:
        ach = getattr(item, "discovery_achievement", None)  # noqa: GETATTR_LITERAL
        if ach is None:
            continue
        results = grant_achievement(ach, [character_sheet])
        is_first = bool(results and results[0].discovery_id is not None)
        name = getattr(item, "name", str(item))  # noqa: GETATTR_LITERAL
        announce_achievement(
            [character_sheet],
            is_first=is_first,
            first_body=(
                f"For the first time in recorded history, a character has manifested {name}."
            ),
            personal_body=f"You are among the first to manifest {name}.",
            category=NarrativeCategory.ABILITY,
        )
