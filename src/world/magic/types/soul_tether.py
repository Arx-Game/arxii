"""Soul Tether typed payloads and result objects (Spec B)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
import uuid

from world.character_sheets.models import CharacterSheet
from world.magic.models.affinity import Resonance
from world.magic.models.soul_tether import Sineating, SoulTetherRescue
from world.relationships.models import CharacterRelationship

if TYPE_CHECKING:
    from world.magic.models import Thread
    from world.scenes.models import Scene


class SoulTetherRole(str, Enum):
    """Roles in a Soul Tether bond (Spec B §1.4)."""

    SINNER = "SINNER"
    SINEATER = "SINEATER"


@dataclass(frozen=True, slots=True)
class MireTransfer:
    """What one ``take_on_corruption`` moved (#5177).

    ``left_sinner`` is what the Sinner shed. ``arrived`` is what reached the Sineater after
    their resistance, which is what the holding grew by. ``held`` is the holding's amount
    afterwards (0 when nothing moved and no holding exists yet).
    """

    left_sinner: int
    arrived: int
    held: int


@dataclass(frozen=True, slots=True)
class MireCarried:
    """What a Sineater carries for one Sinner in one resonance (#5177).

    ``stage_order`` and ``label`` describe the Sineater's own corruption in the resonance:
    the stage it has reached and the name a player is shown for it ("Intrusive Thoughts:
    <resonance>" and so on), not a stage of the holding alone.
    """

    sinner_sheet_id: int
    sinner_name: str
    resonance_name: str
    amount: int
    stage_order: int
    label: str


@dataclass(frozen=True, slots=True)
class MireForSinner:
    """Everything a Sineater carries for one Sinner, with the total across resonances (#5177)."""

    sinner_sheet_id: int
    sinner_name: str
    rows: tuple[MireCarried, ...]
    total: int


@dataclass(frozen=True, slots=True)
class CheckedPlea:
    """A Sinner's plea after every refusal has passed, before anything is written (#5231).

    ``units`` is the number offered after clamping to the scene's cap. ``resonance`` is the one
    on the Sinner's tether ``thread`` in which the plea moves her corruption.
    """

    relationship: CharacterRelationship
    thread: Thread
    scene: Scene
    units: int
    resonance: Resonance


@dataclass(frozen=True, slots=True)
class SineatingOffer:
    """A Sinner's plea for Sineating, as recorded (#5177)."""

    sinner_sheet: CharacterSheet
    sineater_sheet: CharacterSheet
    relationship: CharacterRelationship
    resonance: Resonance
    max_units_offered: int
    current_hollow: int
    hollow_max: int
    sineater_current_strain_stage: int
    scene: Scene


@dataclass(frozen=True, slots=True)
class SineatingResult:
    """What a Sineating did, or a declined plea (#5177).

    ``resonance`` is the one the Sinner's corruption moved in: the resonance on her tether thread
    in which she had the most of her own to shed. ``sinner_resonance_earned`` is her total
    earning and ``sinner_earned_parts`` what each grant recorded, one pair per resonance on
    her thread that was paid (#5231). ``sineater_resonance`` is the resonance of the Sineater's own
    thread, None when they hold no resonance for it to channel, in which case they earned
    nothing. ``cut_by_ceiling`` is True when the Sineater could take on only part of the
    corruption the units would have moved.
    """

    audit_row: Sineating
    units_accepted: int
    declined: bool
    new_hollow_current: int
    new_lifetime_helped: int
    sinner_sheet: CharacterSheet
    sineater_sheet: CharacterSheet
    resonance: Resonance
    corruption_left_sinner: int = 0
    corruption_taken: int = 0
    cut_by_ceiling: bool = False
    outcome_name: str = ""
    sinner_resonance_earned: int = 0
    sinner_earned_parts: tuple[tuple[Resonance, int], ...] = ()
    sineater_resonance: Resonance | None = None
    sineater_resonance_earned: int = 0


@dataclass(frozen=True, slots=True)
class SineatingLines:
    """What each party is told about a Sineating, in the order they read it (#5177).

    One function builds both, so telnet and the web say the same thing. A line is plain text
    with no colour codes.
    """

    sinner: tuple[str, ...]
    sineater: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SineatingOption:
    """One thing a character can attach to a pose now: a plea to make or a plea to answer.

    ``role`` is the ``SineatingPoseRole`` the writer would play. ``max_units`` is the most
    units the writer can name: the scene's cap for a plea, the plea's offer for the ritual.
    ``resonance_name`` is the tether's resonance.
    """

    role: str
    partner_sheet_id: int
    partner_name: str
    max_units: int
    resonance_name: str


@dataclass(frozen=True, slots=True)
class PendingSineating:
    """The Sineating a pose asked for, checked and not yet carried out (#5177).

    ``role`` is the pose writer's part: ``SineatingPoseRole.ENTREAT`` (the Sinner's plea) or
    ``PERFORM`` (the Sineater's ritual). ``units`` is the amount after clamping to what the
    plea allows, so the writer is told what will happen.
    """

    role: str
    sinner_sheet: CharacterSheet
    sineater_sheet: CharacterSheet
    units: int


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


@dataclass(frozen=True, slots=True)
class SoulTetherDissolvedPayload:
    """Reactive event payload emitted when a Soul Tether bond dissolves (Spec B §13, Phase 15)."""

    sinner_sheet: CharacterSheet
    sineater_sheet: CharacterSheet
    relationship: CharacterRelationship
