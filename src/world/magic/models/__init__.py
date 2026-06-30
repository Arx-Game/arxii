"""Magic system models.

This package was split from the original flat ``models.py`` per Scope 6 §4.4.
Public names are re-exported here so external callers continue to use
``from world.magic.models import X`` unchanged.

Submodules (see Scope 6 §4.4):
- affinity: Affinity, Resonance
- aura: CharacterAura, CharacterResonance, CharacterAffinityTotal
- anima: CharacterAnima, AnimaRitualPerformance
- gifts: Gift, CharacterGift, Tradition, CharacterTradition
- techniques: EffectType, TechniqueStyle, Restriction, IntensityTier, Technique,
  TechniqueAppliedCondition, TechniqueCapabilityGrant, TechniqueCapabilityRequirement,
  TechniqueDamageProfile, CharacterTechnique, TechniqueOutcomeModifier
- technique_draft: TechniqueDraft, TechniqueDraftCapabilityGrant,
  TechniqueDraftDamageProfile, TechniqueDraftAppliedCondition
- specialization: TechniqueVariant, TechniqueVariantCapabilityGrant,
  TechniqueVariantDamageProfile, TechniqueVariantAppliedCondition
  (gift-technique specialization variants, #1578)
- cantrips: Cantrip
- motifs: Facet, Motif, MotifResonance, MotifResonanceAssociation
- soulfray: SoulfrayConfig, MishapPoolTier
- alterations: MagicalAlterationTemplate, PendingAlteration, MagicalAlterationEvent
- threads: Thread, ThreadLevelUnlock, ThreadPullCost, ThreadXPLockedLevel,
  ThreadPullEffect
- weaving: ThreadWeavingUnlock, CharacterThreadWeavingUnlock,
  ThreadWeavingTeachingOffer
- rituals: Ritual, RitualComponentRequirement, ImbuingProseTemplate
- ritual_check_config: RitualCheckConfig
- reincarnation: Reincarnation
- grant: ResonanceGrant
- progression_milestone: MagicProgressionMilestone

Additionally: ``AudereThreshold`` lives in ``world.magic.audere`` but is
re-exported here so Django's model registry sees it via the ``magic.models``
module import path — and so the ``from world.magic.models import AudereThreshold``
pattern used by historic callers keeps working.
"""

# Keep Django's model registry aware of AudereThreshold by importing it via
# the magic.models package load path. Historic callers also import the name
# directly from world.magic.models.
from world.magic.audere import AbstractPendingOffer, AudereThreshold, PendingAudereOffer
from world.magic.audere_majora import (
    AudereMajoraCrossing,
    AudereMajoraThreshold,
    PendingAudereMajoraOffer,
)

# entry-flourish offer (#1140, re-exported so Django's model registry sees it)
from world.magic.entry_flourish import PendingEntryFlourishOffer
from world.magic.models.affinity import (
    Affinity,
    AffinityManager,
    Resonance,
    ResonanceManager,
)
from world.magic.models.alterations import (
    MagicalAlterationEvent,
    MagicalAlterationTemplate,
    PendingAlteration,
)
from world.magic.models.anima import (
    AnimaConfig,
    AnimaRitualPerformance,
    CharacterAnima,
)
from world.magic.models.aura import (
    CharacterAffinityTotal,
    CharacterAura,
    CharacterResonance,
)
from world.magic.models.cantrips import Cantrip
from world.magic.models.commitments import CommittingDeclaration  # noqa: F401
from world.magic.models.corruption_config import CorruptionConfig
from world.magic.models.dramatic_moment import DramaticMomentTag, DramaticMomentType
from world.magic.models.endorsement import (
    EntryFlourishRecord,
    PoseEndorsement,
    PresentationEndorsement,
    SceneEntryEndorsement,
    StylePresentationEndorsement,
)
from world.magic.models.fury import FuryConfig, FuryTier
from world.magic.models.gain_config import ResonanceGainConfig
from world.magic.models.gifts import (
    CharacterGift,
    CharacterTradition,
    Gift,
    GiftManager,
    Tradition,
    TraditionManager,
)
from world.magic.models.grant import ResonanceGrant
from world.magic.models.grants import (
    BeginningsRitualGrant,
    CodexEntryRitualGrant,
    DistinctionRitualGrant,
    PathGiftGrant,
    PathRitualGrant,
    TraditionRitualGrant,
)
from world.magic.models.knowledge import CharacterRitualKnowledge
from world.magic.models.liturgy import RitualLiturgy
from world.magic.models.motifs import (
    Facet,
    FacetManager,
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
    MotifResonanceStyle,
)
from world.magic.models.power_config import AuraPowerConfig, LevelPowerConfig, StandingCapBand
from world.magic.models.progression_milestone import MagicProgressionMilestone
from world.magic.models.reincarnation import Reincarnation
from world.magic.models.renown_config import RenownAwardConfig
from world.magic.models.resonance_environment import AffinityInteraction, ResonanceEnvironmentConfig
from world.magic.models.ritual_check_config import RitualCheckConfig
from world.magic.models.rituals import (
    ImbuingProseTemplate,
    PendingRitualEffect,
    Ritual,
    RitualComponentRequirement,
)
from world.magic.models.sanctum import (
    SanctumDetails,
    SanctumOwnerMode,
    SanctumPendingPayout,
)
from world.magic.models.sessions import (
    RitualSession,
    RitualSessionParticipant,
    RitualSessionReference,
)
from world.magic.models.soul_tether import (
    PendingStageAdvanceOffer,
    Sineating,
    SineatingPendingOffer,
    SoulTetherRescue,
)
from world.magic.models.soul_tether_config import SoulTetherConfig
from world.magic.models.soulfray import MishapPoolTier, SoulfrayConfig
from world.magic.models.technique_builder import (
    TechniqueBudgetConfig,
    TechniqueTierBudget,
)
from world.magic.models.technique_draft import (
    TechniqueDraft,
    TechniqueDraftAppliedCondition,
    TechniqueDraftCapabilityGrant,
    TechniqueDraftDamageProfile,
    TechniqueDraftRemovedCondition,
)
from world.magic.models.techniques import (
    CharacterTechnique,
    EffectType,
    EffectTypeManager,
    IntensityTier,
    Restriction,
    RestrictionManager,
    Technique,
    TechniqueAppliedCondition,
    TechniqueCapabilityGrant,
    TechniqueCapabilityRequirement,
    TechniqueDamageProfile,
    TechniqueOutcomeModifier,
    TechniqueRemovedCondition,
    TechniqueStyle,
    TechniqueStyleManager,
)
from world.magic.models.threads import (
    Thread,
    ThreadLevelUnlock,
    ThreadPullCost,
    ThreadPullEffect,
    ThreadSurvivabilityTuning,
    ThreadXPLockedLevel,
)
from world.magic.models.weaving import (
    CharacterThreadWeavingUnlock,
    ThreadWeavingTeachingOffer,
    ThreadWeavingUnlock,
)
from world.magic.specialization.models import (
    TechniqueVariant,
    TechniqueVariantAppliedCondition,
    TechniqueVariantCapabilityGrant,
    TechniqueVariantDamageProfile,
)

__all__ = [
    # audere (re-exported from world.magic.audere)
    "AbstractPendingOffer",
    # affinity
    "Affinity",
    # resonance-environment
    "AffinityInteraction",
    "AffinityManager",
    # anima
    "AnimaConfig",
    "AnimaRitualPerformance",
    # audere majora (re-exported from world.magic.audere_majora)
    "AudereMajoraCrossing",
    "AudereMajoraThreshold",
    # audere (re-exported from world.magic.audere)
    "AudereThreshold",
    # power config (#768)
    "AuraPowerConfig",
    # knowledge layer grants (Anima Ritual UI spec §Decision 6)
    "BeginningsRitualGrant",
    # cantrips
    "Cantrip",
    # aura
    "CharacterAffinityTotal",
    "CharacterAnima",
    "CharacterAura",
    # gifts
    "CharacterGift",
    "CharacterResonance",
    # knowledge layer (Anima Ritual UI spec §Decision 6)
    "CharacterRitualKnowledge",
    # techniques
    "CharacterTechnique",
    # weaving
    "CharacterThreadWeavingUnlock",
    "CharacterTradition",
    "CodexEntryRitualGrant",
    # corruption config (Scope 7 §2.3)
    "CorruptionConfig",
    # dramatic moment tagging (#545)
    "DistinctionRitualGrant",
    "DramaticMomentTag",
    "DramaticMomentType",
    "EffectType",
    "EffectTypeManager",
    # endorsement — entry flourish (#545)
    "EntryFlourishRecord",
    "Facet",
    "FacetManager",
    # fury lever
    "FuryConfig",
    "FuryTier",
    "Gift",
    "GiftManager",
    # rituals
    "ImbuingProseTemplate",
    "IntensityTier",
    # power config (#637)
    "LevelPowerConfig",
    # progression dashboard (#536)
    "MagicProgressionMilestone",
    # alterations
    "MagicalAlterationEvent",
    "MagicalAlterationTemplate",
    # soulfray
    "MishapPoolTier",
    "Motif",
    "MotifResonance",
    "MotifResonanceAssociation",
    "MotifResonanceStyle",
    "PathGiftGrant",
    "PathRitualGrant",
    "PendingAlteration",
    # audere majora offer (#543, re-exported from world.magic.audere_majora)
    "PendingAudereMajoraOffer",
    # audere offer surface (#873, re-exported from world.magic.audere)
    "PendingAudereOffer",
    # entry-flourish offer (#1140, re-exported from world.magic.entry_flourish)
    "PendingEntryFlourishOffer",
    # CEREMONY-kind ritual in-progress effect (#1342)
    "PendingRitualEffect",
    # soul tether (Spec B §14.1, §15.1 — Task 1.7)
    "PendingStageAdvanceOffer",
    # endorsement (Spec C §2.2)
    "PoseEndorsement",
    # endorsement (Outfits Phase C §2.2 — #514)
    "PresentationEndorsement",
    # reincarnation
    "Reincarnation",
    # renown award config abstract base (#953)
    "RenownAwardConfig",
    "Resonance",
    # resonance-environment config
    "ResonanceEnvironmentConfig",
    # gain config (Spec C §2.1)
    "ResonanceGainConfig",
    # gain ledger (Spec C §2.4)
    "ResonanceGrant",
    "ResonanceManager",
    "Restriction",
    "RestrictionManager",
    "Ritual",
    "RitualCheckConfig",
    "RitualComponentRequirement",
    "RitualLiturgy",
    # sessions (Slice B §4.2–§4.4)
    "RitualSession",
    "RitualSessionParticipant",
    "RitualSessionReference",
    # sanctum (Plan 4 Subsystem F)
    "SanctumDetails",
    "SanctumOwnerMode",
    "SanctumPendingPayout",
    # endorsement (Spec C §2.3)
    "SceneEntryEndorsement",
    # soul tether (Spec B §14.1, §15.1)
    "Sineating",
    "SineatingPendingOffer",
    "SoulTetherConfig",
    "SoulTetherRescue",
    "SoulfrayConfig",
    # power config — per-level standing cap bands (#853)
    "StandingCapBand",
    # endorsement (Spec C style presentation — #1152)
    "StylePresentationEndorsement",
    "Technique",
    "TechniqueAppliedCondition",
    # technique builder config (#537)
    "TechniqueBudgetConfig",
    "TechniqueCapabilityGrant",
    "TechniqueCapabilityRequirement",
    "TechniqueDamageProfile",
    # technique draft authoring state (#1496)
    "TechniqueDraft",
    "TechniqueDraftAppliedCondition",
    "TechniqueDraftCapabilityGrant",
    "TechniqueDraftDamageProfile",
    "TechniqueDraftRemovedCondition",
    "TechniqueOutcomeModifier",
    "TechniqueRemovedCondition",
    "TechniqueStyle",
    "TechniqueStyleManager",
    "TechniqueTierBudget",
    # gift-technique specialization variants (#1578)
    "TechniqueVariant",
    "TechniqueVariantAppliedCondition",
    "TechniqueVariantCapabilityGrant",
    "TechniqueVariantDamageProfile",
    # threads
    "Thread",
    "ThreadLevelUnlock",
    "ThreadPullCost",
    "ThreadPullEffect",
    "ThreadSurvivabilityTuning",
    "ThreadWeavingTeachingOffer",
    "ThreadWeavingUnlock",
    "ThreadXPLockedLevel",
    "Tradition",
    "TraditionManager",
    "TraditionRitualGrant",
]
