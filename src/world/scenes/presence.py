"""Online-presence listing for the ``who`` surface (#1463).

``who`` lists currently-online characters by their **active** persona's display name and a
**coarse** idle indicator. The idle is deliberately bucketed — never exact minutes — so two
characters on one account never show an identical exact idle time that would correlate them
as alts. Mirrors the ``where`` listing's session-enumeration shape (`world.areas.services`).
"""

from __future__ import annotations

from dataclasses import dataclass

# Coarse idle buckets, in seconds. Intentionally coarse (alt-safety); tunable.
_IDLE_ACTIVE_UNDER = 15 * 60  # under 15 min: active (no marker)
_IDLE_AWAY_OVER = 60 * 60  # over 1 hour: away

# Coarse idle states — never an exact duration, so identical idle times can't out alts.
IDLE_ACTIVE = ""
IDLE_IDLE = "idle"
IDLE_AWAY = "away"


@dataclass(frozen=True)
class WhoEntry:
    """One ``who`` row: a present character's active-persona name + coarse idle state."""

    name: str
    idle: str  # "" (active), "idle", or "away"


def idle_bucket(idle_seconds: float) -> str:
    """Map raw idle seconds to a coarse, alt-safe bucket (never an exact duration)."""
    if idle_seconds < _IDLE_ACTIVE_UNDER:
        return IDLE_ACTIVE
    if idle_seconds < _IDLE_AWAY_OVER:
        return IDLE_IDLE
    return IDLE_AWAY


def who_listing() -> list[WhoEntry]:
    """Currently-online characters, by active persona, with a coarse idle state (#1463).

    One entry per character (minimum idle across its sessions = most-recent activity), keyed
    on the **active** persona so a disguised character shows the face it's wearing. Sorted by
    name. Idle is bucketed, never exact, to avoid outing alts by identical idle times.
    """
    from time import time  # noqa: PLC0415

    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415
    from evennia import SESSION_HANDLER  # noqa: PLC0415

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    now = time()
    idle_by_puppet: dict[int, float] = {}
    puppets_by_id: dict[int, object] = {}
    for session in SESSION_HANDLER.get_sessions():
        puppet = getattr(session, "puppet", None)  # noqa: GETATTR_LITERAL
        if puppet is None:
            continue
        last = getattr(session, "cmd_last_visible", None)  # noqa: GETATTR_LITERAL
        idle = now - last if last else 0.0
        if puppet.id not in idle_by_puppet or idle < idle_by_puppet[puppet.id]:
            idle_by_puppet[puppet.id] = idle
            puppets_by_id[puppet.id] = puppet

    entries: list[WhoEntry] = []
    for puppet_id, puppet in puppets_by_id.items():
        try:
            sheet = puppet.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        persona = active_persona_for_sheet(sheet)
        entries.append(
            WhoEntry(name=persona.display_ic(), idle=idle_bucket(idle_by_puppet[puppet_id]))
        )
    entries.sort(key=lambda entry: entry.name.lower())
    return entries
