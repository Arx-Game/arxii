"""Multi-person mission orchestration (Phase 4) — pure service functions.

A multi-person mission is *cooperative*: the receiver is the
contract-holder, the surfaced option list is the UNION of every
participant's single-participant Phase-3 option list (each entry already
owner-tagged), and when participants pick different options the node's
authored ``conflict_mode`` decides which option(s) actually resolve.

Two invariants this module enforces:

  * **Moral consequence follows the actor.** The deed ``actor`` is always
    the participant whose option actually performed. GROUP_VOTE resolves
    to ONE acting participant; JOINT runs every participant's own pick so
    each participant's per-act consequences attach to *their own*
    deed (Phase-3 ``resolve_option(actor=participant)`` already records
    that participant — no cross-attribution).
  * **Contractual consequence is the contract-holder's alone.** Phase 4
    only keeps the contract-holder identifiable (``contract_holder``);
    cooldown / NPC-standing / failure-penalty *application* is Phase 5+
    (standing lives on :class:`world.npc_services.models.NPCStanding`;
    the engine using it for contractual consequence application beyond
    cooldown is Phase 5b+).

This module owns NO check/consequence/routing math: it reuses the Phase-3
per-character option-presentation body (extracted as
``present_options_for_character`` — ``build_option_list``'s
single-participant behavior is unchanged) and Phase-3 ``resolve_option``
UNCHANGED (for the actual per-actor resolution). It only orchestrates
*which* participant/option resolves and, for JOINT, applies the single
combined routing decision via the Phase-3 routing/terminal helpers
(``_route_next_node`` / ``_finish_terminal``) — never duplicating them.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Sum

from world.missions.constants import ConflictMode, JointCombine
from world.missions.models import MissionOptionRoute
from world.missions.services.resolution import (
    _current_room_profile_id,
    _finish_terminal,
    _route_next_node,
    option_is_locally_live,
    present_options_for_character,
    resolve_option,
)
from world.missions.services.rewards import emit_candidate_rewards, emit_terminal_rewards
from world.narrative.constants import NarrativeCategory
from world.narrative.services import emit_ambient_room_stir, send_narrative_message

if TYPE_CHECKING:
    from world.mechanics.models import ChallengeApproach
    from world.missions.models import (
        MissionDeedRecord,
        MissionGroupBallot,
        MissionInstance,
        MissionNode,
        MissionOption,
        MissionParticipant,
    )
    from world.missions.types import PresentedOption

# Established success-tier threshold. The codebase classifies a check
# outcome's tier by ``CheckOutcome.success_level`` (see
# ``world.conditions.services._SUCCESS_LEVEL`` = 1, mirrored by
# ``vitals``/``combat``): success_level >= 1 is a clear success, 0 is
# partial, < 0 is failure. A JOINT attempt "succeeded" iff its deed's
# resolved outcome is at this success tier. A BRANCH attempt (deed.outcome
# is None — no dice) is NOT a dice success.
_SUCCESS_LEVEL = 1


def _banked_easing_for_node(instance: MissionInstance, node: MissionNode) -> int:
    """Sum all banked easing declarations for this node entry (#2046)."""
    from world.missions.models import MissionSupportDeclaration  # noqa: PLC0415

    return (
        MissionSupportDeclaration.objects.filter(instance=instance, snapshot__node=node).aggregate(
            total=Sum("easing_banked")
        )["total"]
        or 0
    )


def contract_holder(instance: MissionInstance) -> MissionParticipant:
    """Return the instance's single contract-holding participant.

    Exactly one participant per instance is the contract holder (enforced
    by ``MissionParticipant.clean``). Phase 4 does NOT apply the
    contract-holder-scoped contractual consequences (cooldown,
    giver-standing, failure penalty) — those are Phase 5; this helper only
    keeps the holder identifiable.
    """
    return instance.participants.get(is_contract_holder=True)


def build_group_option_list(
    instance: MissionInstance,
    node: MissionNode,
) -> list[PresentedOption]:
    """Union of every participant's Phase-3 option list at ``node``.

    For each participant ``p`` (ordered by participant pk for a stable,
    deterministic result), the participant's Phase-3 per-viewer option
    list is appended verbatim; each ``PresentedOption.owner`` is already
    that participant's character (Phase 3 sets it). The merge is purely
    additive — players still pick; conflicting picks are arbitrated later
    by :func:`resolve_group_node` (GROUP_VOTE tally / JOINT combine).

    The location conjunct (#885/#887) is applied **per participant**: each
    participant only sees options live where *their* character currently stands
    (mirroring the solo ``build_option_list`` — ANYWHERE always live, ANCHOR/
    ROOMS/INSTANCE gated on the participant's room). A node with the default
    ANYWHERE mode surfaces every option to everyone, unchanged.

    The node's options are fetched ONCE and reused across every participant, so
    the union does NOT re-issue the options query per participant. Phase-3
    ``build_option_list``'s single-participant behavior is unchanged (it
    delegates to the same extracted helper + conjunct).
    """
    # select_related("challenge") + prefetch "locations" so neither the
    # CHALLENGE-branch FK walk (in present_options_for_character) nor the
    # location conjunct's per-option ``locations`` M2M fires a query per option
    # per participant — the options list is built once and reused.
    options = list(
        node.options.select_related("challenge")
        .prefetch_related("locations")  # noqa: PREFETCH_STRING
        .order_by("order", "pk")
    )

    participants = instance.participants.all().order_by("pk")
    presented: list[PresentedOption] = []
    for participant in participants:
        here = _current_room_profile_id(participant.character)
        local = [opt for opt in options if option_is_locally_live(opt, node, instance, here)]
        presented.extend(present_options_for_character(participant.character, local))
    return presented


def resolve_group_node(
    instance: MissionInstance,
    node: MissionNode,
) -> list[MissionDeedRecord]:
    """Resolve a group ``node`` from its collected ``MissionGroupBallot`` rows (#1036).

    GROUP_VOTE — winner = plurality of the stage-2 votes (falling back to the
    stage-1 picks when nobody voted), ties broken at random; it resolves ONCE
    via the Phase-3 path as a *picker* of the winning option (holder preferred),
    so moral consequence follows the actor.
    JOINT — every participant's own pick resolves in parallel; the combined
    result routes once.

    Ballots are deleted after resolution. Returns the resulting deeds; an empty
    list when no ballots exist (nothing to resolve) OR when ``instance`` is
    paused (#1899) — a disconnect-pause freezes group resolution too, and this
    is the single choke point both the lazy on-access path
    (``_resolve_group_if_ready``) and the cron backstop sweep
    (``resolve_expired_group_votes``) call into, so gating here covers both
    callers rather than just one.
    """
    if instance.is_paused:
        return []

    from world.missions.models import MissionGroupBallot  # noqa: PLC0415

    ballots = list(
        MissionGroupBallot.objects.filter(instance=instance, node=node).select_related(
            "participant", "picked_option", "voted_option"
        )
    )
    if not ballots:
        return []
    # Resolution + ballot cleanup are one atomic unit: ``resolve_option`` always
    # creates a fresh (non-idempotent) deed, so a mid-resolution raise must roll
    # back any partial deeds rather than leave the node wedged with stale ballots
    # that a retry would double-resolve.
    with transaction.atomic():
        presented = build_group_option_list(instance, node)
        easing = _banked_easing_for_node(instance, node)
        if node.conflict_mode == ConflictMode.JOINT:
            picks = {ballot.participant: ballot.picked_option for ballot in ballots}
            attempts = tuple(sorted(picks.items(), key=lambda item: item[0].pk))
            deeds = _resolve_joint(instance, node, presented, attempts, extra_modifiers=easing)
        else:
            option, actor = _tally_group_winner(ballots)
            deeds = _resolve_single_winner(
                instance, node, presented, option, actor, extra_modifiers=easing
            )
        MissionGroupBallot.objects.filter(instance=instance, node=node).delete()
    # Per-actor STORY + ambient stir (#887). Emitted OUTSIDE the atomic block
    # so narrative side-effects don't roll back with a partial-resolution retry;
    # both the play surface and the cron sweep (``resolve_expired_group_votes``)
    # reach here, so timed-out resolutions emit the same prose.
    _emit_group_resolution_narrative(instance, presented, deeds)
    return deeds


def _emit_group_resolution_narrative(
    instance: MissionInstance,
    presented: list[PresentedOption],
    deeds: list[MissionDeedRecord],
) -> None:
    """Per-actor STORY + source-ambiguous ambient stir on group resolution (#887).

    Each acting participant gets their own deed's ``outcome_text`` as a STORY
    message (the actor/audience split the solo path established at
    ``resolve_beat_option``). Non-acting participants and room bystanders get
    the ambient stir. Best-effort and quiet: a sheet-less actor or a run with no
    anchor room emits nothing.
    """
    from world.missions.services.play import _story_text_for  # noqa: PLC0415

    template_name = instance.template.name
    presented_by_owner_option = {(p.owner.pk, p.option.pk): p for p in presented}
    for deed in deeds:
        presented_opt = presented_by_owner_option.get((deed.actor_id, deed.option_id))
        if presented_opt is None:
            continue
        story_text = _story_text_for(presented_opt, deed, template_name)
        actor = deed.actor
        sheet = getattr(actor, "sheet_data", None)  # noqa: GETATTR_LITERAL
        if sheet is not None:
            send_narrative_message(
                recipients=[sheet],
                body=story_text,
                category=NarrativeCategory.STORY,
                ooc_note=f"Mission group beat resolved (instance #{instance.pk}).",
            )
    anchor_room = instance.anchor_room
    if anchor_room is not None:
        emit_ambient_room_stir(anchor_room)


def _tally_group_winner(
    ballots: list[MissionGroupBallot],
) -> tuple[MissionOption, MissionParticipant]:
    """The GROUP_VOTE winning option + acting participant from the ballots.

    Winner = plurality of cast votes (``voted_option``); when nobody voted, fall
    back to the stage-1 picks. Ties break uniformly at random (the COINFLIP
    element folded in). The actor is a *picker* of the winning option — the
    contract holder when they picked it, else the lowest-pk picker. Votes choose
    the option; picks choose who can actually perform it.

    Votes are filtered to options still *surfaced* (currently picked by someone)
    at tally time — a participant can re-pick after others voted for their old
    option, which would otherwise leave a vote-winner with no picker. This keeps
    the winner always pickable (``pickers`` is never empty).
    """
    surfaced = {ballot.picked_option_id for ballot in ballots}
    voted = [
        ballot.voted_option
        for ballot in ballots
        if ballot.voted_option_id is not None and ballot.voted_option_id in surfaced
    ]
    tally = voted or [ballot.picked_option for ballot in ballots]
    counts: dict[int, int] = {}
    by_pk: dict[int, MissionOption] = {}
    for option in tally:
        counts[option.pk] = counts.get(option.pk, 0) + 1
        by_pk[option.pk] = option
    top = max(counts.values())
    tied = [by_pk[pk] for pk in sorted(counts) if counts[pk] == top]
    winner = tied[0] if len(tied) == 1 else random.choice(tied)  # noqa: S311

    # The actor is a picker of the winner, holder preferred. ``is_contract_holder``
    # is already loaded on each ballot's participant (select_related upstream), so
    # we find the holder among the pickers in-memory — no ``contract_holder`` query.
    pickers = sorted(
        (ballot.participant for ballot in ballots if ballot.picked_option_id == winner.pk),
        key=lambda participant: participant.pk,
    )
    actor = next((p for p in pickers if p.is_contract_holder), pickers[0])
    return winner, actor


def _approach_for_pick(
    presented: list[PresentedOption],
    participant: MissionParticipant,
    option: MissionOption,
) -> ChallengeApproach | None:
    """The ``ChallengeApproach`` ``participant``'s pick of ``option`` uses.

    Recovered from the already-built group option list (the same union the
    participant picked from) — the first entry for ``option`` owned by this
    participant's character. AUTHORED picks carry no approach (None); a
    CHALLENGE pick carries the approach the runtime fan-out selected for
    this participant. No re-query: we walk the list
    :func:`build_group_option_list` already produced.
    """
    for entry in presented:
        if entry.option.pk == option.pk and entry.owner.pk == participant.character_id:
            return entry.approach
    return None


def _is_success_tier(deed: MissionDeedRecord) -> bool:
    """True iff the deed's resolved outcome is at the success tier.

    Reuses the codebase's ``CheckOutcome.success_level`` classification
    (the same notion ``conditions``/``vitals``/``combat`` use). A BRANCH
    deed has ``outcome is None`` (no dice) and is not a dice success.
    """
    if deed.outcome is None:
        return False
    return int(deed.outcome.success_level) >= _SUCCESS_LEVEL


def _joint_combined_success(
    node: MissionNode,
    deeds: list[MissionDeedRecord],
) -> bool:
    """Combine per-participant deeds per the node's ``joint_combine``.

    ANY — at least one attempt at the success tier; ALL — every attempt;
    COUNT — at least ``node.joint_count`` attempts.
    """
    successes = sum(1 for deed in deeds if _is_success_tier(deed))
    if node.joint_combine == JointCombine.ANY:
        return successes >= 1
    if node.joint_combine == JointCombine.ALL:
        return successes == len(deeds)
    # JointCombine.COUNT — joint_count is required by MissionNode.clean.
    return successes >= node.joint_count


def _combined_route(
    holder_option: MissionOption,
    combined_success: bool,
) -> MissionOptionRoute:
    """The single route the combined JOINT result takes.

    Routing is computed ONCE from the boolean combined result against the
    contract-holder pick's authored route-set. The boolean is mapped to a
    route by the SAME ``CheckOutcome.success_level`` classification used
    everywhere else (no new success predicate): a combined success takes
    the holder-option route whose outcome tier is at the success tier
    (highest ``success_level``); a combined failure takes the route whose
    tier is below it (lowest ``success_level``). Ties on level break by
    route pk for determinism. A BRANCH-style null-tier route is never a
    JOINT routing target (JOINT nodes resolve CHECK picks).
    """
    routes = list(
        MissionOptionRoute.objects.filter(
            option=holder_option,
            outcome_tier__isnull=False,
        ).select_related("outcome_tier")
    )
    if not routes:
        msg = (
            f"JOINT contract-holder option {holder_option.pk} has no "
            f"outcome-tier routes — route-set incompleteness (graph-level "
            f"authoring error)."
        )
        raise ValueError(msg)

    success_routes = [r for r in routes if int(r.outcome_tier.success_level) >= _SUCCESS_LEVEL]
    fail_routes = [r for r in routes if int(r.outcome_tier.success_level) < _SUCCESS_LEVEL]
    pool = success_routes if combined_success else fail_routes
    if not pool:
        msg = (
            f"JOINT contract-holder option {holder_option.pk} has no "
            f"{'success' if combined_success else 'failure'}-tier route for "
            f"the combined result — route-set incompleteness."
        )
        raise ValueError(msg)

    # Representative tier: best success / worst failure, then route pk.
    pool.sort(
        key=lambda r: (int(r.outcome_tier.success_level), r.pk),
        reverse=combined_success,
    )
    return pool[0]


def _resolve_single_winner(  # noqa: PLR0913
    instance: MissionInstance,
    node: MissionNode,
    presented: list[PresentedOption],
    option: MissionOption,
    actor: MissionParticipant,
    *,
    extra_modifiers: int = 0,
) -> list[MissionDeedRecord]:
    """Resolve ONE winning option once, as ``actor`` (the GROUP_VOTE path).

    Phase-3 ``resolve_option`` performs the check, applies the route
    consequence, and advances/terminates the run — we reimplement none of it.
    Moral consequence follows ``actor`` (a picker of the winning option).
    """
    approach = _approach_for_pick(presented, actor, option)
    deed = resolve_option(
        instance, node, option, actor, chosen_approach=approach, extra_modifiers=extra_modifiers
    )
    return [deed]


def _resolve_joint(
    instance: MissionInstance,
    node: MissionNode,
    presented: list[PresentedOption],
    attempts: tuple[tuple[MissionParticipant, MissionOption], ...],
    *,
    extra_modifiers: int = 0,
) -> list[MissionDeedRecord]:
    """JOINT: every participant runs their OWN pick; combined result routes once.

    Each ``resolve_option(actor=participant)`` records that participant's deed
    and applies their own check + per-act consequences (no cross-attribution).
    The combined success (per ``joint_combine``/``joint_count``) drives a single
    routing/terminal decision against the contract holder's pick route-set.

    Phase 4 does NOT apply contractual consequences (cooldown, giver-standing,
    failure penalty) — those are contract-holder-scoped and applied in Phase 5.

    ``attempts`` is the (participant, option) set, ordered by participant pk.
    """
    # JOINT: run every participant's own pick via Phase-3 resolve_option
    # in the routing-free mode (advance=False — Phase-5a I-1). Each call
    # records that participant as the deed actor and applies that
    # participant's own check + per-act consequences — per-actor
    # moral consequence is correct by construction (no cross-attribution).
    # Crucially, NO per-attempt routing or terminal write touches the
    # instance: the only thing that routes/terminates is the combined
    # decision computed below. This is the primitive Phase 5b needs because
    # reward-line / contractual side effects can no longer be neutralized
    # by an "overwrite" trick.
    holder = contract_holder(instance)
    attempt_option: dict[int, MissionOption] = {}
    deeds: list[MissionDeedRecord] = []
    for participant, option in attempts:
        attempt_option[participant.pk] = option
        approach = _approach_for_pick(presented, participant, option)
        deeds.append(
            resolve_option(
                instance,
                node,
                option,
                participant,
                chosen_approach=approach,
                advance=False,
                extra_modifiers=extra_modifiers,
            )
        )

    # The combined decision routes through one anchor participant's option
    # route-set. Normally that's the contract holder; on a timeout/partial
    # where the holder never picked, fall back to the lowest-pk attempt so the
    # node still resolves rather than raising (#1036). ``attempts`` is non-empty.
    anchor = holder if holder.pk in attempt_option else attempts[0][0]
    anchor_option = attempt_option[anchor.pk]

    # ROUTE ONCE based on the COMBINED result. _combined_route maps the
    # boolean to the anchor pick's authored route via the same
    # CheckOutcome.success_level classification; _route_next_node /
    # _finish_terminal are the Phase-3 routing/terminal helpers reused
    # verbatim (not duplicated). DESIGN: JOINT nodes route by combined
    # success/failure BUCKET (best success-tier route / worst failure-tier
    # route), NOT per rolled tier — authors must author JOINT route-sets
    # accordingly. Per-attempt resolve_option calls used ``advance=False``, so
    # the instance position/status was never touched mid-loop.
    combined_success = _joint_combined_success(node, deeds)
    route = _combined_route(anchor_option, combined_success)
    next_node, candidate = _route_next_node(route)
    anchor_deed = next(d for d in deeds if d.actor_id == anchor.character_id)
    if candidate is not None:
        # #941: record the fired random-set candidate on the anchor deed and
        # emit its reward bundle once (on selection, like the solo path).
        anchor_deed.route_candidate = candidate
        anchor_deed.save(update_fields=["route_candidate"])
        emit_candidate_rewards(instance, candidate, anchor_deed)
    if next_node is None:
        _finish_terminal(instance, route=route)
        # Phase 5b.0: JOINT terminal emits the route's reward lines ONCE.
        emit_terminal_rewards(instance, route, anchor_deed)
    else:
        instance.current_node = next_node
        instance.save()

    return deeds
