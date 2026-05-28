"""Copy services for the Mission Studio authoring tool (Phase D D4.2).

Three operations:
- ``copy_template`` — duplicate a whole MissionTemplate (including its
  full graph: every node + option + route + candidate + reward). All
  route target_nodes stay internal to the new template (clone-to-clone
  re-pointing). Lands with ``access_tier=STAFF_ONLY`` so the author can
  fix flavor before publishing.
- ``copy_node`` — duplicate a single node within its current template
  (with its options/routes/candidates/rewards). Routes keep their
  original target_node FKs — the copy is "stuck" until the author
  re-wires. Useful for "duplicate this branch's entry point and edit".
- ``copy_subtree`` — duplicate a node + every downstream node reachable
  via route target_node FKs (BFS), all within the same template. All
  routes within the copied closure are re-pointed to the corresponding
  copies. Because the closure is full-reachability, there are no
  "external" routes — every routes' target is also copied. (If you want
  a narrower copy that DOES leave external routes, that's a future
  enhancement; the design called for that escape valve but the
  full-closure semantics make it unnecessary today.)

Every copied flavor field is marked ``needs_rewrite=True`` per design
§10: copy creates an inheritance signal, not a fait accompli.

Atomic — each function runs inside a single transaction so partial
copies never persist.
"""

from __future__ import annotations

from collections import deque

from django.db import transaction

from world.missions.constants import AccessTier
from world.missions.models import (
    MissionNode,
    MissionOption,
    MissionOptionRoute,
    MissionOptionRouteCandidate,
    MissionOptionRouteReward,
    MissionTemplate,
)


def _copy_node_into(
    template: MissionTemplate,
    source: MissionNode,
    new_key: str,
) -> MissionNode:
    """Clone ``source`` into ``template`` with the given key.

    Flavor fields marked needs_rewrite. NOT recursive — only copies the
    node row itself plus its options/routes/candidates/rewards. Caller
    handles target_node re-pointing.
    """
    new_node = MissionNode.objects.create(
        template=template,
        key=new_key,
        is_entry=False,  # copies are never entry nodes — author flips manually
        conflict_mode=source.conflict_mode,
        joint_combine=source.joint_combine,
        joint_count=source.joint_count,
        deny_all_riders=source.deny_all_riders,
        editor_x=source.editor_x,
        editor_y=source.editor_y,
        flavor_text=source.flavor_text,
        flavor_text_needs_rewrite=True,
    )
    new_node.allowed_riders.set(source.allowed_riders.all())
    return new_node


def _copy_option_into(new_node: MissionNode, source_option: MissionOption) -> MissionOption:
    """Clone ``source_option`` onto ``new_node``. Flavor needs_rewrite."""
    return MissionOption.objects.create(
        node=new_node,
        order=source_option.order,
        option_kind=source_option.option_kind,
        source_kind=source_option.source_kind,
        visibility_rule=dict(source_option.visibility_rule or {}),
        authored_check_type=source_option.authored_check_type,
        authored_base_risk=source_option.authored_base_risk,
        authored_ic_framing=source_option.authored_ic_framing,
        authored_ic_framing_needs_rewrite=True,
        branch_target=source_option.branch_target,
        challenge=source_option.challenge,
    )


def _copy_route_into(
    new_option: MissionOption,
    source_route: MissionOptionRoute,
    target_node: MissionNode | None,
    *,
    needs_rewrite: bool,
) -> MissionOptionRoute:
    """Clone a route onto ``new_option`` with the resolved target_node."""
    return MissionOptionRoute.objects.create(
        option=new_option,
        outcome_tier=source_route.outcome_tier,
        target_node=target_node,
        is_random_set=source_route.is_random_set,
        consequence=source_route.consequence,
        outcome_text=source_route.outcome_text,
        outcome_text_needs_rewrite=needs_rewrite,
    )


def _copy_candidates_into(
    new_route: MissionOptionRoute,
    source_route: MissionOptionRoute,
    node_map: dict[int, MissionNode],
) -> None:
    """Clone candidates of ``source_route`` onto ``new_route``.

    Candidate target_node FKs respect the same internal/external rule
    as their parent route — internal targets are re-pointed; external
    targets land null + flagged.
    """
    for cand in source_route.candidates.all():
        if cand.target_node_id and cand.target_node_id in node_map:
            new_target = node_map[cand.target_node_id]
            needs_rewrite = True  # always flag copied candidate text
        else:
            new_target = cand.target_node  # external — keep pointer
            needs_rewrite = True
        MissionOptionRouteCandidate.objects.create(
            route=new_route,
            target_node=new_target,
            weight=cand.weight,
            consequence=cand.consequence,
            outcome_text=cand.outcome_text,
            outcome_text_needs_rewrite=needs_rewrite,
        )


def _copy_rewards_for_route(
    new_route: MissionOptionRoute, source_route: MissionOptionRoute
) -> None:
    """Clone reward lines attached to ``source_route`` onto ``new_route``."""
    for reward in source_route.reward_templates.all():
        MissionOptionRouteReward.objects.create(
            route=new_route,
            candidate=None,
            kind=reward.kind,
            sink=reward.sink,
            amount=reward.amount,
        )


def _copy_options_routes_rewards(
    source_node: MissionNode,
    new_node: MissionNode,
    node_map: dict[int, MissionNode] | None = None,
) -> None:
    """Walk source_node's options/routes/candidates/rewards into new_node.

    ``node_map`` maps {source_node_id: copied_node} so route target_node
    FKs that point into the copied set get re-pointed. When ``node_map``
    is None (single-node copy) routes keep their original target_node
    pointers but are still marked needs_rewrite (the author has to
    re-think the copy).
    """
    for source_option in source_node.options.all():
        new_option = _copy_option_into(new_node, source_option)
        for source_route in source_option.routes.all():
            if node_map and source_route.target_node_id in node_map:
                # Internal target — re-point to the copy.
                new_target = node_map[source_route.target_node_id]
                needs_rewrite = True  # still copied content; flavor flagged
            else:
                # External (or no map) — keep original pointer for now;
                # author can re-wire. Flag it loudly.
                new_target = source_route.target_node
                needs_rewrite = True
            new_route = _copy_route_into(
                new_option,
                source_route,
                new_target,
                needs_rewrite=needs_rewrite,
            )
            _copy_candidates_into(new_route, source_route, node_map or {})
            _copy_rewards_for_route(new_route, source_route)


@transaction.atomic
def copy_template(source: MissionTemplate, *, new_name: str | None = None) -> MissionTemplate:
    """Duplicate a whole template + its graph.

    If ``new_name`` is None, derives one via ``next_available_name`` from
    ``"<source.name> (copy)"``. Caller-provided ``new_name`` is also
    auto-suffixed if it collides — copy never errors on name conflict.
    All routes' target_node FKs stay internal (re-pointed to copies).
    Lands with ``access_tier=STAFF_ONLY`` so the author can fix flavor
    before publishing.
    """
    from django.db import IntegrityError  # noqa: PLC0415

    from world.missions.services.naming import next_available_name  # noqa: PLC0415

    base = new_name if new_name is not None else f"{source.name} (copy)"

    # Build the fields dict once so both INSERT attempts use the same values.
    fields = {
        "summary": source.summary,
        "epilogue": source.epilogue,
        "level_band_min": source.level_band_min,
        "level_band_max": source.level_band_max,
        "risk_tier": source.risk_tier,
        "base_weight": source.base_weight,
        "created_in_era": source.created_in_era,
        "arc_scope": source.arc_scope,
        "percent_replace": source.percent_replace,
        "cooldown": source.cooldown,
        "reward_group_rule": source.reward_group_rule,
        "availability_rule": dict(source.availability_rule or {}),
        "is_active": source.is_active,
        "access_tier": AccessTier.STAFF_ONLY,  # copies always land unpublished
    }

    final_name = next_available_name(base, MissionTemplate.objects.all())
    try:
        with transaction.atomic():  # savepoint so the outer atomic isn't poisoned on failure
            new_template = MissionTemplate.objects.create(name=final_name, **fields)
    except IntegrityError:
        # Concurrent create stole our name between the SELECT and INSERT.
        # Recompute the suffix (now seeing the just-committed row) and retry once.
        final_name = next_available_name(base, MissionTemplate.objects.all())
        new_template = MissionTemplate.objects.create(name=final_name, **fields)
    new_template.categories.set(source.categories.all())
    # First pass — clone every node so the node_map is complete before
    # we wire routes.
    node_map: dict[int, MissionNode] = {}
    for source_node in source.nodes.all():
        new_node = _copy_node_into(new_template, source_node, source_node.key)
        # Preserve is_entry from source for whole-template copy — every
        # template needs exactly one entry node, and the source's was
        # already valid.
        if source_node.is_entry:
            new_node.is_entry = True
            new_node.save(update_fields=["is_entry"])
        node_map[source_node.pk] = new_node
    # Second pass — wire options/routes/candidates/rewards now that we
    # can re-point internal target_node FKs.
    for source_node in source.nodes.all():
        new_node = node_map[source_node.pk]
        _copy_options_routes_rewards(source_node, new_node, node_map)
    return new_template


@transaction.atomic
def copy_node(source: MissionNode, *, new_key: str) -> MissionNode:
    """Duplicate a single node within its current template.

    Options/routes/candidates/rewards copied. Route target_node FKs keep
    pointing at the originals (the copy is "stuck" until the author
    re-wires); routes are flagged needs_rewrite.
    """
    new_node = _copy_node_into(source.template, source, new_key)
    _copy_options_routes_rewards(source, new_node, node_map=None)
    return new_node


def _reachable_closure(source: MissionNode) -> dict[int, MissionNode]:
    """BFS from ``source`` along route + candidate target_node FKs.

    Only follows targets within the same template (defense — the model
    doesn't enforce same-template, but the authoring design assumes it).
    Returns ``{source_pk: node_instance}`` for every reachable node
    including the source itself.
    """
    reachable: dict[int, MissionNode] = {source.pk: source}
    queue: deque[MissionNode] = deque([source])
    while queue:
        node = queue.popleft()
        for option in node.options.all():
            for route in option.routes.all():
                _enqueue_target(route.target_node_id, route.target_node, source, reachable, queue)
                for cand in route.candidates.all():
                    _enqueue_target(cand.target_node_id, cand.target_node, source, reachable, queue)
    return reachable


def _enqueue_target(
    target_id: int | None,
    target: MissionNode | None,
    source: MissionNode,
    reachable: dict[int, MissionNode],
    queue: deque[MissionNode],
) -> None:
    """Add ``target`` to the reachable set + BFS queue if eligible."""
    if not target_id or target_id in reachable or target is None:
        return
    if target.template_id != source.template_id:
        return
    reachable[target_id] = target
    queue.append(target)


@transaction.atomic
def copy_subtree(source: MissionNode, *, new_key_prefix: str) -> MissionNode:
    """Duplicate ``source`` and every downstream node within the same template.

    Reachability is the full BFS closure (see ``_reachable_closure``).
    Routes within the copy are re-pointed to the corresponding copies;
    by definition the closure has no external routes.
    """
    reachable = _reachable_closure(source)
    # First pass — clone every node so the node_map is complete before
    # we wire routes.
    node_map: dict[int, MissionNode] = {}
    for source_pk, src_node in reachable.items():
        new_key = f"{new_key_prefix}-{src_node.key}"
        new_node = _copy_node_into(source.template, src_node, new_key)
        node_map[source_pk] = new_node
    # Second pass — wire options/routes/candidates/rewards.
    for source_pk, src_node in reachable.items():
        _copy_options_routes_rewards(src_node, node_map[source_pk], node_map)
    return node_map[source.pk]
