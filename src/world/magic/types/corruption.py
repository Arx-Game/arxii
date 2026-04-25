"""Type declarations for the Corruption foundation (Magic Scope #7).

See docs/superpowers/specs/2026-04-25-magic-scope-7-corruption-design.md.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from world.conditions.models import ConditionInstance
    from world.conditions.types import AdvancementOutcome
    from world.magic.models.affinity import Resonance


class CorruptionSource(models.TextChoices):
    TECHNIQUE_USE = "TECHNIQUE_USE", "Technique use"
    SPEC_B_REDIRECT = "SPEC_B_REDIRECT", "Soul Tether redirect"
    STAFF_GRANT = "STAFF_GRANT", "Staff grant"


class CorruptionRecoverySource(models.TextChoices):
    ATONEMENT_RITE = "ATONEMENT_RITE", "Rite of Atonement"
    SPEC_B_RESCUE = "SPEC_B_RESCUE", "Soul Tether rescue"
    PASSIVE_DECAY = "PASSIVE_DECAY", "Passive decay tick"
    STAFF_GRANT = "STAFF_GRANT", "Staff intervention"


class CorruptionCause(models.TextChoices):
    STAGE_5_SUBSUMPTION = "STAGE_5_SUBSUMPTION", "Stage 5 entry — character loss"
    STAGE_5_RECOVERED = "STAGE_5_RECOVERED", "Stage 5 exit — protagonism restored"


@dataclass(frozen=True)
class CorruptionAccrualResult:
    """Frozen result of a single accrue_corruption call."""

    resonance: "Resonance"
    amount_applied: int
    current_before: int
    current_after: int
    lifetime_before: int
    lifetime_after: int
    stage_before: int
    stage_after: int
    advancement_outcome: "AdvancementOutcome"
    condition_instance: "ConditionInstance | None"


@dataclass(frozen=True)
class CorruptionRecoveryResult:
    """Frozen result of a single reduce_corruption call."""

    resonance: "Resonance"
    amount_reduced: int
    current_before: int
    current_after: int
    stage_before: int
    stage_after: int
    condition_resolved: bool


@dataclass(frozen=True)
class CorruptionAccrualSummary:
    """Frozen result of accrue_corruption_for_cast — per-cast roll-up."""

    caster_sheet_id: int
    technique_id: int
    per_resonance: tuple[CorruptionAccrualResult, ...]
