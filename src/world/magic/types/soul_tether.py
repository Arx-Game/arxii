"""Soul Tether typed payloads and result objects (Spec B)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import uuid

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


@dataclass(frozen=True, slots=True)
class StageAdvanceBonusOffer:
    """Pending offer recorded in-memory when the stage-advance prompt fires (Spec B §8.1).

    Synchronous dispatch architecture means the resist check resolves before the
    Sineater can respond.  The offer is stored in the module-level
    ``_pending_stage_advance_offers`` dict (keyed on ``offer_id``) so the Sineater
    can later call ``resolve_stage_advance_prompt`` to commit their contribution.
    The commitment deducts Hollow + adds Strain and is recorded as a
    retroactive resource.  It does NOT change the already-resolved check.
    """

    offer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sinner_sheet: CharacterSheet = field(default=None)  # type: ignore[assignment]
    sineater_sheet: CharacterSheet = field(default=None)  # type: ignore[assignment]
    resonance: Resonance = field(default=None)  # type: ignore[assignment]
    max_hollow_to_spend: int = 0


@dataclass(frozen=True, slots=True)
class StageAdvanceBonusResult:
    """Result of resolving a StageAdvanceBonusOffer (Spec B §8.1)."""

    offer_id: str
    units_committed: int
    hollow_drained: int
    strain_severity_added: int
    declined: bool
