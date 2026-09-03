"""Shared optional beat-routing resolution for GM verbs (#3559).

Several GM actions (staging a battle, starting a combat encounter) accept an
optional ``beat_id`` kwarg that routes the resulting battle/encounter onto a
story beat. Both need the same lookup + permission guard; this module is the
one place that owns it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from commands.utils.gm_resolution import resolve_account_or_none

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.stories.models import Beat

_NO_SUCH_BEAT = "No such beat."


def resolve_routed_beat(
    actor: ObjectDB, beat_id: int, *, permission_denied_message: str
) -> Beat | str:
    """Resolve *beat_id* into a Beat *actor* may route onto, or an error message.

    Callers only invoke this when a ``beat_id`` was actually given - routing is
    always optional, so the "no beat_id" case is the caller's own concern.
    Returns the resolved ``Beat`` on success. On refusal returns the exact
    user-facing message the caller should surface: a shared "no such beat"
    text when the id doesn't resolve, or *permission_denied_message* (each
    caller's own wording) when the actor may not route onto that beat.
    """
    from world.stories.models import Beat  # noqa: PLC0415
    from world.stories.permissions import account_may_route_beat  # noqa: PLC0415

    try:
        beat = Beat.objects.filter(pk=beat_id).first()
    except (TypeError, ValueError):
        beat = None
    if beat is None:
        return _NO_SUCH_BEAT
    if not account_may_route_beat(resolve_account_or_none(actor), beat):
        return permission_denied_message
    return beat
