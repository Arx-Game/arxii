"""A pose's reach for a resonance (#5308).

A poser may name the resonance their pose reaches for, held or not. An endorsement of that pose
pays the named resonance, so the endorser only confirms it (see ``create_pose_endorsement``). A
pose that also points at an act is a mark instead (``world.magic.services.marking``): it pays at
once and writes no reach.

``pending_reach_from`` checks what a pose asked to reach for before anything posts,
``record_pending_reach`` writes the ``PoseResonanceReach`` once the pose is down. Only the
pose's author reaches, and only when posing: nothing here takes an existing pose from outside.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from world.magic.exceptions import ReachError
from world.magic.models import PoseResonanceReach, Resonance
from world.magic.types.kindling import PendingReach
from world.scenes.interaction_services import notify_interaction_changed

if TYPE_CHECKING:
    from world.scenes.models import Interaction

_UNKNOWN_RESONANCE = "That resonance does not exist."


def resolve_reach_name(name: str) -> int:
    """The id of the resonance ``name`` names, matched without regard to case.

    Raises:
        ReachError: the name is blank or matches no resonance. Nothing is written.
    """
    wanted = name.strip()
    if not wanted:
        raise ReachError(_UNKNOWN_RESONANCE)
    resonance = Resonance.objects.filter(name__iexact=wanted).first()
    if resonance is None:
        msg = f"There is no resonance called '{wanted}'."
        raise ReachError(msg)
    return resonance.pk


def pending_reach_from(params: Any) -> PendingReach | None:
    """The reach a pose asked for, checked, or None when it asked for none.

    ``params`` is the action's kwargs or a serializer's validated data: ``reach_resonance_id``
    (optional). Any existing resonance is valid, held or not; nothing is written. A pose that
    also names an act (``reach_act_id``) is a mark (#5327, ``pending_mark_from``), not a reach,
    so it asks for none here.

    Raises:
        ReachError: the id is not a resonance.
    """
    raw = params.get("reach_resonance_id")
    if raw is None or raw == "":
        return None
    act = params.get("reach_act_id")
    if act is not None and act != "":
        return None
    if isinstance(raw, bool):
        raise ReachError(_UNKNOWN_RESONANCE)
    try:
        pk = int(raw)
    except (TypeError, ValueError) as exc:
        raise ReachError(_UNKNOWN_RESONANCE) from exc
    if not Resonance.objects.filter(pk=pk).exists():
        raise ReachError(_UNKNOWN_RESONANCE)
    return PendingReach(resonance_id=pk)


def record_pending_reach(interaction: Interaction, pending: PendingReach) -> PoseResonanceReach:
    """Write a ``pending_reach_from`` result against the pose it rode in on.

    Called once, with the pose the author has just posted, on first acceptance only. Saving the
    row clears the pose's cached lists (``related_cache_fields``); the new row is then set as the
    pose's cached reach so the response reads it without a query. The pose was pushed to the
    room before the reach existed, so the room is told it changed and each page refetches it.
    """
    reach = PoseResonanceReach.objects.create(
        interaction=interaction,
        resonance=Resonance.objects.get(pk=pending.resonance_id),
    )
    interaction.cached_resonance_reaches = [reach]
    notify_interaction_changed(interaction)
    return reach


__all__ = ["pending_reach_from", "record_pending_reach", "resolve_reach_name"]
