"""Missions service layer.

Public surface:
  * :func:`bindings_for_character` (Phase 1) — authored-once affordance
    bindings → the concrete options an acting character can take.
  * :func:`validate_mission_option` (Phase 2) — post-save graph invariants.
  * :func:`build_option_list`, :func:`enter_node`, :func:`resolve_option`
    (Phase 3) — the runtime resolution engine.
  * :func:`build_group_option_list`, :func:`select_group_choice`,
    :func:`group_resolve_node`, :func:`contract_holder` (Phase 4) — the
    multi-participant orchestrator (reuses Phase-3 ``resolve_option``).
  * :func:`offer_missions` (Phase 5a) — front-door availability pipeline.
  * :func:`accept_mission`, :func:`share_mission` (Phase 5a) — mission-run
    lifecycle entry points.
  * :func:`journal_for` (Phase 5a) — per-character journal read.
  * :func:`emit_terminal_rewards` (Phase 5b.0) — terminal-route reward-line
    emission from authored ``MissionOptionRouteReward`` rows.
  * :func:`apply_deed_rewards` (Phase 5b.1) — routes already-emitted reward
    lines downstream (queue rows for deferred payout, stub-seam calls for
    money/beat, and DESIGN-sealed raises for rumor/crime-watch).
  * :func:`apply_mission_reward_batch` (Phase 5b.2) — cron batch that
    walks ``applied=False`` :class:`MissionRewardQueue` rows. Both
    LP/Resonance grant helpers are stub-sealed in 5b.2 pending
    payload-enrichment work (DESIGN §13.3).
"""

from world.missions.services.affordances import bindings_for_character
from world.missions.services.availability import offer_missions
from world.missions.services.cron import apply_mission_reward_batch
from world.missions.services.journal import journal_for
from world.missions.services.mission_graph import validate_mission_option
from world.missions.services.multiplayer import (
    build_group_option_list,
    contract_holder,
    group_resolve_node,
    select_group_choice,
)
from world.missions.services.resolution import (
    build_option_list,
    enter_node,
    resolve_option,
)
from world.missions.services.rewards import (
    MissionRewardRoutingError,
    apply_deed_rewards,
    emit_terminal_rewards,
)
from world.missions.services.run import accept_mission, share_mission

__all__ = [
    "MissionRewardRoutingError",
    "accept_mission",
    "apply_deed_rewards",
    "apply_mission_reward_batch",
    "bindings_for_character",
    "build_group_option_list",
    "build_option_list",
    "contract_holder",
    "emit_terminal_rewards",
    "enter_node",
    "group_resolve_node",
    "journal_for",
    "offer_missions",
    "resolve_option",
    "select_group_choice",
    "share_mission",
    "validate_mission_option",
]
