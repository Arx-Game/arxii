from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models

from world.magic.constants import AnimaRitualEndorsement

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
class AnimaRitualChoices:
    """What a character may pick for her anima ritual's two resonances, and what it holds now.

    ``primal`` are the Primal resonances she holds and ``outward`` the Celestial or Abyssal
    ones, each by name. ``locked`` is true once either pick is set: changing them then takes
    an attunement (#5280).
    """

    primal: tuple[Resonance, ...]
    outward: tuple[Resonance, ...]
    primal_pick: Resonance | None
    outward_pick: Resonance | None
    locked: bool


@dataclass(frozen=True)
class AttunementResult:
    """What attuning an anima ritual to a new pair of resonances cost and did (#5280).

    ``changed`` is true when the roll held and the picks were written. ``anima_spent`` is the
    anima the attunement charged and ``soulfray_deficit`` the part of it she did not have, which
    went into Soulfray. ``resonance_spent`` maps the pk of each newly picked resonance to the
    balance it paid (kept in memory only).
    """

    changed: bool
    anima_spent: int
    soulfray_deficit: int
    resonance_spent: dict[int, int]
    message: str


@dataclass(frozen=True)
class RitualEarningParts:
    """The ritual's resonance award for one roll, split between its two picks (#5280).

    ``primal`` is the part for the Primal pick (how the ritual feels to the performer) and
    ``outward`` the part for the Celestial or Abyssal pick (what it reaches for in the
    partner). The two always add up to the award.
    """

    primal: int
    outward: int


@dataclass(frozen=True)
class HarvestedTrickle:
    """One resonance's waiting trickle an anima ritual harvested (#5308).

    ``amount`` is what the ledger recorded after the earn rate and the bonus check, and
    ``bonus_percent`` is the percent that check added (0 when it added nothing or was off).
    """

    resonance: Resonance
    amount: int
    bonus_percent: int


@dataclass(frozen=True)
class RitualBond:
    """What an Anima ritual with a partner did beyond restoring anima (#5181, #5280).

    ``primal_resonance`` and ``outward_resonance`` are the ritual's two picks (None for a pick
    it has none of). ``primal_granted`` is what the ledger recorded for the Primal pick, after
    the earn rate of its own affinity. ``outward_granted`` is the same for the outward pick, set
    only when a story NPC partner took part and the roll succeeded: a player character partner's
    part is held, not granted, so ``outward_pending`` carries the stored amount and
    ``endorsement`` is ``pending``. ``partner_fatigue_setting`` is the sign of the outward
    affinity's ``ritual_partner_fatigue`` (1 takes, -1 eases, 0 does nothing); ``fatigue_change``
    is the fatigue the partner actually gained (positive) or lost (negative). ``harvested`` is
    the waiting trickles the ritual turned into resonance, one entry per resonance (#5308).
    """

    primal_resonance: Resonance | None = None
    primal_granted: int = 0
    outward_resonance: Resonance | None = None
    outward_granted: int = 0
    outward_pending: int = 0
    endorsement: str = AnimaRitualEndorsement.NOT_ASKED
    partner_fatigue_setting: int = 0
    fatigue_change: int = 0
    harvested: tuple[HarvestedTrickle, ...] = ()


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
