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

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Min
from django.utils import timezone

from world.missions.constants import GROUP_VOTE_TIMEOUT_SECONDS, ConflictMode, MissionStatus
from world.missions.models import (
    MissionDeedRecord,
    MissionGroupBallot,
    MissionOptionRoute,
    MissionParticipant,
)
from world.missions.services.multiplayer import build_group_option_list, resolve_group_node
from world.missions.services.resolution import build_option_list, resolve_option
from world.missions.types import (
    BeatOption,
    BeatView,
    GroupBallotState,
    GroupBeatResult,
    GroupBeatView,
    PresentedOption,
    ResolvedBeat,
)
from world.narrative.constants import NarrativeCategory
from world.narrative.services import emit_ambient_room_stir, send_narrative_message

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionInstance, MissionNode


class BeatActionError(ValueError):
    """A player beat action that cannot proceed; carries a user-safe message."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class NotParticipantError(BeatActionError):
    """The character isn't on this mission — surfaced as 404, never 403.

    A non-participant probing instance ids must not learn which exist.
    """


class AbandonMissionError(BeatActionError):
    """An abandon request that can't proceed (not active / not contract holder)."""


_ERR_NOT_PARTICIPANT = "You are not part of that mission."
_ERR_NOT_ACTIVE = "That mission is no longer in progress."
_ERR_NOT_CONTRACT_HOLDER = "Only the mission's contract holder can abandon it."
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


def abandon_mission(instance: MissionInstance, character: ObjectDB) -> MissionInstance:
    """Abandon an ACTIVE mission at the contract holder's request (#1023).

    The player's deliberate walk-away. Mirrors the terminal write in
    ``resolution._finish_terminal`` (status → ABANDONED, stamp ``completed_at``,
    clear ``current_node``, tear down any spawned instanced room) but does NOT
    fire the Beat-completion seam — abandoning is not completing — and applies
    no standing penalty. The PC active-NPC-mission cap counts only ``ACTIVE``
    runs, so the slot frees automatically; the giver's ``NPCRoleCooldown`` is
    left intact so the same NPC can't be immediately re-rolled.

    Contract-holder-only solo path; multiplayer vote-to-abandon rides the
    multiplayer-engine API follow-up. Non-participant raises (404 at the view);
    not-active / not-contract-holder raise ``AbandonMissionError`` (400).
    """
    participant = participant_for(instance, character)
    if instance.status != MissionStatus.ACTIVE:
        raise AbandonMissionError(_ERR_NOT_ACTIVE)
    if not participant.is_contract_holder:
        raise AbandonMissionError(_ERR_NOT_CONTRACT_HOLDER)
    with transaction.atomic():
        instance.status = MissionStatus.ABANDONED
        instance.completed_at = timezone.now()
        instance.current_node = None
        instance.save()
        if instance.spawned_room_id is not None:
            # Reuse the instanced-room lifecycle service so an abandoned run
            # doesn't strand its spawned room (mirrors resolution teardown).
            from world.instances.services import complete_instanced_room  # noqa: PLC0415

            complete_instanced_room(instance.spawned_room.objectdb)
    return instance


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
    story_text = _story_text_for(presented, deed, instance.template.name)
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


def _story_text_for(presented: PresentedOption, deed: MissionDeedRecord, template_name: str) -> str:
    """The actor's STORY prose: authored outcome_text when it exists.

    A fired random-set candidate's outcome_text wins (#941 — the engine
    recorded which candidate fired on the deed); else the route's text,
    re-derived the same way the engine matched it (option + rolled tier).
    BRANCH deeds with neither fall through to the PLACEHOLDER template.
    """
    candidate = deed.route_candidate
    if candidate is not None and candidate.outcome_text:
        return candidate.outcome_text

    outcome_name = deed.outcome.name if deed.outcome_id else None
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


# ---------------------------------------------------------------------------
# #1036 — group (multi-participant) decision surface.
#
# Two-stage GROUP_VOTE: each participant PICKS their own option, then the party
# VOTES (any member, any surfaced option); plurality wins, ties random. JOINT
# collects picks only (everyone acts). Resolution fires when all have voted or
# the window (first pick + GROUP_VOTE_TIMEOUT_SECONDS) elapses — checked lazily
# on every access so correctness never waits on a background sweep.
# ---------------------------------------------------------------------------

PHASE_PICK = "pick"
PHASE_VOTE = "vote"

_ERR_VOTE_NOT_OPEN = "Voting hasn't opened yet — the party is still choosing."
_ERR_MUST_PICK_FIRST = "Submit your own pick before voting."
_ERR_VOTE_NOT_SURFACED = "You can only vote for an option the party has put forward."


def _group_node(instance: MissionInstance) -> MissionNode:
    """The current node of an ACTIVE run, or raise (no node / not active)."""
    node = instance.current_node
    if node is None or instance.status != MissionStatus.ACTIVE:
        raise BeatActionError(_ERR_NOT_ACTIVE)
    return node


def _group_window_deadline(instance: MissionInstance, node: MissionNode) -> datetime | None:
    """Vote-window deadline (earliest pick + timeout), or None before any pick."""
    earliest = MissionGroupBallot.objects.filter(instance=instance, node=node).aggregate(
        first=Min("created_at")
    )["first"]
    if earliest is None:
        return None
    return earliest + timedelta(seconds=GROUP_VOTE_TIMEOUT_SECONDS)


def _all_picked(instance: MissionInstance, node: MissionNode) -> bool:
    """True once every participant has a ballot (a stage-1 pick)."""
    n_active = instance.participants.count()
    n_picked = MissionGroupBallot.objects.filter(instance=instance, node=node).count()
    return n_active > 0 and n_picked >= n_active


def _resolve_group_if_ready(
    instance: MissionInstance, node: MissionNode
) -> list[MissionDeedRecord] | None:
    """Resolve the group node if the party is done, or the window expired; else None.

    "Done" is mode-specific: GROUP_VOTE needs every participant to have *voted*
    (stage 2); JOINT has no vote stage, so it resolves once every participant has
    *picked*. The timeout backstops both.
    """
    ballots = MissionGroupBallot.objects.filter(instance=instance, node=node)
    if not ballots.exists():
        return None
    deadline = _group_window_deadline(instance, node)
    if deadline is not None and timezone.now() >= deadline:
        return resolve_group_node(instance, node)
    n_active = instance.participants.count()
    if n_active <= 0:
        return None
    if node.conflict_mode == ConflictMode.JOINT:
        done = ballots.count() >= n_active
    else:
        done = ballots.filter(voted_option__isnull=False).count() >= n_active
    if done:
        return resolve_group_node(instance, node)
    return None


def _group_beat_view(instance: MissionInstance, node: MissionNode) -> GroupBeatView:
    """Compose the group beat: union option list + every ballot's pick/vote."""
    presented = build_group_option_list(instance, node)
    ballots = (
        MissionGroupBallot.objects.filter(instance=instance, node=node)
        .select_related("participant")
        .order_by("participant__pk")
    )
    ballot_states = tuple(
        GroupBallotState(
            character_id=ballot.participant.character_id,
            picked_option_id=ballot.picked_option_id,
            voted_option_id=ballot.voted_option_id,
        )
        for ballot in ballots
    )
    deadline = _group_window_deadline(instance, node)
    return GroupBeatView(
        instance_id=instance.pk,
        node_key=node.key,
        flavor_text=node.flavor_text,
        conflict_mode=node.conflict_mode,
        phase=PHASE_VOTE if _all_picked(instance, node) else PHASE_PICK,
        options=tuple(_beat_option(presented_option) for presented_option in presented),
        ballots=ballot_states,
        expires_at=deadline.isoformat() if deadline is not None else None,
    )


def _resolved_group_result(instance: MissionInstance, character: ObjectDB) -> GroupBeatResult:
    """Build the resolved-beat payload after a group node advances/terminates.

    The per-actor STORY/ambient narrative split is the group-UX concern of
    #887; this slice surfaces the mechanical result (outcome + next beat). The
    instance position/status was updated in-place by ``resolve_group_node``.
    """
    is_terminal = instance.current_node_id is None
    resolved = ResolvedBeat(
        instance_id=instance.pk,
        outcome_name=None,
        # PLACEHOLDER — group resolution prose lands with the #887 group beat UX.
        story_text=f"PLACEHOLDER — {instance.template.name}: the party commits and acts.",
        is_terminal=is_terminal,
        next_beat=None if is_terminal else beat_for(instance, character),
        epilogue=instance.template.epilogue if is_terminal else "",
    )
    return GroupBeatResult(group_beat=None, resolved=resolved)


def group_beat(instance: MissionInstance, character: ObjectDB) -> GroupBeatResult:
    """Present the group decision beat, resolving first if the window expired."""
    participant_for(instance, character)
    node = _group_node(instance)
    if _resolve_group_if_ready(instance, node) is not None:
        return _resolved_group_result(instance, character)
    return GroupBeatResult(group_beat=_group_beat_view(instance, node), resolved=None)


def submit_group_pick(
    instance: MissionInstance,
    character: ObjectDB,
    *,
    option_id: int,
    approach_id: int | None = None,
) -> GroupBeatResult:
    """Record ``character``'s stage-1 pick (must be one of their own live options)."""
    participant = participant_for(instance, character)
    node = _group_node(instance)
    if _resolve_group_if_ready(instance, node) is not None:
        return _resolved_group_result(instance, character)
    entry = next(
        (
            presented_option
            for presented_option in build_group_option_list(instance, node)
            if presented_option.option.pk == option_id
            and presented_option.owner.pk == character.pk
            and (presented_option.approach.pk if presented_option.approach else None) == approach_id
        ),
        None,
    )
    if entry is None:
        raise BeatActionError(_ERR_OPTION_NOT_LIVE)
    MissionGroupBallot.objects.update_or_create(
        instance=instance,
        node=node,
        participant=participant,
        defaults={
            "picked_option": entry.option,
            "picked_approach": entry.approach,
            "voted_option": None,
        },
    )
    # JOINT has no vote stage — the last pick resolves it (GROUP_VOTE returns
    # None here and opens the vote phase instead).
    if _resolve_group_if_ready(instance, node) is not None:
        return _resolved_group_result(instance, character)
    return GroupBeatResult(group_beat=_group_beat_view(instance, node), resolved=None)


def cast_group_vote(
    instance: MissionInstance,
    character: ObjectDB,
    *,
    option_id: int,
) -> GroupBeatResult:
    """Record ``character``'s stage-2 vote; auto-resolve when all have voted."""
    participant = participant_for(instance, character)
    node = _group_node(instance)
    if _resolve_group_if_ready(instance, node) is not None:
        return _resolved_group_result(instance, character)
    if not _all_picked(instance, node):
        raise BeatActionError(_ERR_VOTE_NOT_OPEN)
    ballot = MissionGroupBallot.objects.filter(
        instance=instance, node=node, participant=participant
    ).first()
    if ballot is None:
        raise BeatActionError(_ERR_MUST_PICK_FIRST)
    surfaced = set(
        MissionGroupBallot.objects.filter(instance=instance, node=node).values_list(
            "picked_option_id", flat=True
        )
    )
    if option_id not in surfaced:
        raise BeatActionError(_ERR_VOTE_NOT_SURFACED)
    ballot.voted_option_id = option_id
    ballot.save(update_fields=["voted_option"])
    if _resolve_group_if_ready(instance, node) is not None:
        return _resolved_group_result(instance, character)
    return GroupBeatResult(group_beat=_group_beat_view(instance, node), resolved=None)
