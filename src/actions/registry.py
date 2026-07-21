"""Action registry — lookup actions by key or by target type."""

from __future__ import annotations

from actions.base import Action
from actions.definitions.accusations import (
    DenounceFramerAction,
    RefuteAccusationAction,
    SmearAction,
    mint_accusation,
)
from actions.definitions.alterations import ResolveAlterationAction
from actions.definitions.assets import IntroduceAssetAction
from actions.definitions.battles import (
    BeginBattleRoundAction,
    BrowseBattleCatalogAction,
    ChallengeChampionDuelAction,
    ConcludeBattleAction,
    CreateBattleAction,
    DeclareBattleActionAction,
    EnlistBattleParticipantAction,
    JoinPlaceEncounterAction,
    OpenPlaceEncounterAction,
    ResolveBattleRoundAction,
    SpawnBattleUnitsAction,
    StageBattleMapAction,
)
from actions.definitions.cast import CastTechniqueAction
from actions.definitions.ceremonies import (
    AbandonCeremonyAction,
    CeremonyOfferingAction,
    CeremonySpeechAction,
    FinishCeremonyAction,
    OpenCeremonyAction,
    RespondSeanceOfferAction,
)
from actions.definitions.charm_asset import CharmAssetAction
from actions.definitions.coercion import coerce, reveal_secret
from actions.definitions.collect_food import CollectFoodAction
from actions.definitions.combat_maneuvers import (
    ChargeAction,
    CoverAction,
    DemoralizeAction,
    DisengageAction,
    EngageAction,
    FleeAction,
    InterposeAction,
    JoinEncounterAction,
    JoustAction,
    LeaveEncounterAction,
    ParleyAction,
    RallyAction,
    ReadyAction,
    RevertComboAction,
    SuccorAction,
    TauntAction,
    UpgradeComboAction,
    UseItemManeuverAction,
)
from actions.definitions.communication import (
    EmitAction,
    MutterAction,
    PemitAction,
    PoseAction,
    SayAction,
    WhisperAction,
)
from actions.definitions.companions import (
    BindCompanionAction,
    CompanionFightAction,
    DeployCompanionAction,
    DismountCompanionAction,
    MountCompanionAction,
    OrderCompanionAction,
    PromoteSummonAction,
    ReleaseCompanionAction,
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
from actions.definitions.crafting import (
    AttachFacetAction,
    AttachStyleAction,
    CreateItemAction,
    DetachFacetAction,
)
from actions.definitions.crossing import resolve_crossing_offer
from actions.definitions.currency import DepositCoinsAction, GiveCoinsAction, WithdrawCoinsAction
from actions.definitions.deeds import SaveDeedStoryAction, SpreadTaleAction
from actions.definitions.distinctions import (
    AcceptDistinctionChangeAction,
    AuthorizeDistinctionChangeAction,
    GMAwardDistinctionAction,
)
from actions.definitions.domains import (
    AddDomainHoldingAction,
    AppointDomainOfficeAction,
    StartDomainImprovementAction,
    TransferFoodAction,
    VacateDomainOfficeAction,
)
from actions.definitions.doors import BreakExitAction, LockAction, PickLockAction, UnlockAction
from actions.definitions.dramatic_moments import (
    ConfirmDramaticMomentSuggestionAction,
    DismissDramaticMomentSuggestionAction,
)
from actions.definitions.dreams import (
    AscendAction,
    DescendAction,
    DreamwalkAction,
    SleepAction,
)
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
from actions.definitions.estates import WillReadingAction
from actions.definitions.events import (
    CancelEventAction,
    CompleteEventAction,
    CreateEventAction,
    InviteToEventAction,
    RespondInvitationAction,
    ScheduleEventAction,
    StartEventAction,
)
from actions.definitions.evidence import (
    DisposeEvidenceAction,
    ExamineEvidenceAction,
    GatherEvidenceAction,
    ProduceCaseEvidenceAction,
    StartFrameJobAction,
)
from actions.definitions.fashion import JudgePresentationAction, PresentOutfitAction
from actions.definitions.fatigue import RestAction
from actions.definitions.forms import RevertFormAction, ShiftFormAction
from actions.definitions.gift_acquisition import (
    AcceptTechniqueOfferAction,
    AcceptThreadWeavingOfferAction,
    PurchaseGiftUnlockAction,
)
from actions.definitions.gm_adjudication import (
    GMApplyConditionAction,
    GMAwardAction,
    InvokeCatalogCheckAction,
)
from actions.definitions.gm_catalog import FindSituationAction, SubmitCatalogSuggestionAction
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
from actions.definitions.gm_props import StagePropAction, StagePropertyAction
from actions.definitions.gm_stories import (
    ClaimGroupStoryRequestAction,
    CompleteStoryAction,
    DeclareStakesAction,
    MarkBeatAction,
    PromoteEpisodeAction,
    RequestGMForCovenantAction,
    ResolveEpisodeAction,
    WithdrawGroupStoryRequestAction,
)
from actions.definitions.goals import LogGoalProgressAction, SetCharacterGoalsAction
from actions.definitions.identification import IdentifyAction
from actions.definitions.imbue import ImbueAction
from actions.definitions.investigation import SearchAction, StartInvestigationAction
from actions.definitions.items import (
    ActivatePermitAction,
    EquipAction,
    GrantItemAction,
    PutInAction,
    SetContainerPolicyAction,
    StealAction,
    TakeOutAction,
    UnequipAction,
    UseItemAction,
)
from actions.definitions.journals import (
    CreateJournalEntryAction,
    EditJournalEntryAction,
    RespondToJournalAction,
)
from actions.definitions.locations import (
    AssignRoomTenantAction,
    CommissionDecorationAction,
    DigRoomAction,
    EndRoomTenancyAction,
    LinkRoomsAction,
    PlaceFixtureAction,
    PlaceRoomAction,
    PrepareBuildingAction,
    RefurbishBuildingAction,
    RemoveFixtureAction,
    RemoveRoomAction,
    RenameExitAction,
    ResizeRoomAction,
    RoomEditAction,
    SetBuildingStyleAction,
    SetPrimaryHomeAction,
    SettleBuildingArrearsAction,
    StartBuildingActivationAction,
    StartBuildingRenovationAction,
    StartExtensionAction,
    TagRoomResonanceAction,
    ToggleUltraUpkeepAction,
    UnlinkRoomsAction,
    UntagRoomResonanceAction,
)
from actions.definitions.market import (
    BuyStockAction,
    BuyWareAction,
    FinishWareAction,
    ListWareAction,
    ServiceCraftAction,
    SetServiceOfferAction,
)
from actions.definitions.motif_style import (
    BindMotifStyleAction,
    ListMotifStylesAction,
    UnbindMotifStyleAction,
)
from actions.definitions.movement import (
    DropAction,
    GetAction,
    GiveAction,
    HomeAction,
    StopTravelAction,
    TravelAction,
    TraverseExitAction,
)
from actions.definitions.npc_assignments import (
    AssignGuardAction,
    ListGuardAssignmentsAction,
    UnassignGuardAction,
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
from actions.definitions.outfits import (
    AddOutfitSlotAction,
    ApplyOutfitAction,
    DeleteOutfitAction,
    RemoveOutfitSlotAction,
    RenameOutfitAction,
    SaveOutfitAction,
    UndressAction,
)
from actions.definitions.perception import InventoryAction, LookAction, LookAtItemAction
from actions.definitions.personas import SetActivePersonaAction
from actions.definitions.places import JoinPlaceAction, LeavePlaceAction
from actions.definitions.portals import DissolvePortalAnchorAction, InstallPortalAnchorAction
from actions.definitions.positioning import (
    GMPlaceInPositionAction,
    MoveToPositionAction,
    SetTheStageAction,
    TakePositionAction,
)
from actions.definitions.progression import ManageTrainingAction, PurchaseUnlockAction
from actions.definitions.progression_rewards import (
    CastVoteAction,
    ClaimKudosAction,
    ClaimRandomSceneAction,
    ClearPathIntentAction,
    RemoveVoteAction,
    RerollRandomSceneAction,
    SelectPathAction,
    SetPathIntentAction,
)
from actions.definitions.projects import (
    CheckContributeAction,
    DonateToProjectAction,
    LaunchPropagandaCampaignAction,
    StoryContributeAction,
)
from actions.definitions.relationships import (
    CreateCapstoneAction,
    CreateDevelopmentAction,
    CreateFirstImpressionAction,
    FileWriteupComplaintAction,
    GiveWriteupKudosAction,
    RedistributePointsAction,
    RelationshipBumpAction,
)
from actions.definitions.ritual import PerformRitualAction
from actions.definitions.room_features import (
    FundRoomWardAction,
    RepairLabStationAction,
    StartDefenseInstallationAction,
    StartRoomFeatureProjectAction,
)
from actions.definitions.rounds import (
    EndRoundAction,
    ForceResolveRoundAction,
    InterposeSceneAction,
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
from actions.definitions.scenes import (
    FinishSceneAction,
    GrantSceneGMAction,
    MarkDecisiveCheckAction,
    StartSceneAction,
)
from actions.definitions.ships import (
    CommissionShipAction,
    RepairShipAction,
    ShipStatusAction,
    UpgradeShipAction,
)
from actions.definitions.signature import (
    SignatureClearAction,
    SignatureListAction,
    SignatureSetAction,
)
from actions.definitions.situations import SetSituationAction
from actions.definitions.social import (
    blackmail,
    boon,
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
from actions.definitions.speaker_queue import (
    AdvanceSpeakerQueueAction,
    CloseSpeakerQueueAction,
    JoinSpeakerQueueAction,
    LeaveSpeakerQueueAction,
    OpenSpeakerQueueAction,
    SkipSpeakerAction,
)
from actions.definitions.story_builder import (
    CloseSceneRoomAction,
    CreateStoryAreaAction,
    EditStoryAreaAction,
    GrantStoryRoomAccessAction,
    JoinStoryRoomAction,
    LeaveStoryRoomAction,
    RemoveStoryAreaAction,
    RevokeStoryRoomAccessAction,
    SpinUpSceneRoomAction,
    StoryDigRoomAction,
    StoryEditRoomAction,
    StoryLinkRoomsAction,
    StoryPlaceRoomAction,
    StoryRemoveRoomAction,
    StoryUnlinkRoomsAction,
)
from actions.definitions.technique_authoring import AuthorTechniqueAction
from actions.definitions.threads import WeaveThreadAction
from actions.definitions.traps import DisarmTrapAction
from actions.definitions.vault import (
    VaultAccessAddAction,
    VaultAccessListAction,
    VaultAccessRemoveAction,
)
from actions.definitions.vitals import (
    GiveDeathKudosAction,
    RetireCharacterAction,
    WakeAction,
)
from actions.definitions.voyages import (
    AbandonVoyageAction,
    AdvanceLegAction,
    CompleteVoyageAction,
    DepartVoyageAction,
    InviteToVoyageAction,
    RespondVoyageInviteAction,
    StartVoyageAction,
)
from actions.definitions.windows import CloseWindowAction, OpenWindowAction
from actions.definitions.world_builder import (
    CreateAreaAction,
    EditAreaAction,
    PromoteAreaAction,
    PromoteRoomAction,
    StaffDigRoomAction,
    StaffEditRoomAction,
    StaffLinkRoomsAction,
    StaffPlaceClueAction,
    StaffPlaceClueTriggerAction,
    StaffPlacePortalAnchorAction,
    StaffPlaceRoomAction,
    StaffRemoveClueAction,
    StaffRemoveClueTriggerAction,
    StaffRemovePortalAnchorAction,
    StaffRemoveRoomAction,
    StaffRenameExitAction,
    StaffUnlinkRoomsAction,
)
from actions.types import TargetType

# All base action instances. Each is a singleton — actions are stateless.
_ALL_ACTIONS: list[Action] = [
    LookAction(),
    LookAtItemAction(),
    InventoryAction(),
    SearchAction(),
    IdentifyAction(),
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
    DigRoomAction(),
    ResizeRoomAction(),
    RemoveRoomAction(),
    LinkRoomsAction(),
    UnlinkRoomsAction(),
    RenameExitAction(),
    PlaceRoomAction(),
    SetBuildingStyleAction(),
    PlaceFixtureAction(),
    RemoveFixtureAction(),
    AssignRoomTenantAction(),
    EndRoomTenancyAction(),
    SetPrimaryHomeAction(),
    TagRoomResonanceAction(),
    UntagRoomResonanceAction(),
    CommissionDecorationAction(),
    StartExtensionAction(),
    StartBuildingRenovationAction(),
    StartBuildingActivationAction(),
    SettleBuildingArrearsAction(),
    RefurbishBuildingAction(),
    PrepareBuildingAction(),
    ToggleUltraUpkeepAction(),
    DonateToProjectAction(),
    CheckContributeAction(),
    StoryContributeAction(),
    LaunchPropagandaCampaignAction(),
    SetActivePersonaAction(),
    # #1866 — Places join/leave telnet coverage.
    JoinPlaceAction(),
    LeavePlaceAction(),
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
    StealAction(),
    SetContainerPolicyAction(),
    WithdrawCoinsAction(),
    DepositCoinsAction(),
    GiveCoinsAction(),
    ActivatePermitAction(),
    UseItemAction(),
    GrantItemAction(),
    GMAwardDistinctionAction(),
    AuthorizeDistinctionChangeAction(),
    AcceptDistinctionChangeAction(),
    # #2183 — dramatic-moment suggestion confirm/dismiss (account-authorized GM inbox).
    ConfirmDramaticMomentSuggestionAction(),
    DismissDramaticMomentSuggestionAction(),
    # #1866 — crafting telnet coverage.
    AttachFacetAction(),
    DetachFacetAction(),
    AttachStyleAction(),
    CreateItemAction(),
    ApplyOutfitAction(),
    UndressAction(),
    # #1866 — outfit CRUD telnet coverage.
    SaveOutfitAction(),
    RenameOutfitAction(),
    DeleteOutfitAction(),
    AddOutfitSlotAction(),
    RemoveOutfitSlotAction(),
    PresentOutfitAction(),
    JudgePresentationAction(),
    PoseEndorseAction(),
    SceneEntryEndorseAction(),
    StylePresentationEndorseAction(),
    TraverseExitAction(),
    TravelAction(),
    StopTravelAction(),
    HomeAction(),
    MoveToPositionAction(),
    TakePositionAction(),
    GMPlaceInPositionAction(),
    SetTheStageAction(),
    SetSituationAction(),
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
    InterposeSceneAction(),
    FleeAction(),
    CoverAction(),
    InterposeAction(),
    SuccorAction(),
    ChargeAction(),
    JoustAction(),
    UseItemManeuverAction(),
    EngageAction(),
    DisengageAction(),
    RallyAction(),
    DemoralizeAction(),
    TauntAction(),
    ParleyAction(),
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
    GrantSceneGMAction(),
    MarkDecisiveCheckAction(),
    BeginEncounterRoundAction(),
    ResolveEncounterRoundAction(),
    AddOpponentAction(),
    AddEncounterParticipantAction(),
    RemoveEncounterParticipantAction(),
    PauseEncounterAction(),
    EndEncounterAction(),
    PreviewOpponentDefaultsAction(),
    StagePropAction(),
    StagePropertyAction(),
    CompleteStoryAction(),
    ResolveEpisodeAction(),
    PromoteEpisodeAction(),
    MarkBeatAction(),
    DeclareStakesAction(),
    RequestGMForCovenantAction(),
    ClaimGroupStoryRequestAction(),
    WithdrawGroupStoryRequestAction(),
    ResolveAlterationAction(),
    RestAction(),
    ToggleFavoriteAction(),
    ToggleReactionAction(),
    ReactToWindowAction(),
    CreateFirstImpressionAction(),
    CreateDevelopmentAction(),
    CreateCapstoneAction(),
    RedistributePointsAction(),
    RelationshipBumpAction(),
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
    SelectPathAction(),
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
    blackmail,
    boon,
    coerce,
    reveal_secret,
    CharmAssetAction(),
    mint_accusation,
    SmearAction(),
    RefuteAccusationAction(),
    DenounceFramerAction(),
    perform,
    entrance,
    restore_sense,
    resolve_entry_flourish,
    resolve_crossing_offer,
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
    ChallengeChampionDuelAction(),
    OpenPlaceEncounterAction(),
    JoinPlaceEncounterAction(),
    SignatureSetAction(),
    SignatureClearAction(),
    SignatureListAction(),
    BindMotifStyleAction(),
    UnbindMotifStyleAction(),
    ListMotifStylesAction(),
    StartRoomFeatureProjectAction(),
    RepairLabStationAction(),
    StartDefenseInstallationAction(),
    FundRoomWardAction(),
    BuyStockAction(),
    BuyWareAction(),
    ListWareAction(),
    FinishWareAction(),
    SetServiceOfferAction(),
    ServiceCraftAction(),
    CommissionShipAction(),
    UpgradeShipAction(),
    RepairShipAction(),
    ShipStatusAction(),
    BindCompanionAction(),
    CompanionFightAction(),
    DeployCompanionAction(),
    ReleaseCompanionAction(),
    OrderCompanionAction(),
    # #2239 — in-play domain management + office delegation.
    AddDomainHoldingAction(),
    StartDomainImprovementAction(),
    AppointDomainOfficeAction(),
    VacateDomainOfficeAction(),
    MountCompanionAction(),
    DismountCompanionAction(),
    PromoteSummonAction(),
    # #1866 — door lock/unlock telnet coverage.
    LockAction(),
    UnlockAction(),
    PickLockAction(),
    BreakExitAction(),
    OpenWindowAction(),
    CloseWindowAction(),
    # #2116 — gift/technique/thread-weaving acquisition surface.
    PurchaseGiftUnlockAction(),
    AcceptTechniqueOfferAction(),
    AcceptThreadWeavingOfferAction(),
    # #2118 — GM adjudication toolkit: catalog check invocation, awards, conditions.
    InvokeCatalogCheckAction(),
    GMAwardAction(),
    GMApplyConditionAction(),
    # #2127 — GM scenario catalog: situation find/browse + suggestion inbox.
    FindSituationAction(),
    SubmitCatalogSuggestionAction(),
    # #2010 — GM battle staging: JUNIOR-gated catalog-pick-to-live-Battle actions.
    CreateBattleAction(),
    StageBattleMapAction(),
    SpawnBattleUnitsAction(),
    EnlistBattleParticipantAction(),
    BrowseBattleCatalogAction(),
    CollectFoodAction(),
    # #2222 — portal anchor install/dissolve (travel_to's portal branch
    # itself dispatches through TravelAction, already registered above).
    InstallPortalAnchorAction(),
    DissolvePortalAnchorAction(),
    # #1855 — overworld travel / voyages.
    StartVoyageAction(),
    AdvanceLegAction(),
    CompleteVoyageAction(),
    AbandonVoyageAction(),
    # #2352 — voyage party formation.
    InviteToVoyageAction(),
    RespondVoyageInviteAction(),
    DepartVoyageAction(),
    # #2179 — vault access-list management.
    VaultAccessAddAction(),
    VaultAccessRemoveAction(),
    VaultAccessListAction(),
    # #2178 — NPC guard assignment.
    AssignGuardAction(),
    UnassignGuardAction(),
    ListGuardAssignmentsAction(),
    # #2287 — death & unconsciousness core slice.
    WakeAction(),
    # #2290 — dream realm.
    SleepAction(),
    DescendAction(),
    AscendAction(),
    DreamwalkAction(),
    RetireCharacterAction(),
    GiveDeathKudosAction(),
    # #2289 — ceremonies (worship rites over the events/scenes chassis).
    OpenCeremonyAction(),
    CeremonyOfferingAction(),
    CeremonySpeechAction(),
    FinishCeremonyAction(),
    AbandonCeremonyAction(),
    RespondSeanceOfferAction(),
    # #1985 — estates (the executor's will-reading settlement door).
    WillReadingAction(),
    # #2295 — voluntary asset sharing: introduce an owned asset to a co-present ally.
    IntroduceAssetAction(),
    # #1825 — accusation counter-play: the criminal's post-crime evidence moves
    # + the research-lab door into the counter-investigation.
    GatherEvidenceAction(),
    DisposeEvidenceAction(),
    StartInvestigationAction(),
    StartFrameJobAction(),
    ProduceCaseEvidenceAction(),
    ExamineEvidenceAction(),
    # #2219 — inter-domain food transfer.
    TransferFoodAction(),
    # #2356 — speaker queue: room-scoped turn-order utility.
    OpenSpeakerQueueAction(),
    CloseSpeakerQueueAction(),
    JoinSpeakerQueueAction(),
    LeaveSpeakerQueueAction(),
    AdvanceSpeakerQueueAction(),
    SkipSpeakerAction(),
    # #2449 — staff world-builder canvas: create/edit area, dig/link/place/edit/
    # remove world rooms, promote to AUTHORED.
    CreateAreaAction(),
    EditAreaAction(),
    StaffDigRoomAction(),
    StaffEditRoomAction(),
    StaffLinkRoomsAction(),
    StaffUnlinkRoomsAction(),
    StaffRenameExitAction(),
    StaffPlaceRoomAction(),
    StaffRemoveRoomAction(),
    PromoteRoomAction(),
    PromoteAreaAction(),
    StaffPlaceClueAction(),
    StaffRemoveClueAction(),
    StaffPlaceClueTriggerAction(),
    StaffRemoveClueTriggerAction(),
    StaffPlacePortalAnchorAction(),
    StaffRemovePortalAnchorAction(),
    # #2450 — GM story builder: create/edit/remove story areas + dig/edit story rooms.
    CreateStoryAreaAction(),
    EditStoryAreaAction(),
    RemoveStoryAreaAction(),
    StoryDigRoomAction(),
    StoryEditRoomAction(),
    StoryLinkRoomsAction(),
    StoryUnlinkRoomsAction(),
    StoryPlaceRoomAction(),
    StoryRemoveRoomAction(),
    GrantStoryRoomAccessAction(),
    RevokeStoryRoomAccessAction(),
    JoinStoryRoomAction(),
    LeaveStoryRoomAction(),
    SpinUpSceneRoomAction(),
    CloseSceneRoomAction(),
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
    for a in (
        intimidate,
        persuade,
        deceive,
        flirt,
        seduce,
        blackmail,
        perform,
        entrance,
        restore_sense,
    )
}


def get_action(key: str) -> Action | None:
    """Look up an action by its key."""
    return ACTIONS_BY_KEY.get(key)


def get_actions_for_target_type(target_type: TargetType) -> list[Action]:
    """Return all actions that operate on the given target type."""
    return list(ACTIONS_BY_TARGET_TYPE.get(target_type, []))
