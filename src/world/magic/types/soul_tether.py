"""Soul Tether typed payloads and result objects (Spec B)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from world.character_sheets.models import CharacterSheet
from world.magic.models.affinity import Resonance
from world.magic.models.soul_tether import Sineating, SoulTetherRescue
from world.relationships.models import CharacterRelationship


class SoulTetherRole(str, Enum):
    """Roles in a Soul Tether bond (Spec B §1.4)."""

    ABYSSAL = "ABYSSAL"
    SINEATER = "SINEATER"


@dataclass(frozen=True, slots=True)
class SineatingOffer:
    """Payload sent to the Sineater in the PROMPT_PLAYER prompt (Spec B §7.2)."""

    sinner_sheet: CharacterSheet
    sineater_sheet: CharacterSheet
    relationship: CharacterRelationship
    resonance: Resonance
    max_units_offered: int
    anima_cost_per_unit: int
    fatigue_cost_per_unit: int
    current_hollow: int
    hollow_max: int
    sineater_current_strain_stage: int


@dataclass(frozen=True, slots=True)
class SineatingResult:
    """Result of resolving a Sineating prompt (Spec B §7.2)."""

    audit_row: Sineating
    units_accepted: int
    declined: bool
    new_hollow_current: int
    new_lifetime_helped: int


@dataclass(frozen=True, slots=True)
class RescueOutcome:
    """Result of perform_soul_tether_rescue (Spec B §9.4)."""

    audit_row: SoulTetherRescue
    severity_reduced: int
    sinner_stage_at_start: int
    sinner_stage_at_end: int
    sineater_strain_taken: int
    protagonism_lock_lifted: bool
