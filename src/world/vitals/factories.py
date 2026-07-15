"""Factory definitions for the vitals system tests and seed data.

Includes:
- ``CharacterVitalsFactory`` — character vitals test data.
- ``create_bleed_out_terminal_pool()`` — seeds the bleed_out_terminal pool.
- ``create_abandonment_pools()`` — seeds all three abandonment pools.

The pool factories double as integration-test fixtures and seed data per
the repo convention (see CLAUDE.md "Factories as seed data").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import factory
import factory.django as factory_django

from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.constants import (
    POOL_ABANDONMENT_ENEMY,
    POOL_ABANDONMENT_ENVIRONMENTAL,
    POOL_ABANDONMENT_PVP,
    POOL_BLEED_OUT_TERMINAL,
    POOL_SURROUNDED_ENTRY,
    POOL_SURROUNDED_TERMINAL_ENEMY,
    POOL_SURROUNDED_TERMINAL_PVP,
    CharacterLifeState,
)
from world.vitals.models import CharacterVitals

if TYPE_CHECKING:
    from actions.models.consequence_pools import ConsequencePool

# Re-export pool constants so existing callers of factories.POOL_* keep working.
__all__ = [
    "POOL_ABANDONMENT_ENEMY",
    "POOL_ABANDONMENT_ENVIRONMENTAL",
    "POOL_ABANDONMENT_PVP",
    "POOL_BLEED_OUT_TERMINAL",
    "POOL_SURROUNDED_ENTRY",
    "POOL_SURROUNDED_TERMINAL_ENEMY",
    "POOL_SURROUNDED_TERMINAL_PVP",
    "CharacterVitalsFactory",
    "create_abandonment_pools",
    "create_bleed_out_terminal_pool",
    "create_dream_peril_pool",
    "ensure_surrounded_content",
]

# ---------------------------------------------------------------------------
# Outcome-tier label constants used across all peril pools.
# ---------------------------------------------------------------------------

_OUTCOME_FAILURE = "Failure"
_OUTCOME_PARTIAL = "Partial Success"
_OUTCOME_SUCCESS = "Success"


class CharacterVitalsFactory(factory_django.DjangoModelFactory):
    """Factory for creating CharacterVitals instances."""

    class Meta:
        model = CharacterVitals
        django_get_or_create = ("character_sheet",)

    character_sheet = factory.SubFactory(CharacterSheetFactory)
    life_state = CharacterLifeState.ALIVE
    health = 100
    max_health = 100
    base_max_health = 100


# ---------------------------------------------------------------------------
# Peril consequence pool factories (seed + test fixtures).
# ---------------------------------------------------------------------------


def _get_or_create_outcome(name: str, success_level: int):
    """Return a CheckOutcome with the given name, creating it if absent."""
    from world.traits.factories import CheckOutcomeFactory

    return CheckOutcomeFactory(name=name, success_level=success_level)


def _ensure_peril_category():
    """Return a ConditionCategory for incapacitation/peril conditions."""
    from world.conditions.models import ConditionCategory

    obj, _ = ConditionCategory.objects.get_or_create(
        name="Incapacitation",
        defaults={
            "description": ("Acute peril states: incapacitation that may escalate to death."),
            "is_negative": True,
        },
    )
    return obj


def _seed_pool_consequences(pool, consequence_specs) -> None:
    """Idempotently seed Consequence + ConsequencePoolEntry rows for a pool.

    Each ``ConsequencePoolEntry`` stores the pool-specific weight via
    ``weight_override`` so that pools with different weights for the same
    consequence label (e.g. ``die`` is weight=2 in abandonment_enemy but
    weight=1 in bleed_out_terminal) are resolved correctly.  The shared
    ``Consequence`` row's base ``weight`` is a sensible fallback; the actual
    weight used during resolution is always the pool entry's ``weight_override``
    (see ``_entry_to_weighted`` in ``actions/types.py``).

    Args:
        pool: ConsequencePool instance.
        consequence_specs: Iterable of (outcome_tier, label, weight, character_loss).
    """
    from actions.models import ConsequencePoolEntry
    from world.checks.models import Consequence

    for outcome_tier, label, weight, character_loss in consequence_specs:
        consequence, _ = Consequence.objects.get_or_create(
            outcome_tier=outcome_tier,
            label=label,
            defaults={"weight": weight, "character_loss": character_loss},
        )
        ConsequencePoolEntry.objects.get_or_create(
            pool=pool,
            consequence=consequence,
            defaults={"weight_override": weight, "is_excluded": False},
        )


def _seed_captured_alive_consequence(enemy_pool) -> None:
    """Idempotently seed the captured_alive Consequence + ConsequenceEffect on enemy_pool.

    ``captured_alive`` is a non-lethal survival outcome exclusive to the enemy
    abandonment pool — an NPC captor exists; PvP and environmental pools have no
    captor to receive the prisoner, so this entry must NOT be added there.

    The ConsequenceEffect wires the existing ``EffectType.CAPTURE`` handler
    (``_apply_capture`` in ``world/mechanics/effect_handlers.py``) with
    ``capture_offscreen_loss_allowed=False`` (the safe default — off-screen loss
    remains gated until #931 generalises enforcement).  The captor organization
    is left unset (None): the routine pool-level capture uses no named captor.
    """
    from actions.models import ConsequencePoolEntry
    from world.checks.constants import EffectTarget, EffectType
    from world.checks.models import Consequence, ConsequenceEffect

    partial = _get_or_create_outcome(_OUTCOME_PARTIAL, success_level=0)

    consequence, _ = Consequence.objects.get_or_create(
        outcome_tier=partial,
        label="captured_alive",
        defaults={"weight": 2, "character_loss": False},
    )
    ConsequencePoolEntry.objects.get_or_create(
        pool=enemy_pool,
        consequence=consequence,
        defaults={"weight_override": 2, "is_excluded": False},
    )
    # Wire the existing CAPTURE handler — no new EffectType needed.
    ConsequenceEffect.objects.get_or_create(
        consequence=consequence,
        effect_type=EffectType.CAPTURE,
        execution_order=0,
        defaults={
            "target": EffectTarget.SELF,
            "capture_offscreen_loss_allowed": False,
        },
    )


def create_bleed_out_terminal_pool():
    """Create (or return existing) the bleed_out_terminal ConsequencePool.

    Outcomes authored:
    - ``recover`` (Success tier, weight=2): character stabilises and
      recovers from the dying state.
    - ``stay_incapacitated`` (Partial Success tier, weight=3): character
      no longer actively bleeds out but remains incapacitated.
    - ``die`` (Failure tier, weight=1, character_loss=True): character
      dies — only reachable when death_is_permitted (T5 gates this).

    ConsequenceEffect rows (REMOVE_CONDITION for recover/stay_incapacitated,
    mark-dead for die) are NOT authored here because the mechanical
    application is owned by Task 5 (advance_bleed_out rewrite).  No existing
    EffectType covers "mark character dead", so that branch is left entirely
    to T5. REMOVE_CONDITION exists but is wired through advance_bleed_out's
    apply_resolution call rather than being baked into the pool entries — T5
    decides the exact wiring.

    Returns the ConsequencePool instance (safe to call multiple times —
    uses get_or_create throughout).
    """
    from actions.models import ConsequencePool

    pool, _ = ConsequencePool.objects.get_or_create(
        name=POOL_BLEED_OUT_TERMINAL,
        defaults={
            "description": (
                "Terminal bleed-out resolution: the character is at the final stage"
                " of Bleeding Out and must stabilise, remain incapacitated, or die."
            )
        },
    )

    failure = _get_or_create_outcome(_OUTCOME_FAILURE, success_level=-1)
    partial = _get_or_create_outcome(_OUTCOME_PARTIAL, success_level=0)
    success = _get_or_create_outcome(_OUTCOME_SUCCESS, success_level=1)

    _seed_pool_consequences(
        pool,
        [
            (success, "recover", 2, False),
            (partial, "stay_incapacitated", 3, False),
            (failure, "die", 1, True),
        ],
    )

    return pool


def create_abandonment_pools() -> dict[str, ConsequencePool]:
    """Create (or return existing) the three abandonment ConsequencePools.

    Pools and their intended use:
    - ``abandonment_enemy``: NPC (enemy) source abandons the downed victim.
      Higher die weight reflects greater peril from a hostile NPC context.
      Task 6 will add a ``captured_alive`` consequence to this pool.
    - ``abandonment_pvp``: PC source abandons the victim.  ADR-0023: PvP is
      non-lethal, so the ``die`` row exists but is filtered by
      filter_character_loss + death_is_permitted at resolution time.
    - ``abandonment_environmental``: No source (environmental hazard, etc.).
      Moderate danger.

    All three pools share the same three outcome labels:
    - ``recover`` (Success): character is found/helped in time.
    - ``stay_incapacitated`` (Partial Success): character stabilises but
      remains unable to act.
    - ``die`` (Failure, character_loss=True): only reachable when
      death_is_permitted (T5 enforces the gate).

    Returns a dict mapping pool name → ConsequencePool.
    """
    from actions.models import ConsequencePool

    failure = _get_or_create_outcome(_OUTCOME_FAILURE, success_level=-1)
    partial = _get_or_create_outcome(_OUTCOME_PARTIAL, success_level=0)
    success = _get_or_create_outcome(_OUTCOME_SUCCESS, success_level=1)

    pool_specs = {
        POOL_ABANDONMENT_ENEMY: {
            "description": (
                "Abandonment resolution when the source is a non-PC (enemy) attacker."
                " Includes a captured-alive outcome (wired by Task 6)."
            ),
            "consequences": [
                (success, "recover", 2, False),
                (partial, "stay_incapacitated", 2, False),
                (failure, "die", 2, True),
            ],
        },
        POOL_ABANDONMENT_PVP: {
            "description": (
                "Abandonment resolution when the source is a player character."
                " ADR-0023: die row exists but is filtered by death_is_permitted."
            ),
            "consequences": [
                (success, "recover", 2, False),
                (partial, "stay_incapacitated", 3, False),
                (failure, "die", 1, True),
            ],
        },
        POOL_ABANDONMENT_ENVIRONMENTAL: {
            "description": (
                "Abandonment resolution when there is no source"
                " (environmental hazard, unconscious collapse, etc.)."
            ),
            "consequences": [
                (success, "recover", 2, False),
                (partial, "stay_incapacitated", 2, False),
                (failure, "die", 1, True),
            ],
        },
    }

    pools: dict[str, ConsequencePool] = {}
    for pool_name, spec in pool_specs.items():
        pool, _ = ConsequencePool.objects.get_or_create(
            name=pool_name,
            defaults={"description": spec["description"]},
        )
        _seed_pool_consequences(pool, spec["consequences"])
        pools[pool_name] = pool

    # Wire the captured_alive CAPTURE effect onto the enemy pool only — NPC captors
    # exist there; PvP and environmental pools have no captor to receive the prisoner.
    _seed_captured_alive_consequence(pools[POOL_ABANDONMENT_ENEMY])

    return pools


def create_dream_peril_pool():
    """Create (or return existing) the dream_peril ConsequencePool (#2290).

    Outcomes authored:
    - ``wake_shaken`` (Success tier, weight=3, no character_loss): character
      wakes, mental fatigue partially resets, minor temporary debuff.
    - ``nightmares`` (Partial Success tier, weight=2, no character_loss): a
      persistent Nightmares condition applied to the waking character.
    - ``madness`` (Partial Success tier, weight=1, no character_loss): a
      severe persistent Madness condition (behavior-altering).
    - ``die`` (Failure tier, weight=1, character_loss=True): physical death
      — the dreamer's body dies. Only reachable when death_is_permitted
      (environmental/deep-dreaming sources; excluded for PC sources per
      ADR-0023).

    Returns the ConsequencePool instance (safe to call multiple times —
    uses get_or_create throughout).
    """
    from actions.models import ConsequencePool
    from world.vitals.constants import POOL_DREAM_PERIL

    pool, _ = ConsequencePool.objects.get_or_create(
        name=POOL_DREAM_PERIL,
        defaults={
            "description": (
                "Dream peril resolution: a dreamer's mental fatigue has"
                " collapsed. They may wake shaken, suffer nightmares,"
                " descend into madness, or die — their body lost in the"
                " deep dreaming."
            ),
        },
    )

    failure = _get_or_create_outcome(_OUTCOME_FAILURE, success_level=-1)
    partial = _get_or_create_outcome(_OUTCOME_PARTIAL, success_level=0)
    success = _get_or_create_outcome(_OUTCOME_SUCCESS, success_level=1)

    _seed_pool_consequences(
        pool,
        [
            (success, "wake_shaken", 3, False),
            (partial, "nightmares", 2, False),
            (partial, "madness", 1, False),
            (failure, "die", 1, True),
        ],
    )

    return pool


def ensure_surrounded_content() -> dict[str, object]:
    """Idempotently seed the "Surrounded" battle acute-peril condition + its 3 pools.

    (#1733)

    Reuses the existing Endurance CheckType (``_ensure_endurance_check_type``) for
    every stage's resist check — holding against a surrounding attack wave is the
    same survivability semantic Bleeding-Out already uses. See the module docstring
    of ``world/battles/resolution.py`` for how the entry roll and per-round
    escalation consume this content.

    Returns a dict with keys "condition" (ConditionTemplate), "stages" (list of
    the 3 ConditionStage rows ordered by stage_order), and "pools" (dict of the 3
    ConsequencePool rows keyed by name).
    """
    from actions.models import ConsequencePool
    from world.conditions.constants import SURROUNDED_CONDITION_NAME
    from world.conditions.models import ConditionStage, ConditionTemplate
    from world.vitals.services import _ensure_endurance_check_type

    check_type = _ensure_endurance_check_type()
    category = _ensure_peril_category()

    condition, _ = ConditionTemplate.objects.get_or_create(
        name=SURROUNDED_CONDITION_NAME,
        defaults={
            "category": category,
            "has_progression": True,
            "description": "Cut off from allies, facing mounting attack pressure.",
        },
    )

    stage_specs = [
        (1, "Encircled", 15),
        (2, "Overwhelmed", 25),
        (3, "Being Cut Down", 35),
    ]
    stages = []
    for order, name, difficulty in stage_specs:
        stage, _ = ConditionStage.objects.get_or_create(
            condition=condition,
            stage_order=order,
            defaults={
                "name": name,
                "description": f"{name} — resisting being surrounded.",
                "resist_check_type": check_type,
                "resist_difficulty": difficulty,
                "rounds_to_next": 1,
            },
        )
        stages.append(stage)

    failure = _get_or_create_outcome(_OUTCOME_FAILURE, success_level=-1)
    partial = _get_or_create_outcome(_OUTCOME_PARTIAL, success_level=0)
    success = _get_or_create_outcome(_OUTCOME_SUCCESS, success_level=1)

    entry_pool, _ = ConsequencePool.objects.get_or_create(
        name=POOL_SURROUNDED_ENTRY,
        defaults={
            "description": ("Whether an isolated declaration failure results in Surrounded.")
        },
    )
    _seed_pool_consequences(
        entry_pool,
        [
            (success, "no_effect", 3, False),
            (partial, "no_effect", 3, False),
            (failure, "surrounded", 2, False),
        ],
    )

    enemy_pool, _ = ConsequencePool.objects.get_or_create(
        name=POOL_SURROUNDED_TERMINAL_ENEMY,
        defaults={"description": "Surrounded terminal resolution — non-PC isolating side."},
    )
    _seed_pool_consequences(
        enemy_pool,
        [
            (success, "recover", 2, False),
            (partial, "stay_incapacitated", 2, False),
            (failure, "die", 2, True),
        ],
    )

    pvp_pool, _ = ConsequencePool.objects.get_or_create(
        name=POOL_SURROUNDED_TERMINAL_PVP,
        defaults={
            "description": (
                "Surrounded terminal resolution — PC isolating side (ADR-0023). No"
                " die row at all: structurally non-lethal, not filtered-at-resolution."
            )
        },
    )
    _seed_pool_consequences(
        pvp_pool,
        [
            (success, "recover", 2, False),
            (partial, "stay_incapacitated", 3, False),
        ],
    )

    return {
        "condition": condition,
        "stages": stages,
        "pools": {
            POOL_SURROUNDED_ENTRY: entry_pool,
            POOL_SURROUNDED_TERMINAL_ENEMY: enemy_pool,
            POOL_SURROUNDED_TERMINAL_PVP: pvp_pool,
        },
    }
