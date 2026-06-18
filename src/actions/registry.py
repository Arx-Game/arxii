"""Action registry — lookup actions by key or by target type."""

from __future__ import annotations

from actions.base import Action
from actions.definitions.communication import (
    MutterAction,
    PemitAction,
    PoseAction,
    SayAction,
    WhisperAction,
)
from actions.definitions.duels import (
    AcceptChallengeAction,
    AcknowledgeRiskAction,
    ChallengeAction,
    DeclineChallengeAction,
    WithdrawChallengeAction,
    YieldAction,
)
from actions.definitions.fashion import JudgePresentationAction, PresentOutfitAction
from actions.definitions.investigation import SearchAction
from actions.definitions.items import (
    ActivatePermitAction,
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
from actions.definitions.outfits import ApplyOutfitAction, UndressAction
from actions.definitions.perception import InventoryAction, LookAction, LookAtItemAction
from actions.definitions.positioning import MoveToPositionAction
from actions.definitions.rounds import (
    EndRoundAction,
    ForceResolveRoundAction,
    JoinRoundAction,
    LeaveRoundAction,
    PassRoundAction,
    StartRoundAction,
)
from actions.definitions.social import (
    deceive,
    entrance,
    flirt,
    intimidate,
    perform,
    persuade,
)
from actions.definitions.traps import DisarmTrapAction
from actions.types import TargetType

# All base action instances. Each is a singleton — actions are stateless.
# Social singletons are plain classes (not Action subclasses) but share the same interface.
_ALL_ACTIONS: list[Action] = [  # type: ignore[list-item]
    LookAction(),
    LookAtItemAction(),
    InventoryAction(),
    SearchAction(),
    SayAction(),
    PoseAction(),
    WhisperAction(),
    MutterAction(),
    PemitAction(),
    GetAction(),
    DropAction(),
    GiveAction(),
    EquipAction(),
    UnequipAction(),
    PutInAction(),
    TakeOutAction(),
    ActivatePermitAction(),
    ApplyOutfitAction(),
    UndressAction(),
    PresentOutfitAction(),
    JudgePresentationAction(),
    TraverseExitAction(),
    HomeAction(),
    MoveToPositionAction(),
    StartRoundAction(),
    JoinRoundAction(),
    LeaveRoundAction(),
    EndRoundAction(),
    DisarmTrapAction(),
    PassRoundAction(),
    ForceResolveRoundAction(),
    ChallengeAction(),
    AcceptChallengeAction(),
    DeclineChallengeAction(),
    WithdrawChallengeAction(),
    YieldAction(),
    AcknowledgeRiskAction(),
    intimidate,
    persuade,
    deceive,
    flirt,
    perform,
    entrance,
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
