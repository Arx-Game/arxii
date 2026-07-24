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
5. Existing scaling tuning is ALWAYS respected: ``seed_scaling_defaults()`` is
   only called when ``EncounterScalingConfig`` has no rows at all (a fresh/
   unseeded dev DB). Once scaling config exists — including a GM's live
   tuning edits — this module never overwrites it. A tuning-preview tool that
   silently reset the very tuning it's supposed to preview would defeat its
   own purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
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
    EncounterScalingConfig,
)
from world.combat.scaling import compute_opponent_stat_block
from world.magic.factories import CharacterAnimaFactory, TechniqueFactory
from world.magic.models import Technique
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.vitals.models import CharacterVitals

# Ample vitals so a party never starves mid-run for reasons unrelated to the
# boss fight itself (the simulator measures encounter risk, not resource
# attrition). _PC_ANIMA is not sized to outlast round_cap rounds of basic
# attacks (30 / 3 per round = 10 rounds, less than the default round_cap=20)
# — that's fine because resolve_round's path never gates an action on the
# actor's current anima pool; technique.anima_cost only feeds apply_fatigue
# (services.py's per-action fatigue accrual), so a "low" anima pool can never
# hard-block a basic attack. The value just needs to be nonzero/plausible.
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
    combo_rate: float = 0.0


@dataclass(frozen=True)
class SimulationReport:
    """Tallied outcome distribution for a completed simulation batch.

    ``opponent_max_health`` is the scaled ``max_health`` used for the opponent
    in the last iteration run (all iterations share the same params, so this
    is deterministic across the batch). It reflects whatever tier tuning was
    live in the DB at run time — see the module docstring's isolation
    contract point 5.
    """

    params: SimulationParams
    iterations_run: int
    victories: int
    defeats: int
    stalemates: int
    win_rate: float
    round_counts: list[int]
    mean_rounds: float
    opponent_max_health: int


def run_party_vs_boss_simulation(params: SimulationParams) -> SimulationReport:
    """Run ``params.iterations`` independent party-vs-opponent encounters and tally outcomes.

    Every iteration is built from scratch (fresh encounter, party, and
    opponent), driven through the real ``resolve_round`` pipeline until
    either side is wiped or ``params.round_cap`` rounds elapse (a
    stalemate). See the module docstring for the isolation contract; nothing
    this function does is ever persisted.

    Existing scaling tuning rows are ALWAYS respected: defaults are seeded
    only when ``EncounterScalingConfig`` is entirely absent (see the module
    docstring's isolation contract point 5).
    """
    victories = 0
    defeats = 0
    stalemates = 0
    round_counts: list[int] = []

    opponent_max_health = 0

    try:
        with transaction.atomic():
            # Idempotent production seed helper — safe to call every batch;
            # rolled back with everything else by the _BatchRollback below.
            seed_check_resolution_tables()
            # Scaling config is seeded ONLY when entirely absent (fresh/unseeded
            # dev DB). `seed_scaling_defaults()` uses `update_or_create` at every
            # layer, so calling it unconditionally would RESET any GM's live
            # tuning of OpponentTierTemplate / RiskScalingModifier /
            # EncounterScalingConfig back to hardcoded defaults before this
            # batch's opponents are scaled — silently misrepresenting actual
            # game balance in a tool whose entire purpose is to preview it.
            if not EncounterScalingConfig.objects.exists():
                seed_scaling_defaults()

            for _ in range(params.iterations):
                try:
                    with transaction.atomic():
                        outcome, rounds_used, iteration_opponent_max_health = _run_one_iteration(
                            params
                        )
                        round_counts.append(rounds_used)
                        opponent_max_health = iteration_opponent_max_health
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
        opponent_max_health=opponent_max_health,
    )


def _run_one_iteration(params: SimulationParams) -> tuple[str | None, int, int]:
    """Run a single simulated party-vs-opponent combat to completion or the round cap.

    Returns ``(outcome, rounds_used, opponent_max_health)``. ``outcome`` is an
    ``EncounterOutcome`` value, or ``None`` on a stalemate (the round cap was
    reached with the encounter still unresolved). ``opponent_max_health`` is
    the scaled stat block's ``max_health`` actually used for this iteration's
    opponent — read before the iteration's savepoint rolls back.
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
        # select_npc_actions is the production-grade opponent-AI selection
        # service (weighted random pick from the threat pool) and the only
        # creator of CombatOpponentAction rows; live-encounter wiring for it
        # has not been demonstrated. A passive opponent would make every run
        # an automatic victory and defeat the point of a win-rate simulator.
        services.select_npc_actions(encounter)

        services.resolve_round(encounter)

        # Break-bar simulation: if combo_rate > 0, model a landed combo
        # by directly damaging the bar (the synthetic party can't actually
        # combo — it uses a single basic attack technique).
        if (
            hasattr(opponent, "break_bar_threshold")
            and opponent.break_bar_threshold > 0
            and opponent.vulnerability_rounds_remaining == 0
            and random.random() < params.combo_rate  # noqa: S311
        ):
            opponent.break_bar_current = max(0, opponent.break_bar_current - 10)
            if opponent.break_bar_current == 0:
                opponent.vulnerability_rounds_remaining = opponent.vulnerability_rounds
            opponent.save(
                update_fields=[
                    "break_bar_current",
                    "vulnerability_rounds_remaining",
                ]
            )

        if services._check_encounter_completion(encounter):  # noqa: SLF001
            outcome = services._classify_encounter_outcome(encounter)  # noqa: SLF001
            break

    return outcome, rounds_used, opponent.max_health


def _build_party(encounter: CombatEncounter, params: SimulationParams) -> list[CombatParticipant]:
    """Create ``params.party_size`` locationless PC participants for *encounter*."""
    participants: list[CombatParticipant] = []
    for _ in range(params.party_size):
        sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=sheet,
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
