"""Action registry — lookup actions by key or by target type."""

from __future__ import annotations

from actions.base import Action
from actions.definitions.communication import PoseAction, SayAction, WhisperAction
from actions.definitions.items import (
    EquipAction,
    PutInAction,
    TakeOutAction,
    UnequipAction,
)
from actions.definitions.movement import (
    DropAction,
    GetAction,
    GiveAction,
    HomeAction,
    TraverseExitAction,
)
from actions.definitions.perception import InventoryAction, LookAction
from actions.types import TargetType

# All base action instances. Each is a singleton — actions are stateless.
_ALL_ACTIONS: list[Action] = [
    LookAction(),
    InventoryAction(),
    SayAction(),
    PoseAction(),
    WhisperAction(),
    GetAction(),
    DropAction(),
    GiveAction(),
    EquipAction(),
    UnequipAction(),
    PutInAction(),
    TakeOutAction(),
    TraverseExitAction(),
    HomeAction(),
]

# Lookup by key
ACTIONS_BY_KEY: dict[str, Action] = {a.key: a for a in _ALL_ACTIONS}

# Lookup by target type — actions that could apply to this type of target
ACTIONS_BY_TARGET_TYPE: dict[TargetType, list[Action]] = {}
for _action in _ALL_ACTIONS:
    ACTIONS_BY_TARGET_TYPE.setdefault(_action.target_type, []).append(_action)


def get_action(key: str) -> Action | None:
    """Look up an action by its key."""
    return ACTIONS_BY_KEY.get(key)


def get_actions_for_target_type(target_type: TargetType) -> list[Action]:
    """Return all actions that operate on the given target type."""
    return list(ACTIONS_BY_TARGET_TYPE.get(target_type, []))
