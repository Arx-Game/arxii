"""Non-combat transition-matrix integration tests (#523 / #1054, Phase 8 of #520).

Each non-combat damage source — poison tick, trap hit, exhaustion strain — is
asserted to drive Bleeding-Out (health ≤ 0, death tier) and Unconscious (health
0–20%, knockout tier) when it crosses the relevant threshold.  A final block
asserts the invariant that bleed-out advances only via the active-round tick
(tick_round_for_targets), never the long-term chronic tier.

SQLite/PG split
---------------
- Unconscious (non-progressive) tests — SQLite-safe.
- Bleeding-Out (progressive, staged) tests — @tag("postgres"): apply_condition
  for a progressive condition exercises the PG-only DISTINCT ON query path.
  Source: test_bleed_out.py header; vitals/tests/test_consequence_pools.py pattern.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, tag

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import (
    CheckTypeFactory,
    ConsequenceEffectFactory,
    ConsequenceFactory,
)
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.conditions.constants import (
    BLEED_OUT_CONDITION_NAME,
    POISON_DAMAGE_TYPE_NAME,
    POISONED_CONDITION_NAME,
    DamageTickTiming,
)
from world.conditions.factories import (
    BleedingOutConditionFactory,
    ConditionDamageOverTimeFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
    UnconsciousConditionFactory,
)
from world.conditions.models import ConditionTemplate, DamageType
from world.conditions.services import (
    apply_condition,
    batch_chronic_effect_tick,
    ensure_poison_content,
    get_active_conditions,
)
from world.fatigue.constants import EXHAUSTION_DAMAGE_TYPE_NAME
from world.fatigue.services import apply_exhaustion_damage
from world.room_features.factories import TrapFactory
from world.room_features.trap_services import check_room_traps_on_entry
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import (
    apply_clamped_chronic_damage,
    get_vitals_consequence_config,
    tick_round_for_targets,
)

_CONSEQUENCE_RESOLUTION_PERFORM_CHECK = "world.checks.consequence_resolution.perform_check"


def _wire_knockout_pool(*, failure_outcome):
    """Build a failure-tier Unconscious pool and register it as the global knockout pool."""
    unconscious = UnconsciousConditionFactory()
    consequence = ConsequenceFactory(outcome_tier=failure_outcome, character_loss=False)
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.APPLY_CONDITION,
        condition_template=unconscious,
        target="self",
    )
    pool = ConsequencePoolFactory()
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    cfg = get_vitals_consequence_config()
    cfg.knockout_pool = pool
    cfg.save(update_fields=["knockout_pool"])
    return unconscious


def _build_death_pool(*, failure_outcome):
    """Build a failure-tier Bleeding-Out consequence pool (caller wires it to a DamageType)."""
    bleed_out = BleedingOutConditionFactory()
    ConditionStageFactory(condition=bleed_out, stage_order=1, name="Bleeding")
    consequence = ConsequenceFactory(outcome_tier=failure_outcome, character_loss=False)
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.APPLY_CONDITION,
        condition_template=bleed_out,
        target="self",
    )
    pool = ConsequencePoolFactory()
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    return bleed_out, pool


# ---------------------------------------------------------------------------
# Poison tick
# ---------------------------------------------------------------------------


class PoisonTickKnockoutTests(TestCase):
    """Poison DoT tick crossing the knockout threshold (0–20%) applies Unconscious.

    SQLite-safe: Unconscious is non-progressive; ConditionInstance is created
    directly via factory, bypassing the PG-only DISTINCT ON apply_condition path.
    A generic non-progressive DoT avoids the ensure_poison_content progressive
    condition path entirely, keeping the test SQLite-compatible.
    """

    def test_poison_tick_crossing_knockout_threshold_applies_unconscious(self) -> None:
        failure_outcome = CheckOutcomeFactory(name="Poison-KO-Failure", success_level=-1)
        unconscious_template = _wire_knockout_pool(failure_outcome=failure_outcome)

        sheet = CharacterSheetFactory()
        character = sheet.character
        # health=22 → 10-damage DoT → health=12 (12%, in the 0–20% knockout band)
        vitals = CharacterVitalsFactory(character_sheet=sheet, health=22, max_health=100)

        dtype = DamageTypeFactory(name="poison-ko-test")
        template = ConditionTemplateFactory(name="Poison-KO-Test", has_progression=False)
        ConditionDamageOverTimeFactory(
            condition=template,
            damage_type=dtype,
            base_damage=10,
            tick_timing=DamageTickTiming.END_OF_ROUND,
            is_long_term=False,
            scales_with_severity=False,
            scales_with_stacks=False,
        )
        ConditionInstanceFactory(target=character, condition=template)

        with force_check_outcome(failure_outcome):
            tick_round_for_targets([character], timing="end")

        vitals.refresh_from_db()
        self.assertLessEqual(vitals.health, 20, "DoT tick must push health into the knockout band")
        self.assertTrue(
            get_active_conditions(character, condition=unconscious_template).exists(),
            "Poison DoT crossing the knockout threshold must apply Unconscious",
        )
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)


@tag("postgres")
class PoisonTickBleedOutTests(TestCase):
    """Poison DoT tick crossing the death threshold (health ≤ 0) applies Bleeding-Out.

    @tag("postgres"): apply_condition for progressive Poisoned and Bleeding-Out
    uses the PG-only DISTINCT ON query path.

    Also covered end-to-end by AcutePoisonCrossesDeathThresholdTests in
    world/conditions/tests/test_poison.py; included here for transition-matrix
    completeness.
    """

    def test_poison_tick_crossing_death_threshold_applies_bleeding_out(self) -> None:
        ensure_poison_content()
        failure_outcome = CheckOutcomeFactory(name="Poison-BleedOut-Failure", success_level=-1)
        _bleed_out_template, death_pool = _build_death_pool(failure_outcome=failure_outcome)

        poison_dtype = DamageType.objects.get(name=POISON_DAMAGE_TYPE_NAME)
        poison_dtype.death_pool = death_pool
        poison_dtype.save(update_fields=["death_pool"])

        sheet = CharacterSheetFactory()
        character = sheet.character
        # health=2: the Poisoned acute DoT (base 5 dmg at stage 1) crosses health ≤ 0
        vitals = CharacterVitalsFactory(character_sheet=sheet, health=2, max_health=100)

        poisoned = ConditionTemplate.get_by_name(POISONED_CONDITION_NAME)
        apply_condition(target=character, condition=poisoned)

        with force_check_outcome(failure_outcome):
            tick_round_for_targets([character], timing="end")

        vitals.refresh_from_db()
        self.assertLessEqual(vitals.health, 0, "Poison tick must cross the death threshold")
        active_names = {inst.condition.name for inst in get_active_conditions(character)}
        self.assertIn(
            BLEED_OUT_CONDITION_NAME,
            active_names,
            "Crossing the death threshold via poison must apply Bleeding-Out",
        )


# ---------------------------------------------------------------------------
# Trap hit
# ---------------------------------------------------------------------------


class TrapHitKnockoutTests(TestCase):
    """Trap hit crossing the knockout threshold (0–20%) applies Unconscious.

    SQLite-safe: Unconscious is non-progressive.  Both the trap detection check
    and the vitals knockout check are forced to fail by patching perform_check in
    the consequence_resolution module — the single path used by both select_consequence
    calls (trap pool and knockout pool).
    """

    def setUp(self) -> None:
        self.failure_outcome = CheckOutcomeFactory(name="Trap-KO-Failure", success_level=-1)
        self.unconscious_template = _wire_knockout_pool(failure_outcome=self.failure_outcome)

        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb
        self.character = CharacterFactory(db_key="trap-victim-ko")
        self.sheet = CharacterSheetFactory(character=self.character)
        # health=50; trap deals 45 → health=5 (5%, in the 0–20% knockout band)
        self.vitals = CharacterVitalsFactory(character_sheet=self.sheet, health=50, max_health=100)

        pool = ConsequencePoolFactory()
        trap_dtype = DamageTypeFactory(name="trap-ko-spikes")
        consequence = ConsequenceFactory(outcome_tier=self.failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.DEAL_DAMAGE,
            target=EffectTarget.SELF,
            damage_amount=45,
            damage_type=trap_dtype,
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        self.trap = TrapFactory(
            room_profile=self.room_profile,
            consequence_pool=pool,
            detect_check_type=CheckTypeFactory(name="Detect-Trap-KO"),
            detect_difficulty=20,
        )

    def _always_fail(self, _character, check_type, _target_difficulty, _extra_modifiers=0):
        return CheckResult(
            check_type=check_type,
            outcome=self.failure_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

    def test_trap_hit_crossing_knockout_threshold_applies_unconscious(self) -> None:
        with patch(_CONSEQUENCE_RESOLUTION_PERFORM_CHECK, side_effect=self._always_fail):
            check_room_traps_on_entry(self.character, self.room)

        self.vitals.refresh_from_db()
        self.assertLessEqual(
            self.vitals.health, 20, "Trap damage must push health into the knockout band"
        )
        self.assertTrue(
            get_active_conditions(self.character, condition=self.unconscious_template).exists(),
            "Trap hit crossing the knockout threshold must apply Unconscious",
        )
        self.assertEqual(self.vitals.life_state, CharacterLifeState.ALIVE)


@tag("postgres")
class TrapHitBleedOutTests(TestCase):
    """Trap hit crossing the death threshold (health ≤ 0) applies Bleeding-Out.

    @tag("postgres"): applying the progressive Bleeding-Out condition uses DISTINCT ON.
    Both the detection check and the death vitals check are forced to fail via patch.
    """

    def setUp(self) -> None:
        self.failure_outcome = CheckOutcomeFactory(name="Trap-BleedOut-Failure", success_level=-1)
        self.bleed_out_template, death_pool = _build_death_pool(
            failure_outcome=self.failure_outcome
        )

        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb
        self.character = CharacterFactory(db_key="trap-victim-death")
        self.sheet = CharacterSheetFactory(character=self.character)
        # health=5; trap deals 30 → health=-25 (crosses death threshold)
        self.vitals = CharacterVitalsFactory(character_sheet=self.sheet, health=5, max_health=100)

        pool = ConsequencePoolFactory()
        trap_dtype = DamageTypeFactory(name="trap-death-spikes")
        trap_dtype.death_pool = death_pool
        trap_dtype.save(update_fields=["death_pool"])

        consequence = ConsequenceFactory(outcome_tier=self.failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.DEAL_DAMAGE,
            target=EffectTarget.SELF,
            damage_amount=30,
            damage_type=trap_dtype,
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        self.trap = TrapFactory(
            room_profile=self.room_profile,
            consequence_pool=pool,
            detect_check_type=CheckTypeFactory(name="Detect-Trap-Death"),
            detect_difficulty=20,
        )

    def _always_fail(self, _character, check_type, _target_difficulty, _extra_modifiers=0):
        return CheckResult(
            check_type=check_type,
            outcome=self.failure_outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

    def test_trap_hit_crossing_death_threshold_applies_bleeding_out(self) -> None:
        with patch(_CONSEQUENCE_RESOLUTION_PERFORM_CHECK, side_effect=self._always_fail):
            check_room_traps_on_entry(self.character, self.room)

        self.vitals.refresh_from_db()
        self.assertLessEqual(self.vitals.health, 0, "Trap damage must cross the death threshold")
        active_names = {inst.condition.name for inst in get_active_conditions(self.character)}
        self.assertIn(
            BLEED_OUT_CONDITION_NAME,
            active_names,
            "Trap hit crossing the death threshold must apply Bleeding-Out",
        )


# ---------------------------------------------------------------------------
# Exhaustion strain
# ---------------------------------------------------------------------------


class ExhaustionStrainKnockoutTests(TestCase):
    """Exhaustion strain crossing the knockout threshold (0–20%) applies Unconscious.

    SQLite-safe: Unconscious is non-progressive.  apply_exhaustion_damage calls
    process_damage_consequences with the exhaustion DamageType; the global knockout
    pool fires when health falls into the 0–20% band.
    """

    def test_exhaustion_strain_crossing_knockout_threshold_applies_unconscious(
        self,
    ) -> None:
        failure_outcome = CheckOutcomeFactory(name="Exh-KO-Failure", success_level=-1)
        unconscious_template = _wire_knockout_pool(failure_outcome=failure_outcome)

        sheet = CharacterSheetFactory()
        # health=22; 15-point strain → health=7 (7%, in the 0–20% knockout band)
        vitals = CharacterVitalsFactory(character_sheet=sheet, health=22, max_health=100)

        with force_check_outcome(failure_outcome):
            apply_exhaustion_damage(sheet, 15)

        vitals.refresh_from_db()
        self.assertLessEqual(
            vitals.health, 20, "Exhaustion strain must push health into the knockout band"
        )
        self.assertTrue(
            get_active_conditions(sheet.character, condition=unconscious_template).exists(),
            "Exhaustion strain crossing the knockout threshold must apply Unconscious",
        )
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)


@tag("postgres")
class ExhaustionStrainBleedOutTests(TestCase):
    """Exhaustion strain crossing the death threshold (health ≤ 0) applies Bleeding-Out.

    @tag("postgres"): applying the progressive Bleeding-Out condition uses DISTINCT ON.
    apply_exhaustion_damage routes through process_damage_consequences with the
    'exhaustion' DamageType; we wire that type's death_pool before dealing strain.
    """

    def test_exhaustion_strain_crossing_death_threshold_applies_bleeding_out(
        self,
    ) -> None:
        failure_outcome = CheckOutcomeFactory(name="Exh-BleedOut-Failure", success_level=-1)
        _bleed_out_template, death_pool = _build_death_pool(failure_outcome=failure_outcome)

        # Seed the exhaustion DamageType first, then wire the death pool.
        dtype, _ = DamageType.objects.get_or_create(
            name=EXHAUSTION_DAMAGE_TYPE_NAME,
            defaults={"description": "Exhaustion damage"},
        )
        dtype.death_pool = death_pool
        dtype.save(update_fields=["death_pool"])

        sheet = CharacterSheetFactory()
        # health=5; 10-point strain → health=-5 (crosses death threshold)
        vitals = CharacterVitalsFactory(character_sheet=sheet, health=5, max_health=100)

        with force_check_outcome(failure_outcome):
            apply_exhaustion_damage(sheet, 10)

        vitals.refresh_from_db()
        self.assertLessEqual(vitals.health, 0, "Exhaustion strain must cross the death threshold")
        active_names = {inst.condition.name for inst in get_active_conditions(sheet.character)}
        self.assertIn(
            BLEED_OUT_CONDITION_NAME,
            active_names,
            "Exhaustion strain crossing the death threshold must apply Bleeding-Out",
        )


# ---------------------------------------------------------------------------
# Invariant: bleed-out only advances via active round, never the chronic tier
# ---------------------------------------------------------------------------


class BleedOutViaActiveRoundOnlyTests(TestCase):
    """Bleed-out never advances via the long-term chronic tier.

    The long-term tier (batch_chronic_effect_tick) uses apply_clamped_chronic_damage,
    which never calls process_damage_consequences and therefore can never seed a
    Bleeding-Out condition.  advance_bleed_out is called only from tick_round_for_targets
    (active-round timing==end), so an existing Bleeding-Out condition is unaffected
    by chronic ticks.

    Both tests are SQLite-safe: Bleeding-Out is created via ConditionInstanceFactory
    directly, bypassing the PG DISTINCT ON apply_condition path.
    """

    def test_chronic_tier_clamp_never_breaches_knockout_floor(self) -> None:
        """apply_clamped_chronic_damage never drives health into the knockout band,
        so Bleeding-Out can never be seeded by the long-term tier.
        """
        sheet = CharacterSheetFactory()
        vitals = CharacterVitalsFactory(character_sheet=sheet, health=25, max_health=100)

        # Massive chronic hit — should be clamped strictly above the 20% floor.
        apply_clamped_chronic_damage(sheet, 1_000)

        vitals.refresh_from_db()
        self.assertGreater(
            vitals.health_percentage,
            0.20,
            "apply_clamped_chronic_damage must never reduce health into the knockout band",
        )

    def test_chronic_tier_never_advances_existing_bleed_out(self) -> None:
        """batch_chronic_effect_tick does not advance staged Bleeding-Out conditions."""
        sheet = CharacterSheetFactory()
        character = sheet.character
        CharacterVitalsFactory(character_sheet=sheet, health=50, max_health=100)

        check_type = CheckTypeFactory()
        bleed_out = BleedingOutConditionFactory()
        stage1 = ConditionStageFactory(
            condition=bleed_out,
            stage_order=1,
            name="Bleeding",
            resist_check_type=check_type,
            resist_difficulty=20,
            rounds_to_next=None,
        )
        ConditionStageFactory(
            condition=bleed_out,
            stage_order=2,
            name="Dying",
            resist_check_type=check_type,
            resist_difficulty=40,
            rounds_to_next=None,
        )
        instance = ConditionInstanceFactory(
            target=character, condition=bleed_out, current_stage=stage1
        )

        # Multiple chronic ticks must not touch the bleed-out advancement.
        for _ in range(3):
            batch_chronic_effect_tick()

        instance.refresh_from_db()
        self.assertEqual(
            instance.current_stage,
            stage1,
            "batch_chronic_effect_tick must not advance Bleeding-Out stages",
        )
