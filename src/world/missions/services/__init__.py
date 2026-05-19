"""Missions service layer.

Public surface:
  * :func:`bindings_for_character` (Phase 1) — authored-once affordance
    bindings → the concrete options an acting character can take.
  * :func:`validate_mission_option` (Phase 2) — post-save graph invariants.
  * :func:`build_option_list`, :func:`enter_node`, :func:`resolve_option`
    (Phase 3) — the runtime resolution engine.
"""

from world.missions.services.affordances import bindings_for_character
from world.missions.services.mission_graph import validate_mission_option
from world.missions.services.resolution import (
    build_option_list,
    enter_node,
    resolve_option,
)

__all__ = [
    "bindings_for_character",
    "build_option_list",
    "enter_node",
    "resolve_option",
    "validate_mission_option",
]
