"""Test package that blocks traversal."""

from behaviors.models import BehaviorPackageInstance
from flows.object_states.base_state import BaseState


def require_matching_value(
    state: BaseState,
    pkg: BehaviorPackageInstance,
    actor: BaseState | None,
) -> bool:
    return False
