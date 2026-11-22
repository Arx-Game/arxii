from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from world.conditions.models import ConditionStage, ConditionTemplate
    from world.magic.models import Resonance
    from world.magic.models.anima import AnimaRitualPerformance
    from world.mechanics.models import Property
    from world.traits.models import CheckOutcome


class AnimaRitualCategory(models.TextChoices):
    """Categories of anima recovery rituals."""

    SOLITARY = "solitary", "Solitary"
    COLLABORATIVE = "collaborative", "Collaborative"
    ENVIRONMENTAL = "environmental", "Environmental"
    CEREMONIAL = "ceremonial", "Ceremonial"


@dataclass(frozen=True)
class RitualOutcome:
    """What one anima ritual with a partner did to its performer's anima and Soulfray."""

    performance: AnimaRitualPerformance
    outcome: CheckOutcome
    severity_reduced: int
    anima_recovered: int
    soulfray_stage_after: ConditionStage | None
    soulfray_resolved: bool
    #: Anima of ``anima_recovered`` that the Chosen's patron added (#4349), 0 for anyone else,
    #: for a result whose patron row pays nothing and for a critical success (which refills).
    patron_bonus: int = 0
    patron_name: str = ""


@dataclass(frozen=True)
class RitualBond:
    """What an Anima ritual with a partner did beyond restoring anima (#5181).

    ``resonance`` is the resonance the ritual names (None when it names none, and then nothing
    else here is set). ``resonance_granted`` is what the ledger recorded after the earn rate of
    the resonance's own affinity (0 when the roll earned nothing). ``partner_fatigue_setting``
    is the sign of the affinity's ``ritual_partner_fatigue`` (1 takes, -1 eases, 0 does nothing);
    ``fatigue_change`` is the fatigue the partner actually gained (positive) or lost (negative).
    """

    resonance: Resonance | None = None
    resonance_granted: int = 0
    partner_fatigue_setting: int = 0
    fatigue_change: int = 0


@dataclass(frozen=True)
class SoulfrayContent:
    """Composite result from _SoulfrayContentFactory.

    Holds the seeded Soulfray ConditionTemplate, all 5 ordered stages (Fraying
    through Unravelling), and the blocks_anima_regen Property so callers can
    reference any piece without additional DB lookups.

    stages list index:
      0 → Fraying    (stage_order=1, severity_threshold=1)
      1 → Tearing    (stage_order=2, severity_threshold=6,  +blocks_anima_regen)
      2 → Ripping    (stage_order=3, severity_threshold=16, +blocks_anima_regen)
      3 → Sundering  (stage_order=4, severity_threshold=36, +blocks_anima_regen)
      4 → Unravelling(stage_order=5, severity_threshold=66, +blocks_anima_regen)

    ``template``/``stages`` are content-repo-owned (``conditions.ConditionTemplate``/
    ``conditions.ConditionStage``, #2698) — ``template`` is ``None`` and ``stages``
    is empty when the Soulfray condition isn't authored and ``SEED_SAMPLE_CONTENT``
    is off. ``blocks_anima_regen`` (``mechanics.Property``, also #2698) is likewise
    ``None`` when its Property/PropertyCategory aren't authored.
    """

    template: ConditionTemplate | None
    stages: tuple[ConditionStage, ...]
    blocks_anima_regen: Property | None


@dataclass(frozen=True)
class AnimaRegenTickSummary:
    """Result of a single anima_regen_tick() scheduler invocation."""

    examined: int
    regenerated: int
    engagement_blocked: int
    condition_blocked: int
