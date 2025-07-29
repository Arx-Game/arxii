"""Test package granting a strength bonus."""

from behaviors.models import BehaviorPackageInstance
from flows.object_states.base_state import BaseState


def initialize_state(state: BaseState, pkg: BehaviorPackageInstance) -> None:
    state.set_attribute("bonus", pkg.data.get("bonus", 0))


def modify_strength(state: BaseState, pkg: BehaviorPackageInstance, value: int) -> int:
    return value + state.get_attribute("bonus", 0)
