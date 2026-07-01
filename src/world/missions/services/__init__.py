"""Missions service layer.

Public surface:
  * :func:`validate_mission_option` (Phase 2) — post-save graph invariants.
  * :func:`build_option_list`, :func:`enter_node`, :func:`resolve_option`
    (Phase 3) — the runtime resolution engine. A CHALLENGE-sourced option
    fans out per qualifying ``ChallengeApproach`` via
    :func:`world.missions.services.challenge_options.challenge_options_for_character`.
  * :func:`build_group_option_list`, :func:`resolve_group_node`,
    :func:`contract_holder` (Phase 4 / #1036) — the multi-participant
    orchestrator (reuses Phase-3 ``resolve_option``); GROUP_VOTE resolves the
    two-stage ballot, JOINT runs every pick.
  * :func:`share_mission` (Phase 5a) — adds a non-contract-holder
    participant. Mission acceptance now flows through the unified
    NPCServiceOffer framework's MISSION effect handler (`issue_mission`
    in ``world.missions.services.offer_handler``) per #686.
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
  * :func:`on_mission_complete_for_beat` (Phase 5b.3 / #1747) — Mission→Beat
    seam called at terminal. Completes the linked ``Beat`` via
    ``record_outcome_tier_completion`` (graded tier) or
    ``record_gm_marked_outcome(SUCCESS)`` (BRANCH terminal). Free-run
    instances (``source_beat=None``) are a no-op.
"""

from world.missions.services.beat import on_mission_complete_for_beat
from world.missions.services.cron import apply_mission_reward_batch
from world.missions.services.journal import journal_for
from world.missions.services.mission_graph import validate_mission_option
from world.missions.services.multiplayer import (
    build_group_option_list,
    contract_holder,
    resolve_group_node,
)
from world.missions.services.play import beat_for, resolve_beat_option
from world.missions.services.resolution import (
    build_option_list,
    enter_node,
    resolve_option,
)
from world.missions.services.rewards import (
    MissionRewardRoutingError,
    apply_deed_rewards,
    emit_candidate_rewards,
    emit_terminal_rewards,
)
from world.missions.services.run import share_mission, staff_assign_mission

__all__ = [
    "MissionRewardRoutingError",
    "apply_deed_rewards",
    "apply_mission_reward_batch",
    "beat_for",
    "build_group_option_list",
    "build_option_list",
    "contract_holder",
    "emit_candidate_rewards",
    "emit_terminal_rewards",
    "enter_node",
    "journal_for",
    "on_mission_complete_for_beat",
    "resolve_beat_option",
    "resolve_group_node",
    "resolve_option",
    "share_mission",
    "staff_assign_mission",
    "validate_mission_option",
]
