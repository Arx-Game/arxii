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
    SupportDeclarationView,
    SupportMove,
)
from world.narrative.constants import NarrativeCategory
from world.narrative.services import emit_ambient_room_stir, send_narrative_message

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.missions.models import (
        MissionInstance,
        MissionNode,
        MissionParticipant,
        MissionRunTale,
    )


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


class SaveRunTaleError(BeatActionError):
    """A tale request that can't proceed (run not terminal / text invalid)."""


_ERR_NOT_PARTICIPANT = "You are not part of that mission."
_ERR_NOT_ACTIVE = "That mission is no longer in progress."
_ERR_NOT_CONTRACT_HOLDER = "Only the mission's contract holder can abandon it."
_ERR_OPTION_NOT_LIVE = (
    "That option isn't available to you here — it may have moved on, or "
    "you may need to be somewhere else."
)
_ERR_RUN_NOT_TERMINAL = (
    "This mission hasn't ended yet — you can only tell the tale of a completed or abandoned run."
)
_ERR_TALE_TOO_LONG = "Your tale is too long. Keep it under 5,000 characters."
_ERR_TALE_EMPTY = "Your tale cannot be empty."

_TERMINAL_STATUSES = frozenset(
    {
        MissionStatus.RESOLVED,
        MissionStatus.COMPLETE,
        MissionStatus.ABANDONED,
    }
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


def save_run_tale(instance: MissionInstance, character: ObjectDB, text: str) -> MissionRunTale:
    """Upsert a participant's tale on a terminal-status mission run (#2047).

    Guards: participant (404-shaped ``NotParticipantError``), run in a
    terminal status (``RESOLVED``/``COMPLETE``/``ABANDONED``), length cap.
    Deliberately no content gate (permissive-by-default IS the policy;
    ``save_deed_story`` has none either — the reviewer-confirmed precedent).

    On a legend-minting run, seeds ``LegendDeedStory`` rows for unstoried
    ``LegendEntry`` rows linked to the run's deeds whose persona matches
    the tale author's PRIMARY persona — or ``instance.accepted_as_persona``
    when the author is the contract holder (matching the emission-time
    persona rules). Seed, never overwrite.
    """
    from world.missions.constants import TALE_MAX_LENGTH  # noqa: PLC0415
    from world.missions.models import MissionRunTale  # noqa: PLC0415

    participant = participant_for(instance, character)
    if instance.status not in _TERMINAL_STATUSES:
        raise SaveRunTaleError(_ERR_RUN_NOT_TERMINAL)
    text = text.strip()
    if not text:
        raise SaveRunTaleError(_ERR_TALE_EMPTY)
    if len(text) > TALE_MAX_LENGTH:
        raise SaveRunTaleError(_ERR_TALE_TOO_LONG)

    with transaction.atomic():
        tale, _ = MissionRunTale.objects.update_or_create(
            instance=instance,
            participant=participant,
            defaults={"text": text},
        )
        _seed_legend_stories(instance, participant, text)
    return tale


def _seed_legend_stories(
    instance: MissionInstance,
    participant: MissionParticipant,
    text: str,
) -> None:
    """Seed ``LegendDeedStory`` rows for unstoried entries on this run's deeds.

    For every ``LegendEntry`` linked to the run's ``MissionDeedRecord`` rows
    that has no existing story by the tale author's persona — where the
    persona is the tale author's PRIMARY persona, or
    ``instance.accepted_as_persona`` when the author is the contract holder
    (matching the emission-time persona rules) — create a
    ``LegendDeedStory`` with the tale text. Seed, never overwrite.
    """
    from world.societies.models import LegendDeedStory, LegendEntry  # noqa: PLC0415
    from world.societies.spread_services import save_deed_story  # noqa: PLC0415

    sheet = participant.character.character_sheet
    if sheet is None:
        return
    if participant.is_contract_holder and instance.accepted_as_persona_id is not None:
        author_persona = instance.accepted_as_persona
    else:
        author_persona = sheet.primary_persona
    if author_persona is None:
        return

    entry_ids = set(instance.deeds.values_list("legend_entries", flat=True).distinct())
    if not entry_ids:
        return
    entries = list(LegendEntry.objects.filter(pk__in=entry_ids))
    matching_entries = [e for e in entries if e.persona_id == author_persona.pk]
    if not matching_entries:
        return

    storied_ids = set(
        LegendDeedStory.objects.filter(
            deed__in=matching_entries, author=author_persona
        ).values_list("deed_id", flat=True)
    )

    for entry in matching_entries:
        if entry.pk not in storied_ids:
            save_deed_story(author_persona=author_persona, deed=entry, text=text)


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

    # #2048: engagement-armed stakes — arm on the first player action, not
    # at assignment time. activate_stakes_for_instance is a no-op for free
    # runs (source_beat null) and unstaked beats, and is idempotent while
    # an activation is open — safe to call on every action.
    from world.missions.services.beat import activate_stakes_for_instance  # noqa: PLC0415

    stake_sheet = character.character_sheet
    if stake_sheet is not None:
        activate_stakes_for_instance(instance, [stake_sheet])

    outcome_name = deed.outcome.name if deed.outcome_id else None
    story_text = _story_text_for(presented, deed, instance.template.name)
    is_terminal = instance.current_node_id is None

    sheet = character.character_sheet
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
    """True once every participant has a ballot (a stage-1 pick) OR a support declaration."""
    from world.missions.models import MissionSupportDeclaration  # noqa: PLC0415

    n_active = instance.participants.count()
    n_picked = MissionGroupBallot.objects.filter(instance=instance, node=node).count()
    n_supported = MissionSupportDeclaration.objects.filter(
        instance=instance, snapshot__node=node
    ).count()
    return n_active > 0 and (n_picked + n_supported) >= n_active


def _resolve_group_if_ready(
    instance: MissionInstance, node: MissionNode
) -> list[MissionDeedRecord] | None:
    """Resolve the group node if the party is done, or the window expired; else None.

    "Done" is mode-specific: GROUP_VOTE needs every participant to have *voted*
    (stage 2); JOINT has no vote stage, so it resolves once every participant has
    *picked*. The timeout backstops both.

    Paused instances short-circuit to None BEFORE ever calling
    ``resolve_group_node`` (#1899 whole-branch review). ``resolve_group_node``
    itself also returns ``[]`` when paused (for the cron sweep, which calls it
    directly and only cares "did anything resolve"), but ``[] is not None`` —
    every one of this module's five play-surface callers treats a non-None
    return as "the beat really resolved." Without this early return, a paused
    instance whose ballots satisfy the ready condition would fool the caller
    into telling the player the beat resolved, when the mission is actually
    frozen.
    """
    if instance.is_paused:
        return None
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
        from world.missions.models import MissionSupportDeclaration  # noqa: PLC0415

        n_ballots = ballots.count()
        n_supports = MissionSupportDeclaration.objects.filter(
            instance=instance, snapshot__node=node
        ).count()
        done = (n_ballots + n_supports) >= n_active
    else:
        done = ballots.filter(voted_option__isnull=False).count() >= n_active
    if done:
        return resolve_group_node(instance, node)
    return None


def _resolve_if_expired(
    instance: MissionInstance, node: MissionNode
) -> list[MissionDeedRecord] | None:
    """Resolve the group node only if its vote window has elapsed; else None.

    The cheap start-of-action check: a fresh pick/vote can't *complete* the round
    before it's even recorded, so the only reason to resolve up front is a window
    that already expired (someone returning after the party left). The full
    readiness check (``_resolve_group_if_ready``) runs after the write.

    Paused instances short-circuit to None first — see ``_resolve_group_if_ready``'s
    docstring for why this must happen before ``resolve_group_node`` is ever reached.
    """
    if instance.is_paused:
        return None
    deadline = _group_window_deadline(instance, node)
    if deadline is not None and timezone.now() >= deadline:
        return resolve_group_node(instance, node)
    return None


def _group_beat_view(
    instance: MissionInstance,
    node: MissionNode,
    *,
    presented: list[PresentedOption] | None = None,
    character: ObjectDB | None = None,
) -> GroupBeatView:
    """Compose the group beat: union option list + every ballot's pick/vote + support moves.

    Pass ``presented`` when the caller already built the group option list (e.g.
    ``submit_group_pick`` after locating the picked entry) to avoid a second
    per-participant fan-out. The ballots are fetched once and the deadline / phase
    derived from them in Python (no extra ``Min``/``count`` queries).

    Pass ``character`` to populate ``support_moves`` for that viewer (#2046).
    """
    if presented is None:
        presented = build_group_option_list(instance, node)
    ballots = list(
        MissionGroupBallot.objects.filter(instance=instance, node=node)
        .select_related("participant")
        .order_by("participant__pk")
    )
    n_active = instance.participants.count()
    ballot_states = tuple(
        GroupBallotState(
            character_id=ballot.participant.character_id,
            character_name=ballot.participant.character.db_key,
            picked_option_id=ballot.picked_option_id,
            voted_option_id=ballot.voted_option_id,
        )
        for ballot in ballots
    )
    earliest = min((ballot.created_at for ballot in ballots), default=None)
    deadline = (
        earliest + timedelta(seconds=GROUP_VOTE_TIMEOUT_SECONDS) if earliest is not None else None
    )
    phase = PHASE_VOTE if (n_active > 0 and len(ballots) >= n_active) else PHASE_PICK

    # #2046: support moves for the viewing character + declared supports
    support_moves: tuple[SupportMove, ...] = ()
    if character is not None:
        from world.missions.services.support import support_moves_for  # noqa: PLC0415

        support_moves = tuple(support_moves_for(instance, node, character))
    declared_supports = _declared_supports_for(instance, node)

    return GroupBeatView(
        instance_id=instance.pk,
        node_key=node.key,
        flavor_text=node.flavor_text,
        conflict_mode=node.conflict_mode,
        phase=phase,
        options=tuple(_beat_option(presented_option) for presented_option in presented),
        ballots=ballot_states,
        expires_at=deadline.isoformat() if deadline is not None else None,
        support_moves=support_moves,
        declared_supports=declared_supports,
    )


def _resolved_group_result(instance: MissionInstance, character: ObjectDB) -> GroupBeatResult:
    """Build the resolved-beat payload after a group node advances/terminates.

    The per-actor STORY/ambient narrative split was emitted inside
    ``resolve_group_node`` (#887); this builds the requesting character's
    ``ResolvedBeat``: their own deed's ``outcome_text`` if they acted, else a
    generic ambient line (they already received the stir). The instance
    position/status was updated in-place by ``resolve_group_node``.
    """
    is_terminal = instance.current_node_id is None
    story_text = _group_resolution_story_text(instance, character)
    resolved = ResolvedBeat(
        instance_id=instance.pk,
        outcome_name=None,
        story_text=story_text,
        is_terminal=is_terminal,
        next_beat=None if is_terminal else beat_for(instance, character),
        epilogue=instance.template.epilogue if is_terminal else "",
    )
    return GroupBeatResult(group_beat=None, resolved=resolved)


def _group_resolution_story_text(instance: MissionInstance, character: ObjectDB) -> str:
    """The requesting character's STORY prose after a group node resolves (#887).

    If they were an acting participant, their own deed's ``outcome_text``;
    otherwise a generic ambient line (non-actors received the source-ambiguous
    stir already).
    """
    node = instance.current_node
    deed_qs = instance.deeds.filter(actor=character)
    if node is not None:
        deed_qs = deed_qs.filter(node=node)
    deed = deed_qs.order_by("-applied_at").first()
    if deed is None:
        return f"The party's effort resolves. (Mission #{instance.pk}.)"
    # The deed's own node is the resolved node (instance.current_node may be
    # None on a terminal resolution); build the presented list from it.
    presented = build_group_option_list(instance, deed.node)
    own_presented = next(
        (p for p in presented if p.owner.pk == character.pk and p.option.pk == deed.option_id),
        None,
    )
    if own_presented is None:
        return f"The party's effort resolves. (Mission #{instance.pk}.)"
    return _story_text_for(own_presented, deed, instance.template.name)


def group_beat(instance: MissionInstance, character: ObjectDB) -> GroupBeatResult:
    """Present the group decision beat, resolving first if the window expired."""
    participant_for(instance, character)
    node = _group_node(instance)
    if _resolve_if_expired(instance, node) is not None:
        return _resolved_group_result(instance, character)
    return GroupBeatResult(
        group_beat=_group_beat_view(instance, node, character=character), resolved=None
    )


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
    if _resolve_if_expired(instance, node) is not None:
        return _resolved_group_result(instance, character)
    presented = build_group_option_list(instance, node)
    entry = next(
        (
            presented_option
            for presented_option in presented
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
    # Reuse the option list already built above (the union doesn't change when a
    # pick is recorded) so the beat view doesn't re-run the per-participant fan-out.
    return GroupBeatResult(
        group_beat=_group_beat_view(instance, node, presented=presented), resolved=None
    )


def cast_group_vote(
    instance: MissionInstance,
    character: ObjectDB,
    *,
    option_id: int,
) -> GroupBeatResult:
    """Record ``character``'s stage-2 vote; auto-resolve when all have voted."""
    participant = participant_for(instance, character)
    node = _group_node(instance)
    if _resolve_if_expired(instance, node) is not None:
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


def _declared_supports_for(
    instance: MissionInstance, node: MissionNode
) -> tuple[SupportDeclarationView, ...]:
    """All declared supports at this node, visible to the party (#2046)."""
    from world.missions.models import MissionSupportDeclaration  # noqa: PLC0415

    decls = MissionSupportDeclaration.objects.filter(
        instance=instance, snapshot__node=node
    ).select_related("participant__character", "outcome")
    return tuple(
        SupportDeclarationView(
            character_id=decl.participant.character_id,
            character_name=decl.participant.character.db_key,
            label=(
                decl.pattern.name
                if decl.pattern_id
                else (decl.support_option.flavor_template or "Support")
            ),
            outcome_name=decl.outcome.name if decl.outcome_id else None,
            easing_banked=decl.easing_banked,
        )
        for decl in decls
    )


def declare_support_play(
    instance: MissionInstance,
    character: ObjectDB,
    *,
    source_kind: str,
    source_id: int,
) -> GroupBeatResult:
    """Declare a support move in place of a pick/vote (#2046).

    Thin player-facing wrapper: validates group-beat context, delegates to
    ``support.declare_support``, then returns the updated group beat (or the
    resolved beat if the declaration completed the party).
    """
    from world.missions.services.support import declare_support  # noqa: PLC0415

    participant_for(instance, character)
    node = _group_node(instance)
    if _resolve_if_expired(instance, node) is not None:
        return _resolved_group_result(instance, character)
    declare_support(instance, character, source_kind=source_kind, source_id=source_id)
    if _resolve_group_if_ready(instance, node) is not None:
        return _resolved_group_result(instance, character)
    return GroupBeatResult(
        group_beat=_group_beat_view(instance, node, character=character), resolved=None
    )


def maybe_pause_mission_for_disconnect(character_sheet: CharacterSheet) -> None:
    """Pause every active MissionInstance the character currently participates
    in, on disconnect (#1899).

    No scale exception — missions don't reach battle-scale participant counts.
    Pauses *all* matching instances, not just the first: nothing in
    world/missions/services/run.py prevents a character being an ACTIVE
    participant in more than one MissionInstance concurrently, so a naive
    .first() would silently leave a second concurrent mission unpaused.

    Deliberately per-instance ``.save(update_fields=...)`` rather than a bulk
    ``.filter(...).update(...)``: MissionInstance is a SharedMemoryModel
    (idmapper). A bulk queryset ``.update()`` writes the DB row directly and
    bypasses the identity map, so an already-cached MissionInstance Python
    object (e.g. one a caller elsewhere in the process is still holding) never
    sees ``is_paused`` flip — confirmed empirically: the DB row shows
    ``is_paused=True`` right after a bulk update, but the process's cached
    instance (and thus ``refresh_from_db()`` on it, since idmapper's
    model-construction hook returns the pre-existing cached object rather than
    applying the freshly queried row) still reads ``False``. Loading each
    instance and calling ``.save()`` goes through SharedMemoryModel's
    post-save cache refresh instead, so the in-memory singleton is updated
    too. The instance count here is bounded by one character's concurrent
    mission count (small), so the extra queries are cheap.
    """
    from world.missions.models import MissionInstance, MissionParticipant  # noqa: PLC0415

    instance_ids = MissionParticipant.objects.filter(
        character=character_sheet.character,
        instance__status=MissionStatus.ACTIVE,
    ).values_list("instance_id", flat=True)
    for instance in MissionInstance.objects.filter(pk__in=list(instance_ids)):
        instance.is_paused = True
        instance.save(update_fields=["is_paused"])
