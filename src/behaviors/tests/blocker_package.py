"""Test package that blocks traversal."""

from behaviors.models import BehaviorPackageInstance
from flows.object_states.base_state import BaseState


def can_traverse(
    state: BaseState, pkg: BehaviorPackageInstance, actor: BaseState | None
) -> bool:
    return False


hooks = {
    "can_traverse": can_traverse,
}
