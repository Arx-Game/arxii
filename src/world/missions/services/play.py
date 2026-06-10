"""Player-facing mission play orchestration (#885).

The thin layer between the player API (and, later, telnet commands) and
the Phase-3 resolution engine: build the current beat for a character,
resolve a chosen option, and deliver the narrative text both ways —
clear STORY prose to the actor, a source-ambiguous ambient stir to the
room (the actor/audience split; see ``narrative.emit_ambient_room_stir``).

This module wires two previously stored-but-unconsumed authored fields
(see the inventory in ``services/resolution.py``):

* ``MissionNode.flavor_text`` — surfaced as the beat card's framing.
* ``MissionOptionRoute.outcome_text`` — the actor's STORY prose when the
  author wrote one; a PLACEHOLDER template line otherwise.

Resolution is RE-VERIFIED here: the chosen option must still be live
(location conjunct ∧ visibility predicate) at resolve time — a stale beat
card can never resolve an option the character is no longer eligible for
or no longer standing in the right room for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.missions.constants import MissionStatus
from world.missions.models import MissionOptionRoute, MissionParticipant
from world.missions.services.resolution import build_option_list, resolve_option
from world.missions.types import BeatOption, BeatView, PresentedOption, ResolvedBeat
from world.narrative.constants import NarrativeCategory
from world.narrative.services import emit_ambient_room_stir, send_narrative_message

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionInstance


class BeatActionError(ValueError):
    """A player beat action that cannot proceed; carries a user-safe message."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class NotParticipantError(BeatActionError):
    """The character isn't on this mission — surfaced as 404, never 403.

    A non-participant probing instance ids must not learn which exist.
    """


_ERR_NOT_PARTICIPANT = "You are not part of that mission."
_ERR_NOT_ACTIVE = "That mission is no longer in progress."
_ERR_OPTION_NOT_LIVE = (
    "That option isn't available to you here — it may have moved on, or "
    "you may need to be somewhere else."
)

# PLACEHOLDER fallback when the author wrote no route outcome_text. Greppable
# for the voice-rewrite pass; never shown when authored prose exists.
_PLACEHOLDER_STORY_TEXT = (
    "PLACEHOLDER — {template}: you commit to '{label}'."
    "{outcome_clause} The thread of the story moves on."
)


def participant_for(instance: MissionInstance, character: ObjectDB) -> MissionParticipant:
    """The character's participant row on ``instance``; raises BeatActionError."""
    participant = MissionParticipant.objects.filter(instance=instance, character=character).first()
    if participant is None:
        raise NotParticipantError(_ERR_NOT_PARTICIPANT)
    return participant


def beat_for(instance: MissionInstance, character: ObjectDB) -> BeatView | None:
    """The current beat as ``character`` sees it; None when the run is done.

    Options are the LIVE set only (location ∧ visibility already applied
    by ``build_option_list``) — an active node with zero options here
    means "go where the compass points," not an error.
    """
    participant = participant_for(instance, character)
    node = instance.current_node
    if node is None:
        return None
    presented = build_option_list(instance, node, participant)
    return BeatView(
        instance_id=instance.pk,
        template_name=instance.template.name,
        node_key=node.key,
        flavor_text=node.flavor_text,
        options=tuple(_beat_option(p) for p in presented),
    )


def _beat_option(presented: PresentedOption) -> BeatOption:
    return BeatOption(
        option_id=presented.option.pk,
        approach_id=presented.approach.pk if presented.approach is not None else None,
        label=presented.ic_framing,
        kind=presented.kind,
        check_type_name=presented.check_type.name if presented.check_type else None,
        base_risk=presented.base_risk,
    )


def resolve_beat_option(
    instance: MissionInstance,
    character: ObjectDB,
    *,
    option_id: int,
    approach_id: int | None = None,
) -> ResolvedBeat:
    """Resolve the chosen option for ``character``; deliver both narratives.

    Re-verifies liveness (the option must be in the CURRENT live set for
    this character, matching ``approach_id`` for CHALLENGE fan-outs), then
    delegates to the Phase-3 engine, emits the actor's STORY message and
    the room's ambient stir, and returns the typed result with the next
    beat (or the epilogue on terminal).
    """
    participant = participant_for(instance, character)
    node = instance.current_node
    if node is None or instance.status != MissionStatus.ACTIVE:
        raise BeatActionError(_ERR_NOT_ACTIVE)

    presented = next(
        (
            p
            for p in build_option_list(instance, node, participant)
            if p.option.pk == option_id
            and (p.approach.pk if p.approach is not None else None) == approach_id
        ),
        None,
    )
    if presented is None:
        raise BeatActionError(_ERR_OPTION_NOT_LIVE)

    deed = resolve_option(
        instance,
        node,
        presented.option,
        participant,
        chosen_approach=presented.approach,
    )

    outcome_name = deed.outcome.name if deed.outcome_id else None
    story_text = _story_text_for(presented, outcome_name, instance.template.name)
    is_terminal = instance.current_node_id is None

    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is not None:
        send_narrative_message(
            recipients=[sheet],
            body=story_text,
            category=NarrativeCategory.STORY,
            ooc_note=f"Mission beat resolved (instance #{instance.pk}).",
        )
    location = character.location
    if location is not None:
        emit_ambient_room_stir(location, exclude=character)

    return ResolvedBeat(
        instance_id=instance.pk,
        outcome_name=outcome_name,
        story_text=story_text,
        is_terminal=is_terminal,
        next_beat=None if is_terminal else beat_for(instance, character),
        epilogue=instance.template.epilogue if is_terminal else "",
    )


def _story_text_for(
    presented: PresentedOption, outcome_name: str | None, template_name: str
) -> str:
    """The actor's STORY prose: authored route outcome_text when it exists.

    The route is re-derived the same way the engine matched it (option +
    rolled tier); BRANCH deeds have no outcome tier and fall through to
    the PLACEHOLDER template.
    """
    if outcome_name is not None:
        route = (
            MissionOptionRoute.objects.filter(
                option=presented.option,
                outcome_tier__name=outcome_name,
            )
            .only("outcome_text")
            .first()
        )
        if route is not None and route.outcome_text:
            return route.outcome_text
    outcome_clause = f" The outcome: {outcome_name}." if outcome_name else ""
    return _PLACEHOLDER_STORY_TEXT.format(
        template=template_name,
        label=presented.ic_framing,
        outcome_clause=outcome_clause,
    )
