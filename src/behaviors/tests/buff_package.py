"""Test package granting a strength bonus."""

from behaviors.models import BehaviorPackageInstance
from flows.object_states.base_state import BaseState


def initialize_state(state: BaseState, pkg: BehaviorPackageInstance) -> None:
    state.bonus = pkg.data.get("bonus", 0)


def modify_strength(state: BaseState, pkg: BehaviorPackageInstance, value: int) -> int:
    return value + state.bonus


hooks = {
    "initialize_state": initialize_state,
    "modify_strength": modify_strength,
}
