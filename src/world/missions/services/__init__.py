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
"""

from world.missions.services.affordances import bindings_for_character
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

__all__ = [
    "bindings_for_character",
    "build_group_option_list",
    "build_option_list",
    "contract_holder",
    "enter_node",
    "group_resolve_node",
    "resolve_option",
    "select_group_choice",
    "validate_mission_option",
]
