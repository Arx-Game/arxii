"""Magic system type declarations (thematic submodule split — Scope 6 §4.4).

Public surface is preserved for the flat-module era: importers that use
``from world.magic.types import <name>`` continue to work unchanged.
Submodules:

- ``aura``        — aura percentages and the AffinityType enum
- ``ritual``      — ritual-related enums (reserved for Phase 8's RitualOutcome)
- ``threads``     — thread axis enum and Imbuing / XP-lock result types
- ``techniques``  — runtime stats, anima cost, soulfray, mishap, use-technique results
- ``alterations`` — Mage Scar exception classes and pending/resolution results
- ``pull``        — resonance-pull action context and resolved / preview results
"""

from world.magic.types.alterations import (
    AlterationGateError,
    AlterationResolutionError,
    AlterationResolutionResult,
    PendingAlterationResult,
    PendingAlterationTierReduction,
)
from world.magic.types.aura import AffinityType, AuraPercentages
from world.magic.types.pull import (
    PullActionContext,
    PullPreviewResult,
    ResolvedPullEffect,
    ResonancePullResult,
)
from world.magic.types.ritual import AnimaRitualCategory
from world.magic.types.techniques import (
    AnimaCostResult,
    MishapResult,
    RuntimeTechniqueStats,
    SoulfrayResult,
    SoulfrayWarning,
    TechniqueUseResult,
)
from world.magic.types.threads import ThreadAxis, ThreadImbueResult, ThreadXPLockProspect

__all__ = [
    "AffinityType",
    "AlterationGateError",
    "AlterationResolutionError",
    "AlterationResolutionResult",
    "AnimaCostResult",
    "AnimaRitualCategory",
    "AuraPercentages",
    "MishapResult",
    "PendingAlterationResult",
    "PendingAlterationTierReduction",
    "PullActionContext",
    "PullPreviewResult",
    "ResolvedPullEffect",
    "ResonancePullResult",
    "RuntimeTechniqueStats",
    "SoulfrayResult",
    "SoulfrayWarning",
    "TechniqueUseResult",
    "ThreadAxis",
    "ThreadImbueResult",
    "ThreadXPLockProspect",
]
