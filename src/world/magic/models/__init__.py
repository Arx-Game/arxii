"""Magic system models.

This package was split from the original flat ``models.py`` per Scope 6 §4.4.
Public names are re-exported here so external callers continue to use
``from world.magic.models import X`` unchanged.

Submodules (see Scope 6 §4.4):
- affinity: Affinity, Resonance
- aura: CharacterAura, CharacterResonance, CharacterAffinityTotal
- anima: CharacterAnima, CharacterAnimaRitual, AnimaRitualPerformance
- gifts: Gift, CharacterGift, Tradition, CharacterTradition
- techniques: EffectType, TechniqueStyle, Restriction, IntensityTier, Technique,
  TechniqueCapabilityGrant, CharacterTechnique, TechniqueOutcomeModifier
- cantrips: Cantrip
- motifs: Facet, CharacterFacet, Motif, MotifResonance, MotifResonanceAssociation
- soulfray: SoulfrayConfig, MishapPoolTier
- alterations: MagicalAlterationTemplate, PendingAlteration, MagicalAlterationEvent
- threads: Thread, ThreadLevelUnlock, ThreadPullCost, ThreadXPLockedLevel,
  ThreadPullEffect
- weaving: ThreadWeavingUnlock, CharacterThreadWeavingUnlock,
  ThreadWeavingTeachingOffer
- rituals: Ritual, RitualComponentRequirement, ImbuingProseTemplate
- reincarnation: Reincarnation

Additionally: ``AudereThreshold`` lives in ``world.magic.audere`` but is
re-exported here so Django's model registry sees it via the ``magic.models``
module import path — and so the ``from world.magic.models import AudereThreshold``
pattern used by historic callers keeps working.
"""

# Keep Django's model registry aware of AudereThreshold by importing it via
# the magic.models package load path. Historic callers also import the name
# directly from world.magic.models.
from world.magic.audere import AudereThreshold
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
    CharacterAnimaRitual,
)
from world.magic.models.aura import (
    CharacterAffinityTotal,
    CharacterAura,
    CharacterResonance,
)
from world.magic.models.cantrips import Cantrip
from world.magic.models.gain_config import ResonanceGainConfig
from world.magic.models.gifts import (
    CharacterGift,
    CharacterTradition,
    Gift,
    GiftManager,
    Tradition,
    TraditionManager,
)
from world.magic.models.motifs import (
    CharacterFacet,
    Facet,
    FacetManager,
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
)
from world.magic.models.reincarnation import Reincarnation
from world.magic.models.rituals import (
    ImbuingProseTemplate,
    Ritual,
    RitualComponentRequirement,
)
from world.magic.models.soulfray import MishapPoolTier, SoulfrayConfig
from world.magic.models.techniques import (
    CharacterTechnique,
    EffectType,
    EffectTypeManager,
    IntensityTier,
    Restriction,
    RestrictionManager,
    Technique,
    TechniqueCapabilityGrant,
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
    "AffinityManager",
    # anima
    "AnimaConfig",
    "AnimaRitualPerformance",
    # audere (re-exported from world.magic.audere)
    "AudereThreshold",
    # cantrips
    "Cantrip",
    # aura
    "CharacterAffinityTotal",
    "CharacterAnima",
    "CharacterAnimaRitual",
    "CharacterAura",
    # motifs
    "CharacterFacet",
    # gifts
    "CharacterGift",
    "CharacterResonance",
    # techniques
    "CharacterTechnique",
    # weaving
    "CharacterThreadWeavingUnlock",
    "CharacterTradition",
    "EffectType",
    "EffectTypeManager",
    "Facet",
    "FacetManager",
    "Gift",
    "GiftManager",
    # rituals
    "ImbuingProseTemplate",
    "IntensityTier",
    # alterations
    "MagicalAlterationEvent",
    "MagicalAlterationTemplate",
    # soulfray
    "MishapPoolTier",
    "Motif",
    "MotifResonance",
    "MotifResonanceAssociation",
    "PendingAlteration",
    # reincarnation
    "Reincarnation",
    "Resonance",
    # gain config (Spec C §2.1)
    "ResonanceGainConfig",
    "ResonanceManager",
    "Restriction",
    "RestrictionManager",
    "Ritual",
    "RitualComponentRequirement",
    "SoulfrayConfig",
    "Technique",
    "TechniqueCapabilityGrant",
    "TechniqueOutcomeModifier",
    "TechniqueStyle",
    "TechniqueStyleManager",
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
]
