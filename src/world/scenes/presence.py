"""Online-presence listing for the ``who`` surface (#1463).

``who`` lists currently-online characters by their **active** persona's display name and a
**coarse** idle indicator. The idle is deliberately bucketed — never exact minutes — so two
characters on one account never show an identical exact idle time that would correlate them
as alts. Mirrors the ``where`` listing's session-enumeration shape (`world.areas.services`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

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


# ---------------------------------------------------------------------------
# Quiet/hidden mode + transient AFK (#1463)
# ---------------------------------------------------------------------------
#
# A character's player can enable *quiet mode* (per-character, persistent
# ``TenureDisplaySettings.appear_offline``): they drop off where/who and become unpageable —
# EXCEPT to people on their allowlist (`PlayerAllowList`), who still see and reach them.
# Async (mail/mission/channels) and same-room presence are never affected. The helpers below
# are the single source of truth for that visibility/reachability rule, shared by who
# (`who_listing`), where (`world.areas.services.where_listing`), and page (`CmdPage`).

# Transient "away from keyboard" marker lives on the puppet's ndb (``puppet.ndb.appear_afk``),
# set by the `afk` command. Cleared on toggle or server reload — never persisted (it's a
# right-now state, not a setting), so it stays out of TenureDisplaySettings.


def character_appears_offline(character: object) -> bool:
    """Whether this character's player has quiet/hidden mode on (#1463, ``appear_offline``).

    Reads the per-tenure ``TenureDisplaySettings.appear_offline``; defaults to ``False``
    (visible/reachable) when there's no current tenure or settings row yet.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        tenure = character.sheet_data.roster_entry.current_tenure
    except (AttributeError, ObjectDoesNotExist):
        return False
    if tenure is None:
        return False
    try:
        return tenure.display_settings.appear_offline
    except (AttributeError, ObjectDoesNotExist):
        return False


def account_on_allowlist(*, owner_account: object, viewer_account: object) -> bool:
    """Whether ``viewer_account`` is on ``owner_account``'s ``PlayerAllowList`` (the whitelist).

    Account↔account: the allowlist follows the player across characters, so quiet-mode
    exemptions are by person, not by mask.
    """
    if owner_account is None or viewer_account is None:
        return False
    from evennia_extensions.models import PlayerAllowList  # noqa: PLC0415

    return PlayerAllowList.objects.filter(
        owner__account_id=owner_account.pk,
        allowed_player__account_id=viewer_account.pk,
    ).exists()


def hidden_from_viewer(character: object, viewer_account: object) -> bool:
    """Whether ``character`` should be omitted from a presence surface for this viewer (#1463).

    A quiet-mode character is hidden from everyone EXCEPT the player themselves (same account)
    and viewers on the character's allowlist. A non-hidden character is never omitted; an
    anonymous viewer (no account) never sees a hidden character.
    """
    if not character_appears_offline(character):
        return False
    owner = character.active_account
    if owner is not None and viewer_account is not None and owner.pk == viewer_account.pk:
        return False
    return not account_on_allowlist(owner_account=owner, viewer_account=viewer_account)


def who_listing(viewer_account: object | None = None) -> list[WhoEntry]:
    """Currently-online characters, by active persona, with a coarse idle state (#1463).

    One entry per character (minimum idle across its sessions = most-recent activity), keyed
    on the **active** persona so a disguised character shows the face it's wearing. Sorted by
    name. Idle is bucketed, never exact, to avoid outing alts by identical idle times; an `afk`
    marker forces the ``away`` bucket. Quiet-mode characters are omitted unless ``viewer_account``
    is the player themselves or on their allowlist. A concealed character (#1225 — any active
    ``conceals_from_perception`` condition) is omitted unconditionally, mirroring the quiet-mode
    omission above — there is no per-observer "detection" concept for an anonymous global
    directory like ``who``, unlike the room-occupant list's per-observer ``can_perceive`` gate.
    """
    from time import time  # noqa: PLC0415

    from evennia import SESSION_HANDLER  # noqa: PLC0415

    now = time()
    idle_by_puppet: dict[int, float] = {}
    puppets_by_id: dict[int, object] = {}
    for session in SESSION_HANDLER.get_sessions():
        puppet = session.puppet
        if puppet is None:
            continue
        last = getattr(session, "cmd_last_visible", None)  # noqa: GETATTR_LITERAL
        idle = now - last if last else 0.0
        if puppet.id not in idle_by_puppet or idle < idle_by_puppet[puppet.id]:
            idle_by_puppet[puppet.id] = idle
            puppets_by_id[puppet.id] = puppet

    entries: list[WhoEntry] = []
    for puppet_id, puppet in puppets_by_id.items():
        entry = _who_entry_for_puppet(puppet, puppet_id, idle_by_puppet[puppet_id], viewer_account)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda entry: entry.name.lower())
    return entries


def _who_entry_for_puppet(
    puppet: object,
    _puppet_id: int,
    idle: float,
    viewer_account: object | None,
) -> WhoEntry | None:
    """Build a single ``WhoEntry`` for ``puppet``, or None to omit it.

    Omits a hidden or concealed character, or one whose sheet can't be resolved.
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.conditions.services import is_concealed  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if hidden_from_viewer(puppet, viewer_account):
        return None
    # puppets_by_id is typed loosely (`object`) to match this module's other
    # puppet-handling helpers; is_concealed's real ObjectDB param is a runtime
    # guarantee (puppet is always a session's live Character), not a static one.
    if is_concealed(cast("ObjectDB", puppet)):
        return None
    try:
        sheet = puppet.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None
    persona = active_persona_for_sheet(sheet)
    idle_value = IDLE_AWAY if puppet.ndb.appear_afk else idle_bucket(idle)
    return WhoEntry(name=persona.display_ic(), idle=idle_value)
