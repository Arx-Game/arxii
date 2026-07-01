"""Action registry — lookup actions by key or by target type."""

from __future__ import annotations

from actions.base import Action
from actions.definitions.alterations import ResolveAlterationAction
from actions.definitions.battles import (
    BeginBattleRoundAction,
    ConcludeBattleAction,
    DeclareBattleActionAction,
    ResolveBattleRoundAction,
)
from actions.definitions.cast import CastTechniqueAction
from actions.definitions.combat_maneuvers import (
    CoverAction,
    FleeAction,
    InterposeAction,
    JoinEncounterAction,
    LeaveEncounterAction,
    ReadyAction,
    RevertComboAction,
    SuccorAction,
    UpgradeComboAction,
)
from actions.definitions.communication import (
    EmitAction,
    MutterAction,
    PemitAction,
    PoseAction,
    SayAction,
    WhisperAction,
)
from actions.definitions.conditions import treat_condition
from actions.definitions.consent_preferences import (
    AddSocialConsentBlacklistAction,
    AddSocialConsentWhitelistAction,
    RemoveSocialConsentBlacklistAction,
    RemoveSocialConsentWhitelistAction,
    SetSocialConsentCategoryRuleAction,
    SetSocialConsentPreferenceAction,
)
from actions.definitions.covenants import (
    AssignCovenantRankAction,
    DisengageCovenantMembershipAction,
    EngageCovenantMembershipAction,
    KickCovenantMemberAction,
    LeaveCovenantAction,
    StandDownBattleCovenantAction,
    TransferTopRankAction,
)
from actions.definitions.deeds import SaveDeedStoryAction, SpreadTaleAction
from actions.definitions.duels import (
    AcceptChallengeAction,
    AcknowledgeRiskAction,
    ChallengeAction,
    DeclineChallengeAction,
    WithdrawChallengeAction,
    YieldAction,
)
from actions.definitions.endorsements import (
    PoseEndorseAction,
    SceneEntryEndorseAction,
    StylePresentationEndorseAction,
)
from actions.definitions.events import (
    CancelEventAction,
    CompleteEventAction,
    CreateEventAction,
    InviteToEventAction,
    RespondInvitationAction,
    ScheduleEventAction,
    StartEventAction,
)
from actions.definitions.fashion import JudgePresentationAction, PresentOutfitAction
from actions.definitions.fatigue import RestAction
from actions.definitions.forms import RevertFormAction, ShiftFormAction
from actions.definitions.gm_combat import (
    AddEncounterParticipantAction,
    AddOpponentAction,
    BeginEncounterRoundAction,
    EndEncounterAction,
    PauseEncounterAction,
    PreviewOpponentDefaultsAction,
    RemoveEncounterParticipantAction,
    ResolveEncounterRoundAction,
)
from actions.definitions.gm_stories import (
    CompleteStoryAction,
    MarkBeatAction,
    PromoteEpisodeAction,
    ResolveEpisodeAction,
)
from actions.definitions.goals import LogGoalProgressAction, SetCharacterGoalsAction
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
from actions.definitions.journals import (
    CreateJournalEntryAction,
    EditJournalEntryAction,
    RespondToJournalAction,
)
from actions.definitions.locations import RoomEditAction
from actions.definitions.movement import (
    DropAction,
    GetAction,
    GiveAction,
    HomeAction,
    TraverseExitAction,
)
from actions.definitions.npc_services import (
    end_npc_interaction,
    resolve_npc_offer,
    start_npc_interaction,
)
from actions.definitions.organizations import (
    org_apply_action,
    org_demote_action,
    org_expel_action,
    org_invite_action,
    org_join_action,
    org_leave_action,
    org_promote_action,
)
from actions.definitions.outfits import ApplyOutfitAction, UndressAction
from actions.definitions.perception import InventoryAction, LookAction, LookAtItemAction
from actions.definitions.personas import SetActivePersonaAction
from actions.definitions.positioning import MoveToPositionAction, SetTheStageAction
from actions.definitions.progression import ManageTrainingAction, PurchaseUnlockAction
from actions.definitions.progression_rewards import (
    CastVoteAction,
    ClaimKudosAction,
    ClaimRandomSceneAction,
    ClearPathIntentAction,
    RemoveVoteAction,
    RerollRandomSceneAction,
    SetPathIntentAction,
)
from actions.definitions.projects import (
    CheckContributeAction,
    DonateToProjectAction,
    StoryContributeAction,
)
from actions.definitions.relationships import (
    CreateCapstoneAction,
    CreateDevelopmentAction,
    CreateFirstImpressionAction,
    FileWriteupComplaintAction,
    GiveWriteupKudosAction,
    RedistributePointsAction,
)
from actions.definitions.ritual import PerformRitualAction
from actions.definitions.rounds import (
    EndRoundAction,
    ForceResolveRoundAction,
    JoinRoundAction,
    LeaveRoundAction,
    PassRoundAction,
    SetRoundModeAction,
    StartRoundAction,
    SuccorSceneAction,
)
from actions.definitions.sanctum import (
    SanctumAbsorbAction,
    SanctumDissolveAction,
    SanctumHomecomingAction,
    SanctumInstallAction,
    SanctumPurgingAction,
    SanctumSeverAction,
    SanctumWeaveAction,
)
from actions.definitions.scene_reactions import (
    ReactToWindowAction,
    ToggleFavoriteAction,
    ToggleReactionAction,
)
from actions.definitions.scenes import FinishSceneAction, StartSceneAction
from actions.definitions.signature import (
    SignatureClearAction,
    SignatureListAction,
    SignatureSetAction,
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
    seduce,
)
from actions.definitions.technique_authoring import AuthorTechniqueAction
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
    EmitAction(),
    WhisperAction(),
    MutterAction(),
    PemitAction(),
    GetAction(),
    DropAction(),
    GiveAction(),
    EquipAction(),
    UnequipAction(),
    RoomEditAction(),
    DonateToProjectAction(),
    CheckContributeAction(),
    StoryContributeAction(),
    SetActivePersonaAction(),
    ShiftFormAction(),
    RevertFormAction(),
    SetSocialConsentPreferenceAction(),
    SetSocialConsentCategoryRuleAction(),
    AddSocialConsentWhitelistAction(),
    RemoveSocialConsentWhitelistAction(),
    AddSocialConsentBlacklistAction(),
    RemoveSocialConsentBlacklistAction(),
    SpreadTaleAction(),
    SaveDeedStoryAction(),
    PutInAction(),
    TakeOutAction(),
    ActivatePermitAction(),
    UseItemAction(),
    ApplyOutfitAction(),
    UndressAction(),
    PresentOutfitAction(),
    JudgePresentationAction(),
    PoseEndorseAction(),
    SceneEntryEndorseAction(),
    StylePresentationEndorseAction(),
    TraverseExitAction(),
    HomeAction(),
    MoveToPositionAction(),
    SetTheStageAction(),
    PerformRitualAction(),
    AuthorTechniqueAction(),
    ImbueAction(),
    WeaveThreadAction(),
    StartRoundAction(),
    JoinRoundAction(),
    LeaveRoundAction(),
    EndRoundAction(),
    DisarmTrapAction(),
    PassRoundAction(),
    ForceResolveRoundAction(),
    SetRoundModeAction(),
    SuccorSceneAction(),
    FleeAction(),
    CoverAction(),
    InterposeAction(),
    SuccorAction(),
    ReadyAction(),
    UpgradeComboAction(),
    RevertComboAction(),
    JoinEncounterAction(),
    LeaveEncounterAction(),
    ChallengeAction(),
    AcceptChallengeAction(),
    DeclineChallengeAction(),
    WithdrawChallengeAction(),
    YieldAction(),
    AcknowledgeRiskAction(),
    CastTechniqueAction(),
    StartSceneAction(),
    FinishSceneAction(),
    BeginEncounterRoundAction(),
    ResolveEncounterRoundAction(),
    AddOpponentAction(),
    AddEncounterParticipantAction(),
    RemoveEncounterParticipantAction(),
    PauseEncounterAction(),
    EndEncounterAction(),
    PreviewOpponentDefaultsAction(),
    CompleteStoryAction(),
    ResolveEpisodeAction(),
    PromoteEpisodeAction(),
    MarkBeatAction(),
    ResolveAlterationAction(),
    RestAction(),
    ToggleFavoriteAction(),
    ToggleReactionAction(),
    ReactToWindowAction(),
    CreateFirstImpressionAction(),
    CreateDevelopmentAction(),
    CreateCapstoneAction(),
    RedistributePointsAction(),
    CreateJournalEntryAction(),
    RespondToJournalAction(),
    EditJournalEntryAction(),
    SetCharacterGoalsAction(),
    LogGoalProgressAction(),
    GiveWriteupKudosAction(),
    FileWriteupComplaintAction(),
    EngageCovenantMembershipAction(),
    DisengageCovenantMembershipAction(),
    LeaveCovenantAction(),
    KickCovenantMemberAction(),
    AssignCovenantRankAction(),
    TransferTopRankAction(),
    StandDownBattleCovenantAction(),
    CreateEventAction(),
    ScheduleEventAction(),
    StartEventAction(),
    CompleteEventAction(),
    CancelEventAction(),
    InviteToEventAction(),
    RespondInvitationAction(),
    ManageTrainingAction(),
    PurchaseUnlockAction(),
    ClaimKudosAction(),
    CastVoteAction(),
    RemoveVoteAction(),
    ClaimRandomSceneAction(),
    RerollRandomSceneAction(),
    SetPathIntentAction(),
    ClearPathIntentAction(),
    start_npc_interaction,
    resolve_npc_offer,
    end_npc_interaction,
    org_invite_action,
    org_apply_action,
    org_join_action,
    org_leave_action,
    org_promote_action,
    org_demote_action,
    org_expel_action,
    intimidate,
    persuade,
    deceive,
    flirt,
    seduce,
    perform,
    entrance,
    restore_sense,
    resolve_entry_flourish,
    treat_condition,
    SanctumInstallAction(),
    SanctumHomecomingAction(),
    SanctumPurgingAction(),
    SanctumWeaveAction(),
    SanctumDissolveAction(),
    SanctumAbsorbAction(),
    SanctumSeverAction(),
    # #1592 — battle system lifecycle: GM verbs + player declare.
    BeginBattleRoundAction(),
    ResolveBattleRoundAction(),
    ConcludeBattleAction(),
    DeclareBattleActionAction(),
    SignatureSetAction(),
    SignatureClearAction(),
    SignatureListAction(),
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
    for a in (intimidate, persuade, deceive, flirt, seduce, perform, entrance, restore_sense)
}


def get_action(key: str) -> Action | None:
    """Look up an action by its key."""
    return ACTIONS_BY_KEY.get(key)


def get_actions_for_target_type(target_type: TargetType) -> list[Action]:
    """Return all actions that operate on the given target type."""
    return list(ACTIONS_BY_TARGET_TYPE.get(target_type, []))
