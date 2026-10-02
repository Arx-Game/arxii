"""Magic system type declarations (thematic submodule split — Scope 6 §4.4).

Public surface is preserved for the flat-module era: importers that use
``from world.magic.types import <name>`` continue to work unchanged.
Submodules:

- ``aura``        — aura percentages and the AffinityType enum
- ``ritual``      — ritual-related enums, RitualOutcome, and AnimaRegenTickSummary
- ``threads``     — thread axis enum and Imbuing / XP-lock result types
- ``techniques``  — runtime stats, anima cost, soulfray, mishap, use-technique results
- ``alterations`` — Mage Scar exception classes and pending/resolution results
- ``pull``        — resonance-pull action context and resolved / preview results
- ``ultimates``   — Audere ultimate reveal cards/groups and owner-facing state (#4098)
"""

from world.magic.types.alterations import (
    AlterationGateError,
    AlterationResolutionError,
    AlterationResolutionResult,
    PendingAlterationResult,
    PendingAlterationTierReduction,
)
from world.magic.types.aura import AffinityType, AuraDrift, AuraPercentages
from world.magic.types.gain import (
    ResonanceDailyTickSummary,
    ResonanceWeeklySettlementSummary,
    SettlementResult,
)
from world.magic.types.pull import (
    PullActionContext,
    PullPreviewResult,
    ResolvedPullEffect,
    ResonancePullResult,
)
from world.magic.types.ritual import (
    AnimaRegenTickSummary,
    AnimaRitualCategory,
    RitualOutcome,
    SoulfrayContent,
)
from world.magic.types.techniques import (
    AnimaCostResult,
    MishapResult,
    ResonanceInvolvement,
    RuntimeTechniqueStats,
    SoulfrayResult,
    SoulfrayStageSummary,
    SoulfrayWarning,
    TechniqueUseResult,
)
from world.magic.types.threads import (
    ThreadAxis,
    ThreadImbueResult,
    ThreadSurvivabilitySaves,
    ThreadXPLockProspect,
)
from world.magic.types.ultimates import (
    AudereUltimateState,
    UltimateReveal,
    UltimateRevealCard,
    UltimateRevealGroup,
)

__all__ = [
    "AffinityType",
    "AlterationGateError",
    "AlterationResolutionError",
    "AlterationResolutionResult",
    "AnimaCostResult",
    "AnimaRegenTickSummary",
    "AnimaRitualCategory",
    "AudereUltimateState",
    "AuraDrift",
    "AuraPercentages",
    "MishapResult",
    "PendingAlterationResult",
    "PendingAlterationTierReduction",
    "PullActionContext",
    "PullPreviewResult",
    "ResolvedPullEffect",
    "ResonanceDailyTickSummary",
    "ResonanceInvolvement",
    "ResonancePullResult",
    "ResonanceWeeklySettlementSummary",
    "RitualOutcome",
    "RuntimeTechniqueStats",
    "SettlementResult",
    "SoulfrayContent",
    "SoulfrayResult",
    "SoulfrayStageSummary",
    "SoulfrayWarning",
    "TechniqueUseResult",
    "ThreadAxis",
    "ThreadImbueResult",
    "ThreadSurvivabilitySaves",
    "ThreadXPLockProspect",
    "UltimateReveal",
    "UltimateRevealCard",
    "UltimateRevealGroup",
]
