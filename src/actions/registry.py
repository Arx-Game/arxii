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
from actions.definitions.imbue import ImbueAction
from actions.definitions.investigation import SearchAction
from actions.definitions.items import (
    ActivatePermitAction,
    EquipAction,
    PutInAction,
    TakeOutAction,
    UnequipAction,
    UseItemAction,
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
from actions.definitions.positioning import MoveToPositionAction, SetTheStageAction
from actions.definitions.pull import PullThreadAction
from actions.definitions.ritual import PerformRitualAction
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
    resolve_entry_flourish,
    restore_sense,
)
from actions.definitions.threads import WeaveThreadAction
from actions.definitions.traps import DisarmTrapAction
from actions.types import TargetType

# All base action instances. Each is a singleton — actions are stateless.
_ALL_ACTIONS: list[Action] = [
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
    UseItemAction(),
    ApplyOutfitAction(),
    UndressAction(),
    PresentOutfitAction(),
    JudgePresentationAction(),
    TraverseExitAction(),
    HomeAction(),
    MoveToPositionAction(),
    SetTheStageAction(),
    PerformRitualAction(),
    ImbueAction(),
    PullThreadAction(),
    WeaveThreadAction(),
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
    restore_sense,
    resolve_entry_flourish,
]

# Lookup by key
ACTIONS_BY_KEY: dict[str, Action] = {a.key: a for a in _ALL_ACTIONS}

# Lookup by target type — actions that could apply to this type of target
ACTIONS_BY_TARGET_TYPE: dict[TargetType, list[Action]] = {}
for _action in _ALL_ACTIONS:
    ACTIONS_BY_TARGET_TYPE.setdefault(_action.target_type, []).append(_action)

# Social ActionTemplate-backed singletons indexed by their ``template_name``.
# An ActionTemplate has only a unique ``name`` (no key/slug column), so the scene
# layer uses this map to translate a template name back to its registry action —
# both to derive the dispatch ``action_key`` (#1172: "Restore to Sense" → the
# "restore_sense" key, which a naive ``name.lower()`` would mangle) and to resolve
# the ActionTemplate for a consent request.
SOCIAL_ACTIONS_BY_TEMPLATE_NAME: dict[str, Action] = {
    a.template_name: a
    for a in (intimidate, persuade, deceive, flirt, perform, entrance, restore_sense)
}


def get_action(key: str) -> Action | None:
    """Look up an action by its key."""
    return ACTIONS_BY_KEY.get(key)


def get_actions_for_target_type(target_type: TargetType) -> list[Action]:
    """Return all actions that operate on the given target type."""
    return list(ACTIONS_BY_TARGET_TYPE.get(target_type, []))
