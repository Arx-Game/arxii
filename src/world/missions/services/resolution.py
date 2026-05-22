"""Mission resolution engine (Phase 3) — pure service functions.

This module is the runtime that walks a :class:`MissionInstance` through its
authored graph. It owns NO new check/consequence math: it reuses
``world.checks.perform_check`` for the dice and
``world.checks.consequence_resolution.apply_resolution`` for the effects,
mirroring ``world.mechanics.challenge_resolution`` (notably its
``_select_consequence`` synthetic-fallback pattern).

Phase 3 is SINGLE-participant: ``viewer``/``actor`` is the one acting
participant. Multi-participant union/arbitration is Phase 4.

Design invariants honored here:
  * difficulty for an AUTHORED CHECK is ``instance.template.risk_tier`` (the
    authored DC); for a CHALLENGE CHECK it is the challenge's ``severity``
    (design §8.4 Q4). ``base_risk`` is the surfaced "Risk" axis, never the DC.
  * a route's authored ``consequence`` is applied when set; otherwise a
    synthetic UNSAVED fallback ``Consequence`` is built so
    ``apply_resolution`` is still called uniformly (and returns [] for the
    unsaved row — mirrors ``challenge_resolution._select_consequence``).
  * M1: never trust a possibly-stale cached ``instance.current_node``; engine
    functions operate on the ``node`` argument and write (not read) the FK.
  * Phase 5b.0: TERMINAL routes (next_node is None) emit
    :class:`MissionDeedRewardLine` rows from
    :class:`MissionOptionRouteReward` templates on the route via
    :func:`emit_terminal_rewards`. Non-terminal routes still emit no
    reward lines; a terminal route with no authored reward templates
    likewise emits zero lines (returns an empty list).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.checks.consequence_resolution import apply_resolution
from world.checks.models import Consequence
from world.checks.outcome_utils import select_weighted
from world.checks.services import perform_check
from world.checks.types import CheckResult, PendingResolution, ResolutionContext
from world.missions.constants import MissionStatus, OptionKind, OptionSource
from world.missions.models import (
    MissionDeedRecord,
    MissionNodeSnapshot,
    MissionOptionRoute,
)
from world.missions.predicates import CharacterPredicateContext, evaluate
from world.missions.services.beat import on_mission_complete_for_beat
from world.missions.services.challenge_options import challenge_options_for_character
from world.missions.services.rewards import emit_terminal_rewards
from world.missions.types import PresentedOption
from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from collections.abc import Iterable

    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.mechanics.models import ChallengeApproach
    from world.missions.models import (
        MissionInstance,
        MissionNode,
        MissionOption,
        MissionParticipant,
    )

_ERR_CHECK_NO_TYPE = (
    "OptionKind.CHECK option {option_pk} has no resolvable check_type "
    "(neither a chosen binding's check_type nor authored_check_type) — "
    "authoring/configuration error."
)
_ERR_CHALLENGE_NO_APPROACH = (
    "CHALLENGE option {option_pk} resolved without a chosen approach — the "
    "caller must pass the ChallengeApproach the player picked."
)
_ERR_CHALLENGE_NO_CHALLENGE = (
    "CHALLENGE option {option_pk} has no challenge — clean() should forbid "
    "this; the row is corrupt."
)
_ERR_NO_OUTCOME_TIERS = "Cannot synthesize an auto-success result: no CheckOutcome tiers exist."


def build_option_list(
    instance: MissionInstance,  # noqa: ARG001 — part of the stable engine signature; Phase 4 unions across the instance's participants
    node: MissionNode,
    viewer: MissionParticipant,
) -> list[PresentedOption]:
    """Surface the options the acting ``viewer`` can take at ``node``.

    For each :class:`MissionOption` on ``node``:

      * CHALLENGE source — fans out via
        :func:`~world.missions.services.challenge_options.challenge_options_for_character`
        over the option's attached challenge's qualifying approaches.
      * AUTHORED source — included iff its ``visibility_rule`` predicate
        passes for the viewer's character.

    Merge is additive (no arbitration — the player picks later). Order is
    deterministic: option ``order``, then approach pk for fanned-out
    CHALLENGE entries.

    Phase 3 is single-participant; ``instance`` is accepted for signature
    stability (Phase 4 unions across ``instance.participants``).
    """
    # select_related("challenge") so the CHALLENGE-branch FK walk in
    # present_options_for_character doesn't fire one query per option.
    options = node.options.select_related("challenge").order_by("order", "pk")
    return present_options_for_character(viewer.character, options)


def present_options_for_character(
    character: ObjectDB,
    options: Iterable[MissionOption],
) -> list[PresentedOption]:
    """Present an already-ordered ``options`` iterable for one character.

    The single-participant body of :func:`build_option_list`, extracted so
    Phase-4 ``build_group_option_list`` can fetch the node's options ONCE and
    reuse them across every participant. ``options`` MUST already be ordered
    by the caller (``order``, then ``pk``) — this preserves
    :func:`build_option_list`'s exact behavior; it just no longer owns the
    queryset construction. A CHALLENGE-sourced option fans out per qualifying
    ``ChallengeApproach`` via
    :func:`~world.missions.services.challenge_options.challenge_options_for_character`.
    """
    presented: list[PresentedOption] = []
    for option in options:
        if option.source_kind == OptionSource.CHALLENGE:
            challenge = option.challenge
            if challenge is None:
                # DESIGN: defense-in-depth — clean() forbids this state for
                # CHALLENGE source. Unreachable in normal operation.
                raise ValueError(_ERR_CHALLENGE_NO_CHALLENGE.format(option_pk=option.pk))
            presented.extend(
                PresentedOption(
                    option=option,
                    kind=option.option_kind,
                    check_type=co.check_type,
                    base_risk=0,
                    ic_framing=co.approach.display_name,
                    owner=character,
                    approach=co.approach,
                )
                for co in challenge_options_for_character(challenge, character)
            )
        elif evaluate(option.visibility_rule, CharacterPredicateContext(character)):
            # OptionSource.AUTHORED, visibility predicate satisfied.
            presented.append(
                PresentedOption(
                    option=option,
                    kind=option.option_kind,
                    check_type=option.authored_check_type,
                    base_risk=option.authored_base_risk,
                    ic_framing=option.authored_ic_framing,
                    owner=character,
                )
            )
    return presented


def enter_node(instance: MissionInstance, node: MissionNode) -> None:
    """Record entry into ``node`` and advance the run's position.

    Writes one :class:`MissionNodeSnapshot` per participant (Phase 3:
    typically one) — the snapshot rows ARE the once-per-entry evaluation
    record (the instance carries no mutable state blob). Then sets
    ``instance.current_node = node`` and saves.

    M1: operates on the ``node`` argument and only WRITES the FK; it never
    reads a possibly-stale cached ``instance.current_node``.
    """
    for participant in instance.participants.all():
        MissionNodeSnapshot.objects.create(
            instance=instance,
            node=node,
            participant=participant,
        )
    instance.current_node = node
    instance.save()


def _resolve_check_type(option: MissionOption) -> CheckType:
    """The CheckType for an AUTHORED CHECK option; raises if unset.

    A CHECK option's ``clean()`` already requires ``authored_check_type``
    for AUTHORED-source options; this is the runtime defensive guard.
    """
    check_type = option.authored_check_type
    if check_type is None:
        raise ValueError(_ERR_CHECK_NO_TYPE.format(option_pk=option.pk))
    return check_type


def _auto_success_result(check_type: CheckType) -> CheckResult:
    """A synthetic CheckResult landing in the top outcome tier, no roll.

    An ``auto_succeeds`` ChallengeApproach trivializes the obstacle — the
    capability simply wins (findings doc Q3). The synthesized result carries
    the top ``CheckOutcome`` (highest ``success_level``) and neutral roll
    fields so the unchanged routing/consequence pipeline keys on it exactly
    like a real roll.
    """
    top = CheckOutcome.objects.order_by("-success_level").first()
    if top is None:
        raise ValueError(_ERR_NO_OUTCOME_TIERS)
    return CheckResult(
        check_type=check_type,
        outcome=top,
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )


def _resolve_challenge_check(
    option: MissionOption,
    character: ObjectDB,
    chosen_approach: ChallengeApproach | None,
) -> CheckResult:
    """Resolve a CHALLENGE option's check via the player's chosen approach.

    The approach supplies the ``CheckType``; the challenge's ``severity`` is
    the difficulty (design §8.4 Q4 — only ``severity`` rides along into a
    missions context). An ``auto_succeeds`` approach skips the roll and lands
    in the top tier. The challenge is consumed as authored data —
    ``resolve_challenge`` is never called (findings doc Q2).

    The data-source integration also means ``ChallengeApproach.action_template``
    overrides and per-approach ``ApproachConsequence`` rows are NOT honored
    here — missions own the routes and consequences; the approach contributes
    only its capability gate, ``check_type``, and (when set) ``auto_succeeds``.
    """
    if chosen_approach is None:
        raise ValueError(_ERR_CHALLENGE_NO_APPROACH.format(option_pk=option.pk))
    if chosen_approach.auto_succeeds:
        return _auto_success_result(chosen_approach.check_type)
    challenge = option.challenge
    if challenge is None:
        # DESIGN: defense-in-depth — clean() forbids this state for CHALLENGE
        # source. Unreachable in normal operation.
        raise ValueError(_ERR_CHALLENGE_NO_CHALLENGE.format(option_pk=option.pk))
    return perform_check(
        character,
        chosen_approach.check_type,
        target_difficulty=challenge.severity,
    )


def _select_route_consequence(
    route: MissionOptionRoute,
    result: CheckResult,
) -> Consequence:
    """Authored route consequence if set, else a synthetic UNSAVED fallback.

    Mirrors ``world.mechanics.challenge_resolution._select_consequence``: an
    unsaved Consequence makes ``apply_resolution`` a uniform no-op (returns
    []), so callers never special-case "this route has no effect".
    """
    if route.consequence_id is not None:
        return route.consequence
    outcome = result.outcome
    return Consequence(
        outcome_tier=outcome,
        label=str(outcome.name) if outcome else "Unknown",
        weight=1,
        character_loss=False,
    )


def _route_next_node(route: MissionOptionRoute) -> MissionNode | None:
    """Destination for ``route``: a weighted candidate when randomized,
    else ``target_node`` (which may be null = terminal)."""
    if route.is_random_set:
        candidates = list(route.candidates.all())
        if candidates:
            return select_weighted(candidates).target_node
        return None
    return route.target_node


def _finish_terminal(instance: MissionInstance) -> None:
    """Mark the run complete (terminal route reached).

    Phase 5b.3: after the status write, notify the Mission→Beat seam. The
    call is a cheap no-op when ``instance.source_beat_id is None`` (a free
    run); when set, it appends one :class:`MissionBeatTriggerRecord` to the
    seam's stub-record log. The actual Beat-completion engine is deferred —
    see :mod:`world.missions.services.beat` for the three deferred
    product-level design questions. JOINT terminals call ``_finish_terminal``
    exactly once (Phase 4 invariant), so the seam fires exactly once per
    instance termination.
    """
    instance.status = MissionStatus.COMPLETE
    instance.completed_at = timezone.now()
    instance.current_node = None
    instance.save()
    on_mission_complete_for_beat(instance)


def resolve_option(  # noqa: PLR0913 — stable engine signature; 4 positional
    # args identify "who-resolves-what-where" and are co-equal, plus the
    # keyword-only ``chosen_approach``/``advance`` toggles. Collapsing them
    # into a dataclass would obscure call sites.
    instance: MissionInstance,
    node: MissionNode,
    option: MissionOption,
    actor: MissionParticipant,
    *,
    chosen_approach: ChallengeApproach | None = None,
    advance: bool = True,
) -> MissionDeedRecord:
    """Resolve ``actor`` taking ``option`` at ``node``; return its deed.

    BRANCH options route the graph with no dice. CHECK options either:

      * AUTHORED — roll ``perform_check`` at
        ``instance.template.risk_tier``.
      * CHALLENGE — resolve via the player's ``chosen_approach``: run
        ``perform_check`` at the challenge's ``severity`` (or, when the
        approach is ``auto_succeeds``, synthesize a top-tier outcome with
        no roll).

    Either CHECK then matches the route for the rolled outcome tier, applies
    that route's consequence (authored or synthetic fallback) via
    ``apply_resolution``, and advances ``current_node`` or completes the run
    (terminal route). Emits and returns the :class:`MissionDeedRecord`
    (moral consequence follows the actor).

    When ``advance=False`` (Phase-5a I-1, the routing-free check primitive):
    the check + per-act consequence application happens and the deed is
    emitted exactly as ``advance=True``, but NO routing / terminal write
    occurs (``instance.current_node`` / ``status`` / ``completed_at`` are
    left untouched). The Phase-4 JOINT orchestrator uses this so that no
    per-attempt write ever transiently routes/terminates the instance
    mid-loop; the single combined decision is the only thing that routes.

    M1: writes ``current_node`` but never reads a stale cached one.
    """
    character = actor.character

    if option.option_kind == OptionKind.BRANCH:
        return _resolve_branch(instance, node, option, character, advance=advance)

    # OptionKind.CHECK
    if option.source_kind == OptionSource.CHALLENGE:
        # The chosen ChallengeApproach supplies the check; the challenge's
        # severity is the difficulty. Routing below is unchanged — it keys
        # on the resulting CheckOutcome exactly like an AUTHORED CHECK.
        result = _resolve_challenge_check(option, character, chosen_approach)
    else:
        check_type = _resolve_check_type(option)
        result = perform_check(
            character,
            check_type,
            target_difficulty=instance.template.risk_tier,
        )

    route = MissionOptionRoute.objects.filter(
        option=option,
        outcome_tier=result.outcome,
    ).first()
    if route is None:
        msg = (
            f"CHECK option {option.pk} has no route for outcome "
            f"{result.outcome!r} — route-set incompleteness (graph-level "
            f"authoring error)."
        )
        raise ValueError(msg)

    consequence = _select_route_consequence(route, result)
    context = ResolutionContext(character=character)
    apply_resolution(PendingResolution(result, consequence), context)

    is_terminal = False
    if advance:
        next_node = _route_next_node(route)
        if next_node is None:
            _finish_terminal(instance)
            is_terminal = True
        else:
            instance.current_node = next_node
            instance.save()

    deed = MissionDeedRecord.objects.create(
        instance=instance,
        actor=character,
        node=node,
        option=option,
        outcome=result.outcome,
    )
    if is_terminal:
        # Phase 5b.0: emit authored reward lines from MissionOptionRouteReward
        # rows attached to this terminal route. Non-terminal routes still
        # emit no reward lines (the gate is the local is_terminal flag, set
        # ABOVE the deed.create — _finish_terminal runs before the deed
        # exists, so capture it locally and act after).
        emit_terminal_rewards(instance, route, deed)
    return deed


def _resolve_branch(
    instance: MissionInstance,
    node: MissionNode,
    option: MissionOption,
    character: ObjectDB,
    *,
    advance: bool,
) -> MissionDeedRecord:
    """BRANCH path: no check. Destination is ``option.branch_target`` or the
    option's single null-``outcome_tier`` route's target. Null = terminal.
    Deed ``outcome`` is None (no dice).

    Honors the routing-free ``advance=False`` mode: the deed is still
    emitted but the instance position/status is not touched."""
    is_terminal = False
    terminal_route: MissionOptionRoute | None = None
    if advance:
        next_node: MissionNode | None
        route: MissionOptionRoute | None = None
        if option.branch_target_id is not None:
            next_node = option.branch_target
        else:
            route = MissionOptionRoute.objects.filter(
                option=option,
                outcome_tier__isnull=True,
            ).first()
            next_node = _route_next_node(route) if route is not None else None

        if next_node is None:
            _finish_terminal(instance)
            is_terminal = True
            terminal_route = route  # may be None when branch is terminal via
            # an option with neither branch_target nor a null-tier route.
        else:
            instance.current_node = next_node
            instance.save()

    deed = MissionDeedRecord.objects.create(
        instance=instance,
        actor=character,
        node=node,
        option=option,
        outcome=None,
    )
    if is_terminal and terminal_route is not None:
        # Phase 5b.0: emit authored reward lines. A BRANCH option that
        # terminates without an authored route (no branch_target AND no
        # null-tier route) has no MissionOptionRoute to author rewards on
        # — there is simply nowhere for the author to attach reward
        # templates, so we skip emission cleanly. Templates intentionally
        # live on MissionOptionRoute rows; an authored terminal needs an
        # explicit null-target route.
        emit_terminal_rewards(instance, terminal_route, deed)
    return deed
