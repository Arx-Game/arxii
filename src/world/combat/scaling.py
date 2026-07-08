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

from django.core.exceptions import ObjectDoesNotExist
from evennia.accounts.models import AccountDB

from world.combat.constants import OpponentTier, ParticipantStatus
from world.combat.models import (
    CombatEncounter,
    CombatParticipant,
    EncounterScalingConfig,
    OpponentTierTemplate,
    RiskScalingModifier,
    StakesLevelRequirement,
)
from world.covenants.mentorship import effective_combat_level
from world.gm.constants import GMLevel, gm_level_index


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

    Read-only — safe to call on GET endpoints.  Bond dissolution (persisting
    graduation) is a write-side concern handled in ``begin_declaration_phase``.

    Query strategy (#1165, Task 6):
    1. Fetch each ACTIVE participant's ``character_sheet`` in one query
       (``select_related``).
    2. Call ``effective_combat_level(sheet)`` per participant — this may issue
       a small number of additional queries per bonded participant (bounded by
       party size, not a loop-growth problem for normal party sizes).

    ``effective_combat_level`` returns the raw primary level when the
    participant has no active non-graduated bond, so the common case (no bond)
    is unchanged from the previous two-query shape.

    Returns:
        PartyProfile with ``party_size=0`` and ``avg_level=0.0`` for an
        empty encounter.
    """
    participants = list(
        CombatParticipant.objects.filter(
            encounter=encounter,
            status=ParticipantStatus.ACTIVE,
        ).select_related("character_sheet")
    )

    party_size = len(participants)
    if not participants:
        return PartyProfile(party_size=0, avg_level=0.0)

    levels = [effective_combat_level(p.character_sheet) for p in participants]
    avg_level = sum(levels) / len(levels)

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
    actions_per_round: int = 1


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


# =============================================================================
# Task 4: validate_stakes_requirement
# =============================================================================


class StakesRequirementError(ValueError):
    """Raised when a GM or party does not meet a stakes-level gate.

    Attributes:
        user_message: Human-readable explanation suitable for surfacing to
            the GM (e.g. via an API serializer 400 response).
    """

    def __init__(self, *args: object, user_message: str = "") -> None:
        super().__init__(*args)
        self.user_message = user_message


class NPCUnderCustodyError(ValueError):
    """Raised when ``add_opponent`` would appear a story-protected NPC to an outsider GM.

    Raised by ``add_opponent`` (#2001 Task 5) when the opponent resolves to an
    existing ``CharacterSheet`` (via ``existing_objectdb``/``persona``) that a
    ``StoryProtectedSubject`` guards, and ``check_subject_custody`` refuses the
    acting GM's account at ``CustodyScope.APPEAR``.

    Attributes:
        user_message: Disclosure-safe explanation (ADR-0033-style — never the
            protecting story's identity, only the custodian GM's username or a
            staff-routed fallback) suitable for surfacing to the GM.
    """

    def __init__(self, *args: object, user_message: str = "") -> None:
        super().__init__(*args)
        self.user_message = user_message


def validate_stakes_requirement(encounter: CombatEncounter, gm_account: AccountDB) -> None:
    """Raise StakesRequirementError if *gm_account* cannot run *encounter* at its stakes level.

    Gates (in order):
    1. Staff bypass — ``is_staff`` accounts always pass.
    2. No requirement row for the stakes level → ungated, pass.
    3. Party average level below ``minimum_party_average_level`` → raise.
    4. GM level below ``minimum_gm_level`` → raise.

    GM level is read from ``gm_account.gm_profile.level`` (GMProfile,
    related_name ``gm_profile``).  When no ``gm_profile`` row exists a
    ``GMProfile.DoesNotExist`` is caught and the account's level index is
    treated as ``gm_level_index(GMLevel.STARTING)`` — i.e. a no-profile
    account fails any requirement row whose minimum is above STARTING, and
    passes rows whose minimum is STARTING.

    Args:
        encounter: The encounter whose ``stakes_level`` is checked.
        gm_account: The AccountDB of the GM requesting to run the encounter.

    Raises:
        StakesRequirementError: When the party level or GM level gate is unmet.
    """
    if gm_account.is_staff:
        return

    req = StakesLevelRequirement.objects.filter(stakes_level=encounter.stakes_level).first()
    if req is None:
        return

    avg = compute_party_profile(encounter).avg_level
    if avg < req.minimum_party_average_level:
        msg = (
            f"Party average level {avg:.1f} is below the required "
            f"{req.minimum_party_average_level} for {encounter.stakes_level} stakes."
        )
        raise StakesRequirementError(msg, user_message=msg)

    try:
        gm_level: str = gm_account.gm_profile.level
    except ObjectDoesNotExist:
        gm_level = GMLevel.STARTING

    account_level_index = gm_level_index(gm_level)
    required_level_index = gm_level_index(req.minimum_gm_level)
    if account_level_index < required_level_index:
        required_display = GMLevel(req.minimum_gm_level).label
        actual_display = GMLevel(gm_level).label
        msg = (
            f"GM level {actual_display} is below the required "
            f"{required_display} for {encounter.stakes_level} stakes."
        )
        raise StakesRequirementError(msg, user_message=msg)


def compute_party_multiplier(party_size: int, avg_level: float) -> Decimal:
    """Compute the party-size + level multiplier (ADR-0037).

    Shared by ``compute_opponent_stat_block`` and ``check_and_advance_boss_phase``
    (for break-bar threshold re-scaling at phase transition).
    """
    cfg = get_encounter_scaling_config()
    extra_members = max(0, party_size - cfg.baseline_party_size)
    return (
        Decimal(1)
        + cfg.per_extra_member_pct * Decimal(str(extra_members))
        + cfg.per_avg_level_pct * Decimal(str(avg_level))
    )


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
    resolved_party_size: int = party_size if party_size is not None else 0
    resolved_avg_level: float = avg_level if avg_level is not None else 0.0
    if party_size is None or avg_level is None:
        profile = compute_party_profile(encounter)
        if party_size is None:
            resolved_party_size = profile.party_size
        if avg_level is None:
            resolved_avg_level = profile.avg_level

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
            actions_per_round=tpl.base_actions_per_round,
            phases=(),
        )

    # Risk multiplier — fall back to 1.0 if the authored row is missing.
    try:
        risk_row = RiskScalingModifier.objects.get(risk_level=encounter.risk_level)
        risk_mult: Decimal = risk_row.multiplier
    except RiskScalingModifier.DoesNotExist:
        risk_mult = Decimal("1.0")

    party_mult = compute_party_multiplier(resolved_party_size, resolved_avg_level)

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
        actions_per_round=tpl.base_actions_per_round,
        phases=_build_boss_phases(tier, tpl.boss_phase_count, soak_value, probing_threshold),
    )
