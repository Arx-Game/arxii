"""Monte Carlo party-vs-boss combat simulator over the real engine (#1221 Task 5).

Drives ``world.combat.services.resolve_round`` — the exact same production
combat pipeline a live encounter uses — through repeated, fully-synthetic
party-vs-opponent encounters so a GM tuning dashboard can preview a win-rate
distribution for a candidate tier/risk-level/party combination *before*
touching live content. This module never reimplements combat math; every
round is resolved by calling the production services, with real dice
(``perform_check`` via the normal pipeline — never
``world.checks.test_helpers.force_check_outcome``).

Isolation contract (the entire point of this module):

1. The whole batch runs inside one ``transaction.atomic()``; each iteration
   runs inside its own nested savepoint (a second ``transaction.atomic()``)
   that is unwound by raising the internal ``_IterationRollback`` sentinel,
   caught immediately outside that savepoint so the iteration's rows roll
   back while the tally already captured in Python survives. At the very end
   the whole batch is unwound too (``_BatchRollback``) so even
   sequence-consuming outer work rolls back with it. **Nothing this module
   does is ever persisted.**
2. Every synthetic object (encounter, opponent, PCs) is built locationless
   (``room=None``): ``emit_event`` with ``location=None`` gathers zero
   triggers (``flows/emit.py:60-72``), and encounter completion skips its
   ``ENCOUNTER_COMPLETED`` emit when ``room is None`` (``services.py:4735``)
   — so no reactive flow/trigger side effects fire while combat resolves.
3. ``flush_cache()`` runs in a ``finally`` — the SharedMemoryModel identity
   map otherwise keeps stale rolled-back rows cached for the rest of the
   process (mirrors the precedent at ``actions/tests/test_cast_action.py:34``).
4. Only real dice are used through the normal combat pipeline; this module
   never calls ``force_check_outcome`` and never reinvents check/damage math
   — every round is resolved by ``world.combat.services.resolve_round``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from django.db import transaction
from evennia.utils.idmapper.models import flush_cache

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.combat import services
from world.combat.constants import EncounterOutcome, OpponentTier, ParticipantStatus, RiskLevel
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
    seed_scaling_defaults,
)
from world.combat.models import (
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CombatRoundAction,
)
from world.combat.scaling import compute_opponent_stat_block
from world.magic.factories import CharacterAnimaFactory, TechniqueFactory
from world.magic.models import Technique
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.vitals.models import CharacterVitals

# Ample vitals/anima so a party never starves mid-run for reasons unrelated to
# the boss fight itself (the simulator measures encounter risk, not resource
# attrition). Values are arbitrary but generous relative to a basic attack's
# anima_cost below.
_PC_HEALTH = 100
_PC_ANIMA = 30
_BASIC_ATTACK_ANIMA_COST = 3
_BASIC_ATTACK_BASE_DAMAGE = 10


class _IterationRollback(Exception):
    """Internal sentinel: unwind one simulated iteration's savepoint.

    Raised after an iteration's outcome has already been tallied in Python;
    caught immediately outside that iteration's ``transaction.atomic()`` so
    the rows the iteration created roll back without aborting the batch.
    """


class _BatchRollback(Exception):
    """Internal sentinel: unwind the whole simulated batch once every
    iteration has been tallied, so even outer setup (seeding calls) rolls back.
    """


@dataclass(frozen=True)
class SimulationParams:
    """Inputs for one Monte Carlo party-vs-boss simulation batch."""

    party_size: int = 4
    avg_level: int = 5
    tier: str = OpponentTier.BOSS
    risk_level: str = RiskLevel.MODERATE
    iterations: int = 50
    round_cap: int = 20


@dataclass(frozen=True)
class SimulationReport:
    """Tallied outcome distribution for a completed simulation batch."""

    params: SimulationParams
    iterations_run: int
    victories: int
    defeats: int
    stalemates: int
    win_rate: float
    round_counts: list[int]
    mean_rounds: float


def run_party_vs_boss_simulation(params: SimulationParams) -> SimulationReport:
    """Run ``params.iterations`` independent party-vs-opponent encounters and tally outcomes.

    Every iteration is built from scratch (fresh encounter, party, and
    opponent), driven through the real ``resolve_round`` pipeline until
    either side is wiped or ``params.round_cap`` rounds elapse (a
    stalemate). See the module docstring for the isolation contract; nothing
    this function does is ever persisted.
    """
    victories = 0
    defeats = 0
    stalemates = 0
    round_counts: list[int] = []

    try:
        with transaction.atomic():
            # Idempotent production seed helpers — safe to call every batch;
            # rolled back with everything else by the _BatchRollback below.
            seed_check_resolution_tables()
            seed_scaling_defaults()

            for _ in range(params.iterations):
                try:
                    with transaction.atomic():
                        outcome, rounds_used = _run_one_iteration(params)
                        round_counts.append(rounds_used)
                        if outcome is None:
                            stalemates += 1
                        elif outcome == EncounterOutcome.VICTORY:
                            victories += 1
                        else:
                            defeats += 1
                        raise _IterationRollback
                except _IterationRollback:
                    pass

            raise _BatchRollback
    except _BatchRollback:
        pass
    finally:
        flush_cache()

    iterations_run = victories + defeats + stalemates
    win_rate = victories / iterations_run if iterations_run else 0.0
    mean_rounds = sum(round_counts) / len(round_counts) if round_counts else 0.0

    return SimulationReport(
        params=params,
        iterations_run=iterations_run,
        victories=victories,
        defeats=defeats,
        stalemates=stalemates,
        win_rate=win_rate,
        round_counts=round_counts,
        mean_rounds=mean_rounds,
    )


def _run_one_iteration(params: SimulationParams) -> tuple[str | None, int]:
    """Run a single simulated party-vs-opponent combat to completion or the round cap.

    Returns ``(outcome, rounds_used)``. ``outcome`` is an ``EncounterOutcome``
    value, or ``None`` on a stalemate (the round cap was reached with the
    encounter still unresolved).
    """
    # FactoryBoy calls return model instances at runtime; ty sees the factory
    # class (factories.py is ty-excluded), hence the casts here and below.
    encounter = cast(
        "CombatEncounter",
        CombatEncounterFactory(
            room=None,
            risk_level=params.risk_level,
            status=RoundStatus.DECLARING,
            round_number=1,
        ),
    )
    participants = _build_party(encounter, params)
    opponent = _build_opponent(encounter, params)
    technique = _build_basic_attack_technique()

    outcome: str | None = None
    rounds_used = 0
    for round_index in range(params.round_cap):
        if round_index > 0:
            # begin_declaration_phase is the real round-advance seam (DoT
            # tick, engagement-ensure, pull expiry, etc.) — not a bare status
            # flip. Round 1 skips it: the encounter starts in DECLARING already.
            services.begin_declaration_phase(encounter)
            encounter.refresh_from_db()
        rounds_used = encounter.round_number

        for participant in participants:
            CombatRoundAction.objects.create(
                participant=participant,
                round_number=rounds_used,
                focused_action=technique,
                focused_opponent_target=opponent,
            )
        # select_npc_actions is the real opponent-AI selection service (weighted
        # random pick from the threat pool) — the same one a live encounter
        # uses; a passive opponent would make every run an automatic victory
        # and defeat the point of a win-rate simulator.
        services.select_npc_actions(encounter)

        services.resolve_round(encounter)

        if services._check_encounter_completion(encounter):  # noqa: SLF001
            outcome = services._classify_encounter_outcome(encounter)  # noqa: SLF001
            break

    return outcome, rounds_used


def _build_party(encounter: CombatEncounter, params: SimulationParams) -> list[CombatParticipant]:
    """Create ``params.party_size`` locationless PC participants for *encounter*."""
    participants: list[CombatParticipant] = []
    for _ in range(params.party_size):
        sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=sheet.character,
            level=params.avg_level,
            is_primary=True,
        )
        CharacterVitals.objects.create(
            character_sheet=sheet,
            health=_PC_HEALTH,
            max_health=_PC_HEALTH,
            base_max_health=_PC_HEALTH,
        )
        CharacterAnimaFactory(character=sheet.character, current=_PC_ANIMA, maximum=_PC_ANIMA)
        CharacterEngagementFactory(character=sheet.character)
        participants.append(
            cast(
                "CombatParticipant",
                CombatParticipantFactory(
                    encounter=encounter,
                    character_sheet=sheet,
                    status=ParticipantStatus.ACTIVE,
                ),
            )
        )
    return participants


def _build_opponent(encounter: CombatEncounter, params: SimulationParams) -> CombatOpponent:
    """Create the tier-scaled opponent for *encounter* from the real scaling formula."""
    block = compute_opponent_stat_block(
        params.tier,
        encounter,
        party_size=params.party_size,
        avg_level=float(params.avg_level),
    )
    pool = ThreatPoolFactory()
    ThreatPoolEntryFactory(pool=pool, base_damage=_BASIC_ATTACK_BASE_DAMAGE)
    return cast(
        "CombatOpponent",
        CombatOpponentFactory(
            encounter=encounter,
            tier=params.tier,
            health=block.max_health,
            max_health=block.max_health,
            soak_value=block.soak_value,
            probing_threshold=block.probing_threshold,
            swarm_count=block.swarm_count,
            max_swarm_count=block.swarm_count,
            body_toughness=block.body_toughness,
            bodies_per_attack=block.bodies_per_attack,
            barrier_strength=block.barrier_strength,
            threat_pool=pool,
        ),
    )


def _build_basic_attack_technique() -> Technique:
    """Create a minimal combat-ready technique for the party's basic attack.

    Mirrors the minimal recipe in ``test_clash_round_integration.py``: a bare
    ``ActionTemplate`` (auto-creates its own ``CheckType``) plus a Technique
    with an auto-seeded damage profile (from ``EffectType.base_power``) — real
    dice, real damage math, nothing hand-rolled.
    """
    return cast(
        "Technique",
        TechniqueFactory(
            anima_cost=_BASIC_ATTACK_ANIMA_COST,
            action_template=ActionTemplateFactory(),
        ),
    )
