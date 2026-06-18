"""Party profile aggregation and opponent stat-block scaling for encounter scaling (#566).

This module provides:
- ``PartyProfile`` / ``compute_party_profile`` — level-only party snapshot (Task 2).
- ``PhaseSpec`` / ``OpponentStatBlock`` / ``compute_opponent_stat_block`` — scaling
  formula that produces a frozen stat budget for a given tier + encounter (Task 3).
- ``get_encounter_scaling_config`` — singleton accessor, creates pk=1 on first use (Task 3).

The invariant: difficulty scales on party size + average primary character level
ONLY — never on "threads" (relationships, covenants, facets, fashion, magical
loadout).
"""

from dataclasses import dataclass
from decimal import Decimal

from world.classes.models import CharacterClassLevel
from world.combat.constants import OpponentTier, ParticipantStatus
from world.combat.models import (
    CombatEncounter,
    CombatParticipant,
    EncounterScalingConfig,
    OpponentTierTemplate,
    RiskScalingModifier,
)


@dataclass(frozen=True)
class PartyProfile:
    """Immutable snapshot of the active party used by the scaling formula.

    Attributes:
        party_size: Number of ACTIVE participants in the encounter.
        avg_level: Mean primary class level across ACTIVE participants;
            0.0 when the party is empty.
    """

    party_size: int
    avg_level: float


def compute_party_profile(encounter: CombatEncounter) -> PartyProfile:
    """Return a level-only snapshot of the ACTIVE party for *encounter*.

    Two queries only — no traversal of magic/thread/covenant/relationship
    models:

    1. Collect the character-sheet PKs of every ACTIVE participant.
    2. Fetch the primary class level for each of those characters.

    Because ``CharacterSheet`` uses a OneToOneField to ``ObjectDB`` as its
    primary key, ``character_sheet_id == character_id`` on that FK, so the
    second query's ``character_id__in`` filter directly matches
    ``CharacterClassLevel.character_id``.

    Returns:
        PartyProfile with ``party_size=0`` and ``avg_level=0.0`` for an
        empty encounter.
    """
    sheet_ids = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).values_list("character_sheet_id", flat=True)
    )

    levels = list(
        CharacterClassLevel.objects.filter(
            character_id__in=sheet_ids,
            is_primary=True,
        ).values_list("level", flat=True)
    )

    party_size = len(sheet_ids)
    avg_level = (sum(levels) / len(levels)) if levels else 0.0

    return PartyProfile(party_size=party_size, avg_level=avg_level)


# =============================================================================
# Task 3: OpponentStatBlock + compute_opponent_stat_block
# =============================================================================


@dataclass(frozen=True)
class PhaseSpec:
    """A single boss phase specification.

    Attributes:
        phase_number: 1-indexed phase number.
        health_trigger_percentage: Health % at which this phase activates.
            None (or 100.0) means the phase is active from full health.
        soak_value: Flat soak inherited from the computed stat block.
        probing_threshold: Probing threshold inherited from the computed stat block;
            None when the tier does not use probing.
    """

    phase_number: int
    health_trigger_percentage: float | None
    soak_value: int
    probing_threshold: int | None


@dataclass(frozen=True)
class OpponentStatBlock:
    """Frozen budget snapshot for a single opponent at a given tier and encounter context.

    All values are derived by the scaling formula from the authored
    ``OpponentTierTemplate``, the encounter's ``RiskScalingModifier``, and the
    active-party profile from ``EncounterScalingConfig``.

    Attributes:
        max_health: HP pool for this opponent.
        soak_value: Flat damage reduction per hit.
        probing_threshold: Minimum roll to probe the opponent's defenses;
            None when the tier does not use probing.
        swarm_count: Number of swarm bodies; None for non-swarm tiers.
        body_toughness: HP per swarm body; None for non-swarm tiers.
        bodies_per_attack: Bodies lost per outgoing swarm attack; None for non-swarm tiers.
        barrier_strength: Ward barrier strength; None when not template-driven.
        phases: Tuple of PhaseSpecs for BOSS tier (boss_phase_count entries);
            empty for all other tiers.
    """

    max_health: int
    soak_value: int
    probing_threshold: int | None
    swarm_count: int | None
    body_toughness: int | None
    bodies_per_attack: int | None
    barrier_strength: int | None
    phases: tuple[PhaseSpec, ...]


def get_encounter_scaling_config() -> EncounterScalingConfig:
    """Return the EncounterScalingConfig singleton (pk=1), creating it on first use.

    On a fresh DB the row may be absent — this function creates ONLY the singleton
    using the authored defaults from constants.  It does NOT touch the lookup tables
    (OpponentTierTemplate, RiskScalingModifier, StakesLevelRequirement); those are
    seeded separately by ``seed_scaling_defaults()`` and must not be reset here
    because a config accessor must not clobber staff-tuned rows.
    """
    from world.combat.constants import (  # noqa: PLC0415
        SCALING_CONFIG_BASELINE_PARTY_SIZE,
        SCALING_CONFIG_PER_AVG_LEVEL_PCT,
        SCALING_CONFIG_PER_EXTRA_MEMBER_PCT,
    )

    config, _ = EncounterScalingConfig.objects.get_or_create(
        pk=1,
        defaults={
            "baseline_party_size": SCALING_CONFIG_BASELINE_PARTY_SIZE,
            "per_extra_member_pct": Decimal(SCALING_CONFIG_PER_EXTRA_MEMBER_PCT),
            "per_avg_level_pct": Decimal(SCALING_CONFIG_PER_AVG_LEVEL_PCT),
        },
    )
    return config


def _scale_optional(base: int | None, multiplier: Decimal) -> int | None:
    """Return ``round(base * multiplier)`` or ``None`` when *base* is ``None``."""
    if base is None:
        return None
    return round(Decimal(base) * multiplier)


def _build_boss_phases(
    tier: str,
    phase_count: int,
    soak_value: int,
    probing_threshold: int | None,
) -> tuple[PhaseSpec, ...]:
    """Return the PhaseSpec tuple for BOSS tier; empty tuple for all other tiers.

    Phase 1 is active from full health (health_trigger_percentage=None).
    Subsequent phases trigger at evenly-spaced descending thresholds:
    phase k of N triggers at 100*(N-k+1)/N.
    Example (N=3): phase 2 at ≈66.67, phase 3 at ≈33.33.
    """
    if tier != OpponentTier.BOSS:
        return ()
    phases: list[PhaseSpec] = [
        PhaseSpec(
            phase_number=1,
            health_trigger_percentage=None,
            soak_value=soak_value,
            probing_threshold=probing_threshold,
        )
    ]
    for k in range(2, phase_count + 1):
        trigger = round(100.0 * (phase_count - k + 1) / phase_count, 2)
        phases.append(
            PhaseSpec(
                phase_number=k,
                health_trigger_percentage=trigger,
                soak_value=soak_value,
                probing_threshold=probing_threshold,
            )
        )
    return tuple(phases)


def compute_opponent_stat_block(
    tier: str,
    encounter: CombatEncounter,
    *,
    party_size: int | None = None,
    avg_level: float | None = None,
) -> OpponentStatBlock:
    """Compute a frozen stat budget for an opponent of *tier* in *encounter*.

    When *party_size* / *avg_level* are ``None``, the active party profile is
    derived from the encounter via ``compute_party_profile``.

    Formula:
        party_mult = 1
            + cfg.per_extra_member_pct * max(0, party_size - cfg.baseline_party_size)
            + cfg.per_avg_level_pct * avg_level
        risk_mult = RiskScalingModifier for encounter.risk_level (falls back to 1.0)
        max_health  = round(tpl.base_health  * risk_mult * party_mult)
        soak_value  = round(tpl.base_soak    * risk_mult)
        probing_threshold = round(tpl.base_probing_threshold * risk_mult) if not None
        swarm_count = round(tpl.base_swarm_count * party_mult) if not None
        barrier_strength = round(tpl.barrier_strength * risk_mult) if not None
        body_toughness / bodies_per_attack pass through unchanged.

    HERO_KILLER guard: HERO_KILLER base stats are intentionally set to "unbeatable"
    sentinel values (e.g. base_health=9999). Multiplying them would produce nonsense,
    so HERO_KILLER blocks are returned with template values UNSCALED.

    Args:
        tier: An ``OpponentTier`` value (e.g. ``OpponentTier.BOSS``).
        encounter: The ``CombatEncounter`` providing risk_level and party context.
        party_size: Override the active party size (for GM preview / what-if).
        avg_level: Override the average party level (for GM preview / what-if).

    Returns:
        A frozen ``OpponentStatBlock``.

    Raises:
        OpponentTierTemplate.DoesNotExist: When no template row exists for *tier*
            (programmer/seed error — let it propagate).
    """
    # Resolve party profile (two queries at most, or zero if overrides are provided).
    if party_size is None or avg_level is None:
        profile = compute_party_profile(encounter)
        if party_size is None:
            party_size = profile.party_size
        if avg_level is None:
            avg_level = profile.avg_level

    # Fetch authored template — DoesNotExist is a programmer/seed error; propagate.
    tpl: OpponentTierTemplate = OpponentTierTemplate.objects.get(tier=tier)

    # HERO_KILLER guard: return template base values unscaled (sentinel stats must not
    # be multiplied — doing so produces nonsense health/soak budgets).
    if tier == OpponentTier.HERO_KILLER:
        return OpponentStatBlock(
            max_health=tpl.base_health,
            soak_value=tpl.base_soak,
            probing_threshold=tpl.base_probing_threshold,
            swarm_count=tpl.base_swarm_count,
            body_toughness=tpl.body_toughness,
            bodies_per_attack=tpl.bodies_per_attack,
            barrier_strength=tpl.barrier_strength,
            phases=(),
        )

    # Risk multiplier — fall back to 1.0 if the authored row is missing.
    try:
        risk_row = RiskScalingModifier.objects.get(risk_level=encounter.risk_level)
        risk_mult: Decimal = risk_row.multiplier
    except RiskScalingModifier.DoesNotExist:
        risk_mult = Decimal("1.0")

    cfg = get_encounter_scaling_config()

    # Party multiplier (Decimal arithmetic throughout; convert to int once via round).
    extra_members = max(0, party_size - cfg.baseline_party_size)
    party_mult: Decimal = (
        Decimal(1)
        + cfg.per_extra_member_pct * Decimal(str(extra_members))
        + cfg.per_avg_level_pct * Decimal(str(avg_level))
    )

    max_health = round(Decimal(tpl.base_health) * risk_mult * party_mult)
    soak_value = round(Decimal(tpl.base_soak) * risk_mult)
    probing_threshold = _scale_optional(tpl.base_probing_threshold, risk_mult)
    swarm_count = _scale_optional(tpl.base_swarm_count, party_mult)
    barrier_strength = _scale_optional(tpl.barrier_strength, risk_mult)

    return OpponentStatBlock(
        max_health=max_health,
        soak_value=soak_value,
        probing_threshold=probing_threshold,
        swarm_count=swarm_count,
        body_toughness=tpl.body_toughness,
        bodies_per_attack=tpl.bodies_per_attack,
        barrier_strength=barrier_strength,
        phases=_build_boss_phases(tier, tpl.boss_phase_count, soak_value, probing_threshold),
    )
