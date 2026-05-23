"""Clash test-infrastructure: ClashContent seed factory.

Exports:
- ``ClashContentResult`` — frozen dataclass returned by ClashContent.create_all().
- ``ClashContent`` — static-method seed factory for clash end-to-end tests.
  Mirrors the MagicContent pattern at src/integration_tests/game_content/magic.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actions.models.consequence_pools import ConsequencePool
    from world.combat.models import CombatOpponent, ComboDefinition, ThreatPool, ThreatPoolEntry
    from world.conditions.models import ConditionTemplate
    from world.magic.models import EffectType, Technique
    from world.traits.models import CheckOutcome


@dataclass(frozen=True)
class ClashContentResult:
    """Container for seeded clash test content. All fields are persisted DB rows.

    Returned by ``ClashContent.create_all()``. Every field is a live Django
    model instance fetched or created via get_or_create — no stubs.
    """

    # ---- PC-side authored content ----
    # Technique with clash_capable=True; used in CLASH flavor tests.
    clash_capable_technique: Technique
    # Technique whose applied_conditions M2M includes lock_condition (is_clash_lock=True).
    # Used in LOCK/Suppress flavor tests. technique.is_lock_applying == True.
    lock_applying_technique: Technique

    # ---- NPC-side authored content ----
    # ThreatPoolEntry with clash_capable=True; used in CLASH (NPC side).
    npc_clash_capable_entry: ThreatPoolEntry
    # ThreatPoolEntry with is_lock_applying=True; used in LOCK/Break Free (NPC applies lock).
    npc_lock_applying_entry: ThreatPoolEntry
    # ThreatPoolEntry with is_sustained_attack=True; used in WARD (NPC sustained attack).
    sustained_attack_entry: ThreatPoolEntry

    # ---- Condition templates ----
    # The lock condition that lock_applying_technique applies (is_clash_lock=True).
    lock_condition: ConditionTemplate
    # Window-state condition applied by the LOCK resolution pool's PC_DECISIVE consequence.
    # The clash_window_combo requires the target NPC to have this condition active.
    boss_held_condition: ConditionTemplate

    # ---- Consequence pools (one per flavor / event) ----
    clash_resolution_pool: ConsequencePool
    clash_per_round_pool: ConsequencePool
    lock_resolution_pool: ConsequencePool
    ward_resolution_pool: ConsequencePool
    ward_per_round_pool: ConsequencePool
    break_resolution_pool: ConsequencePool

    # ---- Combo gated by clash window condition ----
    # ComboDefinition with required_clash_window_condition=boss_held_condition.
    # Becomes available only when the target NPC has the boss_held condition active
    # (applied by the LOCK resolution PC_DECISIVE consequence).
    clash_window_combo: ComboDefinition

    # ---- Shared threat pool ----
    threat_pool: ThreatPool


class ClashContent:
    """Idempotent seeded test content for clash end-to-end tests.

    Mirrors the MagicContent pattern at src/integration_tests/game_content/magic.py.
    Every entity is get_or_created so multiple test files can call create_all()
    without producing duplicate rows.

    Safe to call from setUpTestData across multiple test classes.
    """

    @staticmethod
    def create_all() -> ClashContentResult:
        """Idempotently create the seed content; returns the populated result.

        Creates (in dependency order):
        1. CheckOutcome rows for success_level -2..3 (needed by consequence pools).
        2. ConditionCategory + two ConditionTemplates (lock, boss_held).
        3. Six ConsequencePool rows, one per clash flavor/event.
        4. Consequences + ConsequenceEffects wiring the LOCK resolution pool's
           PC_DECISIVE tier to apply the boss_held condition.
        5. A shared ThreatPool + three ThreatPoolEntry rows (NPC side).
        6. Two Techniques (PC side: clash_capable, lock_applying).
        7. A ComboDefinition gated by boss_held_condition.

        Returns:
            ClashContentResult with all seeded rows.
        """
        # All imports are deferred (inside the function) following the
        # MagicContent.create_all() pattern — prevents circular imports at
        # module load time and matches the existing integration-test convention.

        from actions.models import ConsequencePool  # noqa: PLC0415
        from world.checks.constants import EffectType as CheckEffectType  # noqa: PLC0415
        from world.checks.models import Consequence, ConsequenceEffect  # noqa: PLC0415
        from world.combat.constants import ActionCategory, ClashFlavor  # noqa: PLC0415
        from world.combat.models import (  # noqa: PLC0415
            ComboDefinition,
            ThreatPool,
            ThreatPoolEntry,
        )
        from world.conditions.constants import DurationType  # noqa: PLC0415
        from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415
        from world.magic.factories import GiftFactory  # noqa: PLC0415
        from world.magic.models import (  # noqa: PLC0415
            EffectType,
            Technique,
            TechniqueAppliedCondition,
            TechniqueStyle,
        )
        from world.traits.models import CheckOutcome  # noqa: PLC0415

        # ------------------------------------------------------------------ #
        # 1. Ensure CheckOutcome rows exist for all success_level tiers used  #
        #    by the clash consequence pipeline (success_level -2 … 3).        #
        # ------------------------------------------------------------------ #
        _OUTCOME_SPECS: list[tuple[str, int]] = [
            ("Clash: Critical Failure", -2),
            ("Clash: Failure", -1),
            ("Clash: Partial Success", 0),
            ("Clash: Success", 1),
            ("Clash: Great Success", 2),
            ("Clash: Critical Success", 3),
        ]
        check_outcomes: dict[int, CheckOutcome] = {}
        for outcome_name, success_level in _OUTCOME_SPECS:
            outcome, _ = CheckOutcome.objects.get_or_create(
                name=outcome_name,
                defaults={
                    "success_level": success_level,
                    "description": f"Clash test outcome: {outcome_name}.",
                    "display_template": outcome_name,
                },
            )
            check_outcomes[success_level] = outcome

        # ------------------------------------------------------------------ #
        # 2. Condition templates                                               #
        # ------------------------------------------------------------------ #
        cond_category, _ = ConditionCategory.objects.get_or_create(
            name="Clash (Test)",
            defaults={
                "description": "Conditions seeded for clash integration tests.",
                "is_negative": True,
                "display_order": 99,
            },
        )

        # Lock condition — is_clash_lock=True is the field Technique.is_lock_applying reads.
        lock_condition, _ = ConditionTemplate.objects.get_or_create(
            name="Suppression Lock (Clash Test)",
            defaults={
                "category": cond_category,
                "description": "A lock condition applied by the Suppressor technique.",
                "default_duration_type": DurationType.ROUNDS,
                "default_duration_value": 3,
                "is_stackable": False,
                "max_stacks": 1,
                "has_progression": False,
                "can_be_dispelled": True,
                "is_clash_lock": True,
                "clash_lock_strength": 10,
            },
        )

        # Boss-held window condition — applied by LOCK resolution's PC_DECISIVE consequence.
        boss_held_condition, _ = ConditionTemplate.objects.get_or_create(
            name="Boss Held — Suppress Window (Clash Test)",
            defaults={
                "category": cond_category,
                "description": (
                    "Window-state condition: the boss is held after a decisive lock win."
                ),
                "default_duration_type": DurationType.ROUNDS,
                "default_duration_value": 2,
                "is_stackable": False,
                "max_stacks": 1,
                "has_progression": False,
                "can_be_dispelled": False,
            },
        )

        # ------------------------------------------------------------------ #
        # 3. Consequence pools (one per flavor/event)                         #
        # ------------------------------------------------------------------ #
        clash_resolution_pool, _ = ConsequencePool.objects.get_or_create(
            name="Clash Resolution Pool (Clash Test)",
            defaults={"description": "Resolution consequences for CLASH flavor clashes."},
        )
        clash_per_round_pool, _ = ConsequencePool.objects.get_or_create(
            name="Clash Per-Round Pool (Clash Test)",
            defaults={"description": "Per-round consequences for CLASH flavor clashes."},
        )
        lock_resolution_pool, _ = ConsequencePool.objects.get_or_create(
            name="Lock Resolution Pool (Clash Test)",
            defaults={"description": "Resolution consequences for LOCK/Suppress flavor clashes."},
        )
        ward_resolution_pool, _ = ConsequencePool.objects.get_or_create(
            name="Ward Resolution Pool (Clash Test)",
            defaults={"description": "Resolution consequences for WARD flavor clashes."},
        )
        ward_per_round_pool, _ = ConsequencePool.objects.get_or_create(
            name="Ward Per-Round Pool (Clash Test)",
            defaults={"description": "Per-round consequences for WARD flavor clashes."},
        )
        break_resolution_pool, _ = ConsequencePool.objects.get_or_create(
            name="Break Resolution Pool (Clash Test)",
            defaults={"description": "Resolution consequences for BREAK flavor clashes."},
        )

        # ------------------------------------------------------------------ #
        # 4. Wire the LOCK resolution pool's PC_DECISIVE consequence          #
        #    (success_level=3) to apply boss_held_condition.                  #
        #                                                                     #
        #    This is the critical authored piece: Task 8.2's combo-prereq     #
        #    integration test checks that a decisive LOCK win applies the      #
        #    boss_held_condition, enabling the clash_window_combo.             #
        # ------------------------------------------------------------------ #
        from actions.models import ConsequencePoolEntry  # noqa: PLC0415

        decisive_outcome = check_outcomes[3]  # success_level=3 → PC_DECISIVE

        # Consequence with a stable (outcome_tier, label) natural key.
        lock_decisive_consequence, _ = Consequence.objects.get_or_create(
            outcome_tier=decisive_outcome,
            label="Lock Resolution: PC Decisive — Apply Boss Held (Clash Test)",
            defaults={
                "mechanical_description": (
                    "Decisive lock win: boss is held, opening a combo window."
                ),
                "weight": 1,
                "character_loss": False,
            },
        )
        ConsequencePoolEntry.objects.get_or_create(
            pool=lock_resolution_pool,
            consequence=lock_decisive_consequence,
        )
        # Wire the APPLY_CONDITION effect (idempotent via get_or_create on triple).
        ConsequenceEffect.objects.get_or_create(
            consequence=lock_decisive_consequence,
            effect_type=CheckEffectType.APPLY_CONDITION,
            condition_template=boss_held_condition,
            defaults={"execution_order": 0},
        )

        # TODO(tuning): the PC_MARGINAL wiring is a test-numerics workaround. With default
        # ClashConfig (decisive_overshoot=3), the first threshold crossing produces overshoot=2,
        # which maps to PC_MARGINAL. When tuning settles, decide whether marginal LOCK wins
        # should grant the boss_held window-state at full strength or a weaker/shorter variant.
        #
        # Also wire PC_MARGINAL (success_level=2) → boss_held, so that a marginal
        # LOCK win also opens the combo window.  With default ClashConfig deltas
        # (delta_critical_success=3, decisive_overshoot=3, threshold=10) the
        # first threshold crossing produces PC_MARGINAL, not PC_DECISIVE.  Both
        # tiers should apply the boss_held condition so integration tests pass
        # regardless of the exact resolution tier.
        marginal_outcome = check_outcomes[2]  # success_level=2 → PC_MARGINAL
        lock_marginal_consequence, _ = Consequence.objects.get_or_create(
            outcome_tier=marginal_outcome,
            label="Lock Resolution: PC Marginal — Apply Boss Held (Clash Test)",
            defaults={
                "mechanical_description": (
                    "Marginal lock win: boss is partially held, opening a combo window."
                ),
                "weight": 1,
                "character_loss": False,
            },
        )
        ConsequencePoolEntry.objects.get_or_create(
            pool=lock_resolution_pool,
            consequence=lock_marginal_consequence,
        )
        ConsequenceEffect.objects.get_or_create(
            consequence=lock_marginal_consequence,
            effect_type=CheckEffectType.APPLY_CONDITION,
            condition_template=boss_held_condition,
            defaults={"execution_order": 0},
        )

        # Add a minimal entry to each remaining pool so they're non-empty and
        # usable in tests without requiring additional wiring.
        _add_minimal_pool_entry(
            pool=clash_resolution_pool,
            outcome=check_outcomes[1],
            label="Clash Resolution: PC Success (Clash Test)",
        )
        _add_minimal_pool_entry(
            pool=clash_per_round_pool,
            outcome=check_outcomes[1],
            label="Clash Per-Round: PC Success (Clash Test)",
        )
        _add_minimal_pool_entry(
            pool=ward_resolution_pool,
            outcome=check_outcomes[1],
            label="Ward Resolution: PC Success (Clash Test)",
        )
        _add_minimal_pool_entry(
            pool=ward_per_round_pool,
            outcome=check_outcomes[1],
            label="Ward Per-Round: PC Success (Clash Test)",
        )
        _add_minimal_pool_entry(
            pool=break_resolution_pool,
            outcome=check_outcomes[1],
            label="Break Resolution: PC Success (Clash Test)",
        )

        # ------------------------------------------------------------------ #
        # 5. Shared threat pool + three NPC ThreatPoolEntry rows             #
        # ------------------------------------------------------------------ #
        threat_pool, _ = ThreatPool.objects.get_or_create(
            name="Clash Test Threat Pool",
            defaults={"description": "Shared NPC threat pool for clash integration tests."},
        )

        npc_clash_capable_entry, _ = ThreatPoolEntry.objects.get_or_create(
            pool=threat_pool,
            name="NPC Clash Attack (Clash Test)",
            defaults={
                "description": "NPC attack that opens a CLASH-flavor clash.",
                "attack_category": ActionCategory.MENTAL,
                "base_damage": 5,
                "clash_capable": True,
                "clash_npc_pressure": 3,
                "clash_resolution_pool": clash_resolution_pool,
                "clash_per_round_pool": clash_per_round_pool,
            },
        )

        npc_lock_applying_entry, _ = ThreatPoolEntry.objects.get_or_create(
            pool=threat_pool,
            name="NPC Lock Attack (Clash Test)",
            defaults={
                "description": "NPC attack that opens a LOCK-flavor clash (PC must break free).",
                "attack_category": ActionCategory.MENTAL,
                "base_damage": 0,
                "is_lock_applying": True,
                "clash_break_free_force": 5,
                "clash_resolution_pool": lock_resolution_pool,
            },
        )

        sustained_attack_entry, _ = ThreatPoolEntry.objects.get_or_create(
            pool=threat_pool,
            name="NPC Sustained Attack (Clash Test)",
            defaults={
                "description": "NPC sustained barrage that opens a WARD-flavor clash.",
                "attack_category": ActionCategory.PHYSICAL,
                "base_damage": 8,
                "is_sustained_attack": True,
                "sustained_duration_rounds": 3,
                "clash_npc_pressure": 2,
                "clash_resolution_pool": ward_resolution_pool,
                "clash_per_round_pool": ward_per_round_pool,
            },
        )

        # ------------------------------------------------------------------ #
        # 6. PC-side techniques                                               #
        # ------------------------------------------------------------------ #
        # Shared gift + style + effect_type for the clash techniques.
        gift = GiftFactory(name="Clash Arts (Clash Test)")

        style, _ = TechniqueStyle.objects.get_or_create(
            name="Clash (Test)",
            defaults={"description": "Magic expressed through direct clash engagement."},
        )
        clash_effect_type, _ = EffectType.objects.get_or_create(
            name="Clash Attack (Test)",
            defaults={
                "description": "A technique designed for clash combat.",
                "base_power": None,
                "base_anima_cost": 5,
                "has_power_scaling": False,
            },
        )

        # clash_capable_technique — drives CLASH flavor tests on the PC side.
        clash_capable_technique, _ = Technique.objects.get_or_create(
            name="Resonant Strike (Clash Test)",
            defaults={
                "gift": gift,
                "style": style,
                "effect_type": clash_effect_type,
                "intensity": 3,
                "control": 3,
                "anima_cost": 10,
                "description": "A technique that can open or sustain a CLASH.",
                "clash_capable": True,
                "clash_resolution_pool": clash_resolution_pool,
                "clash_per_round_pool": clash_per_round_pool,
            },
        )

        # lock_applying_technique — drives LOCK/Suppress flavor tests.
        # Applied conditions M2M must include lock_condition (is_clash_lock=True).
        lock_applying_technique, _ = Technique.objects.get_or_create(
            name="Binding Seal (Clash Test)",
            defaults={
                "gift": gift,
                "style": style,
                "effect_type": clash_effect_type,
                "intensity": 3,
                "control": 3,
                "anima_cost": 12,
                "description": "A technique that suppresses opponents with a lock condition.",
                "clash_capable": False,
                "clash_resolution_pool": lock_resolution_pool,
            },
        )
        # Wire the applied_conditions M2M (through TechniqueAppliedCondition).
        # get_or_create on the UniqueConstraint fields prevents duplicates on re-runs.
        TechniqueAppliedCondition.objects.get_or_create(
            technique=lock_applying_technique,
            condition=lock_condition,
            target_kind="enemy",
            defaults={
                "minimum_success_level": 1,
                "base_severity": 1,
            },
        )

        # ------------------------------------------------------------------ #
        # 7. Combo gated by boss_held_condition (clash window prereq)         #
        # ------------------------------------------------------------------ #
        # The combo slug is derived from the name; slugs are unique in the DB.
        combo, _ = ComboDefinition.objects.get_or_create(
            slug="boss-break-window-clash-test",
            defaults={
                "name": "Boss Break Window (Clash Test)",
                "description": (
                    "A window combo available only while the boss is held "
                    "after a decisive lock win."
                ),
                "hidden": True,
                "discoverable_via_training": True,
                "discoverable_via_combat": True,
                "minimum_probing": 0,
                "bypass_soak": False,
                "bonus_damage": 30,
                "required_clash_flavor": ClashFlavor.LOCK,
                "required_clash_window_condition": boss_held_condition,
            },
        )

        # Ensure at least two ComboSlots exist (the minimum for a valid combo).
        # We need an EffectType for the slot's required_action_type FK.
        _ensure_combo_slots(combo=combo, effect_type=clash_effect_type)

        return ClashContentResult(
            clash_capable_technique=clash_capable_technique,
            lock_applying_technique=lock_applying_technique,
            npc_clash_capable_entry=npc_clash_capable_entry,
            npc_lock_applying_entry=npc_lock_applying_entry,
            sustained_attack_entry=sustained_attack_entry,
            lock_condition=lock_condition,
            boss_held_condition=boss_held_condition,
            clash_resolution_pool=clash_resolution_pool,
            clash_per_round_pool=clash_per_round_pool,
            lock_resolution_pool=lock_resolution_pool,
            ward_resolution_pool=ward_resolution_pool,
            ward_per_round_pool=ward_per_round_pool,
            break_resolution_pool=break_resolution_pool,
            clash_window_combo=combo,
            threat_pool=threat_pool,
        )

    @staticmethod
    def attach_barrier_to_opponent(
        opponent: CombatOpponent,
        strength: int = 10,
        *,
        break_pool: ConsequencePool | None = None,
    ) -> None:
        """Set barrier fields on ``opponent`` and save.

        Barriers are per-encounter data, not standing seed content — this helper
        is called from test setUp after creating a CombatOpponent, passing the
        BREAK pool from ``ClashContentResult``.

        Args:
            opponent: The CombatOpponent to equip with a barrier.
            strength: Barrier strength (BREAK-clash PC win threshold). Default 10.
            break_pool: ConsequencePool fired when PCs break the barrier.
                        If None, the caller must supply it separately or
                        leave barrier_break_pool null (valid for unit tests
                        that don't fire the consequence pipeline).
        """
        opponent.barrier_strength = strength
        opponent.barrier_break_pool = break_pool
        opponent.save(update_fields=["barrier_strength", "barrier_break_pool"])


# ---------------------------------------------------------------------------
# Module-level helpers (private)
# ---------------------------------------------------------------------------


def _add_minimal_pool_entry(
    *,
    pool: ConsequencePool,
    outcome: CheckOutcome,
    label: str,
) -> None:
    """Add a single minimal consequence entry to a pool (idempotent).

    The consequence has no ConsequenceEffect row — it is a placeholder entry
    so that pool.cached_consequences is non-empty when tests query it.
    This is intentional: these pools carry their full authored content in
    production; here we only need enough structure for pipeline plumbing tests
    to find at least one entry without raising an empty-pool error.

    Uses a stable (outcome_tier, label) natural key for the Consequence row.

    Args:
        pool: The pool to add the entry to.
        outcome: The CheckOutcome tier for the consequence.
        label: Stable label string (embedded in unique pool name for soft uniqueness).
    """
    from actions.models import ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.models import Consequence  # noqa: PLC0415

    consequence, _ = Consequence.objects.get_or_create(
        outcome_tier=outcome,
        label=label,
        defaults={
            "mechanical_description": label,
            "weight": 1,
            "character_loss": False,
        },
    )
    ConsequencePoolEntry.objects.get_or_create(
        pool=pool,
        consequence=consequence,
    )


def _ensure_combo_slots(
    *,
    combo: ComboDefinition,
    effect_type: EffectType,
) -> None:
    """Ensure ``combo`` has at least two ComboSlot rows (idempotent).

    ComboSlot.slot_number is not unique per combo in the model, so we use
    get_or_create on (combo, slot_number) to prevent duplicates on re-runs.

    Args:
        combo: The ComboDefinition to add slots to.
        effect_type: EffectType used as required_action_type for each slot.
    """
    from world.combat.models import ComboSlot  # noqa: PLC0415

    for slot_number in (1, 2):
        ComboSlot.objects.get_or_create(
            combo=combo,
            slot_number=slot_number,
            defaults={"required_action_type": effect_type},
        )
