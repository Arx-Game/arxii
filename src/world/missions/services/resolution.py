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
  * difficulty for every CHECK is ``instance.template.risk_tier`` (the only
    authored DC); ``base_risk`` is the surfaced "Risk" axis, never the DC.
  * a route's authored ``consequence`` is applied when set; otherwise a
    synthetic UNSAVED fallback ``Consequence`` is built so
    ``apply_resolution`` is still called uniformly (and returns [] for the
    unsaved row — mirrors ``challenge_resolution._select_consequence``).
  * riders compose ADDITIVELY (a second ``apply_resolution`` call), never by
    precedence, and only when the node permits them.
  * M1: never trust a possibly-stale cached ``instance.current_node``; engine
    functions operate on the ``node`` argument and write (not read) the FK.
  * NO ``MissionDeedRewardLine`` rows are emitted — reward-line authoring is
    deferred to Phase 5. A terminal deed with zero reward lines is valid.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.checks.consequence_resolution import apply_resolution
from world.checks.models import Consequence
from world.checks.outcome_utils import select_weighted
from world.checks.services import perform_check
from world.checks.types import PendingResolution, ResolutionContext
from world.missions.constants import MissionStatus, OptionKind, OptionSource
from world.missions.models import (
    MissionDeedRecord,
    MissionNodeSnapshot,
    MissionOptionRoute,
)
from world.missions.predicates import CharacterPredicateContext, evaluate
from world.missions.services.affordances import bindings_for_character
from world.missions.types import PresentedOption

if TYPE_CHECKING:
    from collections.abc import Iterable

    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.checks.types import CheckResult
    from world.missions.models import (
        AffordanceBinding,
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


def build_option_list(
    instance: MissionInstance,  # noqa: ARG001 — part of the stable engine signature; Phase 4 unions across the instance's participants
    node: MissionNode,
    viewer: MissionParticipant,
) -> list[PresentedOption]:
    """Surface the options the acting ``viewer`` can take at ``node``.

    For each :class:`MissionOption` on ``node``:

      * AFFORDANCE source — fans out via
        :func:`bindings_for_character` over the option's accepted
        affordances; each resolved binding becomes one ``PresentedOption``.
      * AUTHORED source — included iff its ``visibility_rule`` predicate
        passes for the viewer's character.

    Merge is additive (no arbitration — the player picks later). Order is
    deterministic: option ``order``, then affordance name + binding pk for
    fanned-out affordance entries (the order
    :func:`bindings_for_character` already returns them in).

    Phase 3 is single-participant; ``instance`` is accepted for signature
    stability (Phase 4 unions across ``instance.participants``).
    """
    options = node.options.all().order_by("order", "pk")
    return present_options_for_character(viewer.character, options)


def present_options_for_character(
    character: ObjectDB,
    options: Iterable[MissionOption],
) -> list[PresentedOption]:
    """Present an already-ordered ``options`` iterable for one character.

    The single-participant body of :func:`build_option_list`, extracted so
    Phase-4 ``build_group_option_list`` can fetch the node's options +
    ``accepted_affordances`` ONCE (one prefetched queryset) and reuse them
    across every participant instead of re-querying per participant
    (Phase-3 review Minor-1). ``options`` MUST already be ordered by the
    caller (``order``, then ``pk``) — this preserves
    :func:`build_option_list`'s exact behavior; it just no longer owns the
    queryset construction.
    """
    presented: list[PresentedOption] = []
    for option in options:
        if option.source_kind == OptionSource.AFFORDANCE:
            accepted = set(option.accepted_affordances_cached)
            presented.extend(
                PresentedOption(
                    option=option,
                    kind=option.option_kind,
                    check_type=resolved.check_type,
                    base_risk=resolved.base_risk,
                    ic_framing=resolved.ic_framing,
                    owner=character,
                    binding=resolved.binding,
                )
                for resolved in bindings_for_character(character, accepted)
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
                    binding=None,
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


def _resolve_check_type(
    option: MissionOption,
    chosen_binding: AffordanceBinding | None,
) -> CheckType:
    """The CheckType for a CHECK option: binding's else authored.

    Raises ``ValueError`` when neither is set — a CHECK option that resolves
    no check is an authoring/configuration error, not a runtime branch.
    """
    if chosen_binding is not None and chosen_binding.check_type_id is not None:
        return chosen_binding.check_type
    if option.authored_check_type_id is not None:
        return option.authored_check_type
    raise ValueError(_ERR_CHECK_NO_TYPE.format(option_pk=option.pk))


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


def _rider_permitted(
    node: MissionNode,
    chosen_binding: AffordanceBinding | None,
) -> bool:
    """A binding rider attaches only when the node allows it (§6)."""
    if chosen_binding is None or chosen_binding.rider_id is None:
        return False
    if node.deny_all_riders:
        return False
    return node.allowed_riders.filter(pk=chosen_binding.rider_id).exists()


def _finish_terminal(instance: MissionInstance) -> None:
    """Mark the run complete (terminal route reached)."""
    instance.status = MissionStatus.COMPLETE
    instance.completed_at = timezone.now()
    instance.current_node = None
    instance.save()


def resolve_option(
    instance: MissionInstance,
    node: MissionNode,
    option: MissionOption,
    actor: MissionParticipant,
    chosen_binding: AffordanceBinding | None,
) -> MissionDeedRecord:
    """Resolve ``actor`` taking ``option`` at ``node``; return its deed.

    BRANCH options route the graph with no dice. CHECK options roll
    ``perform_check`` (difficulty = ``instance.template.risk_tier``), match
    the route for the rolled outcome tier, apply that route's consequence
    (authored or synthetic fallback) via ``apply_resolution``, then
    additively apply a permitted binding rider as a SECOND
    ``apply_resolution`` call. Either kind then advances ``current_node`` or
    completes the run (terminal route). Emits and returns the
    :class:`MissionDeedRecord` (consequence follows the actor).

    M1: writes ``current_node`` but never reads a stale cached one.
    """
    character = actor.character

    if option.option_kind == OptionKind.BRANCH:
        return _resolve_branch(instance, node, option, character)

    # OptionKind.CHECK
    check_type = _resolve_check_type(option, chosen_binding)
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

    if _rider_permitted(node, chosen_binding):
        apply_resolution(
            PendingResolution(result, chosen_binding.rider),
            ResolutionContext(character=character),
        )

    next_node = _route_next_node(route)
    if next_node is None:
        _finish_terminal(instance)
    else:
        instance.current_node = next_node
        instance.save()

    return MissionDeedRecord.objects.create(
        instance=instance,
        actor=character,
        node=node,
        option=option,
        outcome=result.outcome,
    )


def _resolve_branch(
    instance: MissionInstance,
    node: MissionNode,
    option: MissionOption,
    character: ObjectDB,
) -> MissionDeedRecord:
    """BRANCH path: no check. Destination is ``option.branch_target`` or the
    option's single null-``outcome_tier`` route's target. Null = terminal.
    Deed ``outcome`` is None (no dice)."""
    next_node: MissionNode | None
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
    else:
        instance.current_node = next_node
        instance.save()

    return MissionDeedRecord.objects.create(
        instance=instance,
        actor=character,
        node=node,
        option=option,
        outcome=None,
    )
