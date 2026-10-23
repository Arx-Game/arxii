"""Mission Studio graph check: what is wrong with a mission's graph (#4558).

Read-only. The rules mirror what the engine does (``resolution._resolve_branch``,
``_route_graded_outcome``, ``_route_next_node`` and ``multiplayer._combined_route``)
so a problem here is a place a run could dead-end or never reach. Problems warn;
they never block a save. A fixed number of queries however big the graph is.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from world.combat.models import EncounterOutcomeMapping
from world.missions.constants import (
    SUCCESS_TIER_LEVEL,
    ConflictMode,
    GraphProblemKind,
    OptionKind,
)
from world.missions.models import (
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
)
from world.missions.types import GraphProblem
from world.traits.models import CheckOutcome, ResultChartOutcome

if TYPE_CHECKING:
    from world.missions.models import MissionTemplate

_LABEL_FRAMING_MAX = 40
_ROLLED_KINDS = (OptionKind.CHECK, OptionKind.CONTEST)
_BRANCHING_KINDS = (OptionKind.BRANCH, OptionKind.EXTERNAL_ACT)
# Kinds whose roll on a track node is counted toward the track instead of routing.
_TRACK_COUNTED_KINDS = (OptionKind.CHECK, OptionKind.CONTEST)


def option_label(option: MissionOption) -> str:
    """The option's key, else its framing line cut to 40 characters, else its position."""
    if option.key:
        return option.key
    if option.authored_ic_framing:
        return option.authored_ic_framing[:_LABEL_FRAMING_MAX]
    return f"option {option.order}"


def _tier_sort_key(tier: CheckOutcome) -> tuple[int, int]:
    return (int(tier.success_level), tier.pk)


def _graph_edges(
    nodes: list[MissionNode],
    options: list[MissionOption],
    routes: list[MissionOptionRoute],
    candidates: list[MissionOptionRouteCandidate],
) -> dict[int, set[int]]:
    """Node id -> node ids it leads to, over every edge the engine follows."""
    edges: dict[int, set[int]] = defaultdict(set)
    for node in nodes:
        edges[node.pk].update(
            target_id
            for target_id in (node.track_success_target_id, node.track_failure_target_id)
            if target_id is not None
        )
    option_by_pk = {option.pk: option for option in options}
    track_node_pks = {node.pk for node in nodes if node.is_track}
    for option in options:
        if option.branch_target_id is not None:
            edges[option.node_id].add(option.branch_target_id)
    followed: dict[int, int] = {}  # route pk -> the node it leaves from
    for route in routes:
        option = option_by_pk[route.option_id]
        if option.option_kind in _BRANCHING_KINDS and (
            option.branch_target_id is not None or route.outcome_tier_id is not None
        ):
            continue  # the engine reads only a branch option's tier-less route
        if option.node_id in track_node_pks and option.option_kind in _TRACK_COUNTED_KINDS:
            continue  # a counted roll on a track node never routes; the track decides
        followed[route.pk] = option.node_id
        if route.target_node_id is not None:
            edges[option.node_id].add(route.target_node_id)
    for candidate in candidates:
        if candidate.route_id in followed:
            edges[followed[candidate.route_id]].add(candidate.target_node_id)
    return edges


def _reachable_node_ids(
    nodes: list[MissionNode],
    options: list[MissionOption],
    routes: list[MissionOptionRoute],
    candidates: list[MissionOptionRouteCandidate],
) -> set[int]:
    """Node ids reachable from the entry node(s)."""
    edges = _graph_edges(nodes, options, routes, candidates)
    seen = {node.pk for node in nodes if node.is_entry}
    frontier = list(seen)
    while frontier:
        for target_id in edges[frontier.pop()]:
            if target_id not in seen:
                seen.add(target_id)
                frontier.append(target_id)
    return seen


def _mapped_tiers_by_risk() -> dict[str, set[CheckOutcome]]:
    tiers: dict[str, set[CheckOutcome]] = defaultdict(set)
    for mapping in EncounterOutcomeMapping.objects.select_related("check_outcome"):
        tiers[mapping.risk_level].add(mapping.check_outcome)
    return tiers


def _rollable_check_tiers() -> set[CheckOutcome]:
    chart_rows = ResultChartOutcome.objects.select_related("outcome")
    return {row.outcome for row in chart_rows}


def _option_problems(
    option: MissionOption,
    node: MissionNode,
    routes: list[MissionOptionRoute],
    check_tiers: set[CheckOutcome],
    mapped_tiers: dict[str, set[CheckOutcome]],
) -> list[GraphProblem]:
    label = option_label(option)
    tiered = [route for route in routes if route.outcome_tier_id is not None]
    problems: list[GraphProblem] = []
    joint = node.conflict_mode == ConflictMode.JOINT
    if joint and option.option_kind in _BRANCHING_KINDS:
        return [
            GraphProblem(
                kind=GraphProblemKind.JOINT_MISSING_BUCKET,
                message=f'"{label}" is a branch on a joint node, which can\'t decide '
                "where the group goes.",
                node_id=node.pk,
                option_id=option.pk,
            )
        ]
    if joint and option.option_kind in _ROLLED_KINDS and not check_tiers:
        # No chart names a tier, so MISSING_TIERS has nothing to list; the combined
        # result still needs a success route and a failure route.
        levels = [int(route.outcome_tier.success_level) for route in tiered]
        if not (
            any(level >= SUCCESS_TIER_LEVEL for level in levels)
            and any(level < SUCCESS_TIER_LEVEL for level in levels)
        ):
            problems.append(
                GraphProblem(
                    kind=GraphProblemKind.JOINT_MISSING_BUCKET,
                    message=(
                        f'"{label}" is on a joint node, so it needs a route for a '
                        "success and a route for a failure."
                    ),
                    node_id=node.pk,
                    option_id=option.pk,
                )
            )
        return problems
    if option.option_kind in _ROLLED_KINDS:
        rollable = check_tiers
    elif option.option_kind == OptionKind.ENCOUNTER:
        if not option.encounter_risk_level:
            return [
                GraphProblem(
                    kind=GraphProblemKind.NO_RISK_LEVEL,
                    message=f'"{label}" is an encounter with no risk level.',
                    node_id=node.pk,
                    option_id=option.pk,
                )
            ]
        rollable = mapped_tiers.get(option.encounter_risk_level, set())
    else:
        return problems
    have = {route.outcome_tier_id for route in tiered}
    missing = sorted((tier for tier in rollable if tier.pk not in have), key=_tier_sort_key)
    if missing:
        names = [tier.name for tier in missing]
        problems.append(
            GraphProblem(
                kind=GraphProblemKind.MISSING_TIERS,
                message=f'"{label}" has no route for: {", ".join(names)}.',
                node_id=node.pk,
                option_id=option.pk,
                missing_tiers=names,
            )
        )
    return problems


def check_mission_graph(template: MissionTemplate) -> list[GraphProblem]:
    """Every problem in ``template``'s graph: no entry first, then by node, option, route."""
    nodes = list(MissionNode.objects.filter(template=template).order_by("pk"))
    options = list(MissionOption.objects.filter(node__template=template).order_by("node_id", "pk"))
    routes = list(
        MissionOptionRoute.objects.filter(option__node__template=template)
        .select_related("outcome_tier")
        .order_by("pk")
    )
    candidates = list(
        MissionOptionRouteCandidate.objects.filter(route__option__node__template=template).order_by(
            "pk"
        )
    )
    problems: list[GraphProblem] = []
    if not any(node.is_entry for node in nodes):
        problems.append(
            GraphProblem(
                kind=GraphProblemKind.NO_ENTRY,
                message="This mission has no entry node, so nobody can start it.",
                node_id=None,
            )
        )
    else:
        reachable = _reachable_node_ids(nodes, options, routes, candidates)
        problems.extend(
            GraphProblem(
                kind=GraphProblemKind.UNREACHABLE_NODE,
                message=f'Nothing leads to "{node.key}" from the entry node.',
                node_id=node.pk,
            )
            for node in nodes
            if node.pk not in reachable
        )

    routes_by_option: dict[int, list[MissionOptionRoute]] = defaultdict(list)
    for route in routes:
        routes_by_option[route.option_id].append(route)
    candidate_counts: dict[int, int] = defaultdict(int)
    for candidate in candidates:
        candidate_counts[candidate.route_id] += 1
    node_by_pk = {node.pk: node for node in nodes}
    check_tiers = _rollable_check_tiers()
    mapped_tiers = _mapped_tiers_by_risk()
    for option in sorted(options, key=lambda opt: (opt.node_id, opt.pk)):
        node = node_by_pk[option.node_id]
        option_routes = routes_by_option[option.pk]
        problems.extend(_option_problems(option, node, option_routes, check_tiers, mapped_tiers))
        problems.extend(
            GraphProblem(
                kind=GraphProblemKind.EMPTY_RANDOM_SET,
                message=(
                    f'A random route on "{option_label(option)}" has no candidates, '
                    "so the mission ends there."
                ),
                node_id=node.pk,
                option_id=option.pk,
                route_id=route.pk,
            )
            for route in option_routes
            if route.is_random_set and not candidate_counts[route.pk]
        )
    # NO_ENTRY has no node (sorts first); the rest read down the graph in row order.
    problems.sort(key=lambda p: (p.node_id or 0, p.option_id or 0, p.route_id or 0))
    return problems
