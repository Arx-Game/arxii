"""Multi-person mission orchestration (Phase 4) — pure service functions.

A multi-person mission is *cooperative*: the receiver is the
contract-holder, the surfaced option list is the UNION of every
participant's single-participant Phase-3 option list (each entry already
owner-tagged), and when participants pick different options the node's
authored ``conflict_mode`` decides which option(s) actually resolve.

Two invariants this module enforces:

  * **Moral consequence follows the actor.** The deed ``actor`` is always
    the participant whose option actually performed. COINFLIP/VOTE resolve
    to ONE acting participant; JOINT runs every participant's own pick so
    each participant's per-act consequences/riders attach to *their own*
    deed (Phase-3 ``resolve_option(actor=participant)`` already records
    that participant — no cross-attribution).
  * **Contractual consequence is the contract-holder's alone.** Phase 4
    only keeps the contract-holder identifiable (``contract_holder``);
    cooldown / giver-standing / failure-penalty *application* is Phase 5
    (it needs a ``MissionGiver``/cooldown table that does not exist yet).

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

from django.db.models import Prefetch

from world.missions.constants import ConflictMode, JointCombine
from world.missions.models import MissionOptionRoute
from world.missions.services.resolution import (
    _finish_terminal,
    _route_next_node,
    present_options_for_character,
    resolve_option,
)
from world.missions.services.rewards import emit_terminal_rewards
from world.missions.types import GroupChoice

if TYPE_CHECKING:
    from collections.abc import Mapping

    from world.missions.models import (
        AffordanceBinding,
        MissionDeedRecord,
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
    by :func:`select_group_choice`.

    The node's options + their accepted affordances are fetched ONCE here
    (one ordered queryset with ``Prefetch(... to_attr=
    "accepted_affordances_cached")``) and reused across every participant
    via :func:`present_options_for_character`, so the per-participant
    union does NOT re-issue the options / accepted-affordances queries per
    participant (Phase-3 review Minor-1). This is the behavior-preserving
    shared-prefetch refactor the Phase-4 plan permits: Phase-3
    ``build_option_list``'s single-participant behavior is unchanged (it
    now delegates to the same extracted helper).
    """
    # M-1: Safe to leak on the SharedMemoryModel instance:
    # accepted_affordances is immutable authored graph data, not per-request
    # state. The Prefetch(to_attr="accepted_affordances_cached") attribute
    # would only be a leak hazard if its content varied across requests for
    # the same model row; the authored graph is shared and stable.
    options = list(
        node.options.all()
        .order_by("order", "pk")
        .prefetch_related(
            Prefetch(
                "accepted_affordances",
                to_attr="accepted_affordances_cached",
            )
        )
    )

    participants = instance.participants.all().order_by("pk")
    presented: list[PresentedOption] = []
    for participant in participants:
        presented.extend(present_options_for_character(participant.character, options))
    return presented


def _distinct_picked_options(
    picks: Mapping[MissionParticipant, MissionOption],
) -> list[MissionOption]:
    """The distinct picked options, deterministically ordered by option pk."""
    seen: dict[int, MissionOption] = {}
    for option in picks.values():
        seen.setdefault(option.pk, option)
    return [seen[pk] for pk in sorted(seen)]


def _pickers_of(
    picks: Mapping[MissionParticipant, MissionOption],
    option: MissionOption,
) -> list[MissionParticipant]:
    """Participants who picked ``option``, ordered by participant pk."""
    return sorted(
        (p for p, o in picks.items() if o.pk == option.pk),
        key=lambda p: p.pk,
    )


def _picks_instance(
    picks: Mapping[MissionParticipant, MissionOption],
) -> MissionInstance:
    """The shared instance the picking participants belong to.

    All picks in a group resolution are for participants of one instance;
    any participant resolves it (the identity map already holds it).
    """
    any_participant = next(iter(picks))
    return any_participant.instance


def _coinflip_choice(
    picks: Mapping[MissionParticipant, MissionOption],
) -> GroupChoice:
    """Uniform-random among the DISTINCT picked options.

    The acting participant is the lowest-pk participant who picked the
    winning option (deterministic tiebreak among same-option pickers).
    ``random.choice`` is the codebase's RNG convention (see
    ``world.checks.outcome_utils.select_weighted``); there is no seedable
    seam, so COINFLIP tests assert "one of the distinct picks" rather than
    a fixed value.
    """
    distinct = _distinct_picked_options(picks)
    winner = random.choice(distinct)  # noqa: S311 — game randomness, not crypto
    actor = _pickers_of(picks, winner)[0]
    return GroupChoice(is_joint=False, option=winner, actor=actor)


def _vote_choice(
    picks: Mapping[MissionParticipant, MissionOption],
) -> GroupChoice:
    """Plurality winner; tie broken by the contract-holder's pick, else
    lowest option pk. Acting participant = the contract-holder when they
    picked the winner, else the lowest-pk picker of the winner."""
    distinct = _distinct_picked_options(picks)
    counts: dict[int, int] = {option.pk: len(_pickers_of(picks, option)) for option in distinct}
    top = max(counts.values())
    tied = [option for option in distinct if counts[option.pk] == top]

    holder = contract_holder(_picks_instance(picks))
    holder_pick = picks.get(holder)

    if len(tied) == 1:
        winner = tied[0]
    elif holder_pick is not None and any(o.pk == holder_pick.pk for o in tied):
        winner = next(o for o in tied if o.pk == holder_pick.pk)
    else:
        winner = min(tied, key=lambda o: o.pk)

    if holder_pick is not None and holder_pick.pk == winner.pk:
        actor = holder
    else:
        actor = _pickers_of(picks, winner)[0]
    return GroupChoice(is_joint=False, option=winner, actor=actor)


def select_group_choice(
    node: MissionNode,
    picks: Mapping[MissionParticipant, MissionOption],
) -> GroupChoice:
    """Resolve contested picks per ``node.conflict_mode``.

    COINFLIP — uniform-random among the distinct picked options.
    VOTE — plurality; tie → contract-holder's pick if among the tied,
    else lowest option pk.
    JOINT — no single winner; the returned ``GroupChoice`` carries the
    full set of (participant, option) attempts (the orchestrator runs each
    and combines per ``joint_combine``/``joint_count``).

    ``picks`` is an input mapping (participant → their chosen option); the
    return is the typed :class:`GroupChoice`, never a bare dict.
    """
    if node.conflict_mode == ConflictMode.JOINT:
        attempts = tuple(
            sorted(picks.items(), key=lambda item: item[0].pk),
        )
        return GroupChoice(is_joint=True, attempts=attempts)
    if node.conflict_mode == ConflictMode.VOTE:
        return _vote_choice(picks)
    # ConflictMode.COINFLIP
    return _coinflip_choice(picks)


def _binding_for_pick(
    presented: list[PresentedOption],
    participant: MissionParticipant,
    option: MissionOption,
) -> AffordanceBinding | None:
    """The AffordanceBinding ``participant``'s pick of ``option`` uses.

    Recovered from the already-built group option list (the same union
    the participant picked from) — the first entry for ``option`` owned by
    this participant's character. AUTHORED picks carry no binding (None);
    an AFFORDANCE pick resolves through its binding's check_type / rider
    exactly as Phase-3 single-participant resolution does. No re-query: we
    walk the list ``build_group_option_list`` already produced.
    """
    for entry in presented:
        if entry.option.pk == option.pk and entry.owner.pk == participant.character_id:
            return entry.binding
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


def group_resolve_node(
    instance: MissionInstance,
    node: MissionNode,
    picks: Mapping[MissionParticipant, MissionOption],
) -> list[MissionDeedRecord]:
    """Resolve a multi-participant ``node`` from each participant's pick.

    COINFLIP / VOTE — one winning option resolves once via Phase-3
    ``resolve_option`` as the selected acting participant; the returned
    deed's ``actor`` is that participant's character (moral consequence
    follows the actor). Returns ``[deed]``.

    JOINT — every participant runs their OWN pick via Phase-3
    ``resolve_option(actor=participant)`` so each participant's check and
    per-act consequences/riders attach to their own deed (no
    cross-attribution). The combined success is then computed per
    ``joint_combine``/``joint_count`` and the node ROUTING/terminal is
    performed ONCE — based on that combined boolean — by reusing the
    Phase-3 routing/terminal helpers against the contract-holder pick's
    route-set. Returns the list of every per-participant deed.

    Phase 4 does NOT apply contractual consequences (cooldown,
    giver-standing, failure penalty) — those are contract-holder-scoped
    and applied in Phase 5. This function only ensures the deed ``actor``
    is the correct participant and keeps the holder identifiable via
    :func:`contract_holder`.
    """
    gc = select_group_choice(node, picks)

    # Build the owner-tagged group option list ONCE; bindings for every
    # pick are recovered from it (no per-attempt re-query).
    presented = build_group_option_list(instance, node)

    if not gc.is_joint:
        # COINFLIP / VOTE: exactly one option resolves once, as the
        # selected acting participant — Phase-3 resolve_option performs
        # the check, applies the route consequence + permitted rider, and
        # advances/terminates the run. We do NOT reimplement any of that.
        # select_group_choice guarantees option+actor are set when
        # is_joint is False (only JOINT leaves them None).
        actor = gc.actor
        winning_option = gc.option
        if actor is None or winning_option is None:
            msg = "non-JOINT GroupChoice must carry option and actor"
            raise ValueError(msg)
        binding = _binding_for_pick(presented, actor, winning_option)
        deed = resolve_option(instance, node, winning_option, actor, binding)
        return [deed]

    # JOINT: run every participant's own pick via Phase-3 resolve_option
    # in the routing-free mode (advance=False — Phase-5a I-1). Each call
    # records that participant as the deed actor and applies that
    # participant's own check + per-act consequences/riders — per-actor
    # moral consequence is correct by construction (no cross-attribution).
    # Crucially, NO per-attempt routing or terminal write touches the
    # instance: the only thing that routes/terminates is the combined
    # decision computed below. This is the primitive Phase 5b needs because
    # reward-line / contractual side effects can no longer be neutralized
    # by an "overwrite" trick.
    holder = contract_holder(instance)
    holder_option: MissionOption | None = None
    deeds: list[MissionDeedRecord] = []
    for participant, option in gc.attempts:
        if participant.pk == holder.pk:
            holder_option = option
        binding = _binding_for_pick(presented, participant, option)
        deeds.append(
            resolve_option(
                instance,
                node,
                option,
                participant,
                binding,
                advance=False,
            )
        )

    if holder_option is None:
        msg = (
            "JOINT node group_resolve_node requires the contract holder to "
            "have submitted a pick (its route-set carries the combined "
            "routing decision)."
        )
        raise ValueError(msg)

    # ROUTE ONCE based on the COMBINED result. _combined_route maps the
    # boolean to the holder pick's authored route via the same
    # CheckOutcome.success_level classification; _route_next_node /
    # _finish_terminal are the Phase-3 routing/terminal helpers reused
    # verbatim (not duplicated). DESIGN: JOINT nodes route by combined
    # success/failure BUCKET (best success-tier route / worst failure-tier
    # route), NOT per rolled tier — authors must author JOINT route-sets
    # accordingly.
    #
    # Because per-attempt resolve_option calls used ``advance=False``, the
    # instance position/status was never touched mid-loop; the compensation
    # block that previously restored ACTIVE/cleared completed_at after a
    # transient terminal is no longer needed.
    combined_success = _joint_combined_success(node, deeds)
    route = _combined_route(holder_option, combined_success)
    next_node = _route_next_node(route)
    if next_node is None:
        _finish_terminal(instance)
        # Phase 5b.0: JOINT terminal emits reward lines ONCE (not
        # per-attempt). The natural anchor is the contract holder's deed
        # (the holder's option's route-set drives _combined_route, so the
        # holder's deed is the JOINT decision's deed). Per-attempt deeds
        # carried advance=False, so no rewards were emitted by
        # resolve_option for any participant — this is the single
        # combined-decision emission.
        holder_deed = next(d for d in deeds if d.actor_id == holder.character_id)
        emit_terminal_rewards(instance, route, holder_deed)
    else:
        instance.current_node = next_node
        instance.save()

    return deeds
