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
- cantrips: Cantrip
- motifs: Facet, Motif, MotifResonance, MotifResonanceAssociation
- soulfray: SoulfrayConfig, MishapPoolTier
- alterations: MagicalAlterationTemplate, PendingAlteration, MagicalAlterationEvent
- threads: Thread, ThreadLevelUnlock, ThreadPullCost, ThreadXPLockedLevel,
  ThreadPullEffect
- weaving: ThreadWeavingUnlock, CharacterThreadWeavingUnlock,
  ThreadWeavingTeachingOffer
- rituals: Ritual, RitualComponentRequirement, ImbuingProseTemplate
- ritual_scene_action: RitualSceneActionConfig
- reincarnation: Reincarnation
- grant: ResonanceGrant

Additionally: ``AudereThreshold`` lives in ``world.magic.audere`` but is
re-exported here so Django's model registry sees it via the ``magic.models``
module import path — and so the ``from world.magic.models import AudereThreshold``
pattern used by historic callers keeps working.
"""

# Keep Django's model registry aware of AudereThreshold by importing it via
# the magic.models package load path. Historic callers also import the name
# directly from world.magic.models.
from world.magic.audere import AudereThreshold, PendingAudereOffer
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
from world.magic.models.endorsement import PoseEndorsement, SceneEntryEndorsement
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
    PathRitualGrant,
    TraditionRitualGrant,
)
from world.magic.models.knowledge import CharacterRitualKnowledge
from world.magic.models.motifs import (
    Facet,
    FacetManager,
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
)
from world.magic.models.power_config import AuraPowerConfig, LevelPowerConfig
from world.magic.models.reincarnation import Reincarnation
from world.magic.models.resonance_environment import AffinityInteraction, ResonanceEnvironmentConfig
from world.magic.models.ritual_scene_action import RitualSceneActionConfig
from world.magic.models.rituals import (
    ImbuingProseTemplate,
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
from world.magic.models.soulfray import MishapPoolTier, SoulfrayConfig
from world.magic.models.technique_builder import (
    TechniqueBudgetConfig,
    TechniqueTierBudget,
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
    TechniqueStyle,
    TechniqueStyleManager,
)
from world.magic.models.threads import (
    Thread,
    ThreadLevelUnlock,
    ThreadPullCost,
    ThreadPullEffect,
    ThreadXPLockedLevel,
)
from world.magic.models.weaving import (
    CharacterThreadWeavingUnlock,
    ThreadWeavingTeachingOffer,
    ThreadWeavingUnlock,
)

__all__ = [
    # affinity
    "Affinity",
    # resonance-environment
    "AffinityInteraction",
    "AffinityManager",
    # anima
    "AnimaConfig",
    "AnimaRitualPerformance",
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
    "DistinctionRitualGrant",
    "EffectType",
    "EffectTypeManager",
    "Facet",
    "FacetManager",
    "Gift",
    "GiftManager",
    # rituals
    "ImbuingProseTemplate",
    "IntensityTier",
    # power config (#637)
    "LevelPowerConfig",
    # alterations
    "MagicalAlterationEvent",
    "MagicalAlterationTemplate",
    # soulfray
    "MishapPoolTier",
    "Motif",
    "MotifResonance",
    "MotifResonanceAssociation",
    "PathRitualGrant",
    "PendingAlteration",
    # audere offer surface (#873, re-exported from world.magic.audere)
    "PendingAudereOffer",
    # soul tether (Spec B §14.1, §15.1 — Task 1.7)
    "PendingStageAdvanceOffer",
    # endorsement (Spec C §2.2)
    "PoseEndorsement",
    # reincarnation
    "Reincarnation",
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
    "RitualComponentRequirement",
    "RitualSceneActionConfig",
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
    "SoulTetherRescue",
    "SoulfrayConfig",
    "Technique",
    "TechniqueAppliedCondition",
    # technique builder config (#537)
    "TechniqueBudgetConfig",
    "TechniqueCapabilityGrant",
    "TechniqueCapabilityRequirement",
    "TechniqueDamageProfile",
    "TechniqueOutcomeModifier",
    "TechniqueStyle",
    "TechniqueStyleManager",
    "TechniqueTierBudget",
    # threads
    "Thread",
    "ThreadLevelUnlock",
    "ThreadPullCost",
    "ThreadPullEffect",
    "ThreadWeavingTeachingOffer",
    "ThreadWeavingUnlock",
    "ThreadXPLockedLevel",
    "Tradition",
    "TraditionManager",
    "TraditionRitualGrant",
]
