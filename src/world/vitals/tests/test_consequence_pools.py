from unittest.mock import patch

from django.test import TestCase, tag

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.constants import EffectType, ModifierSourceKind
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.outcome_utils import build_outcome_display
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.conditions.factories import (
    BleedingOutConditionFactory,
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
    UnconsciousConditionFactory,
)
from world.conditions.services import get_active_conditions
from world.traits.factories import CheckOutcomeFactory
from world.vitals.constants import (
    DEATH_BASE_DIFFICULTY,
    DEATH_CHECK_NAME,
    DEATH_SCALING_PER_PERCENT,
    ENDURANCE_CHECK_NAME,
    KNOCKOUT_BASE_DIFFICULTY,
    WOUND_BASE_DIFFICULTY,
    CharacterLifeState,
)
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import (
    _ensure_death_check_type,
    _ensure_endurance_check_type,
    calculate_death_difficulty,
    calculate_knockout_difficulty,
    calculate_wound_difficulty,
)


class SurvivabilityCheckSeedingTests(TestCase):
    def test_endurance_check_seeded_idempotently(self) -> None:
        c1 = _ensure_endurance_check_type()
        c2 = _ensure_endurance_check_type()
        self.assertEqual(c1.pk, c2.pk)
        self.assertEqual(c1.name, ENDURANCE_CHECK_NAME)

    def test_death_check_seeded(self) -> None:
        c1 = _ensure_death_check_type()
        c2 = _ensure_death_check_type()
        self.assertEqual(c1.pk, c2.pk)
        self.assertEqual(c1.name, DEATH_CHECK_NAME)


class DamageTypePoolFieldTests(TestCase):
    def test_pool_fks_default_null(self) -> None:
        dt = DamageTypeFactory()
        self.assertIsNone(dt.wound_pool)
        self.assertIsNone(dt.death_pool)


class VitalsConsequenceConfigTests(TestCase):
    def test_singleton_lazy_created(self) -> None:
        from world.vitals.services import get_vitals_consequence_config

        cfg = get_vitals_consequence_config()
        self.assertEqual(cfg.pk, 1)
        self.assertIsNone(cfg.knockout_pool)

    def test_difficulty_reads_authored_config(self) -> None:
        """Difficulty functions read values from the config singleton, not hardcoded constants.

        Asserts two things:
        1. Default config yields the same result as the existing constants (defaults preserved).
        2. Overriding a config field changes the calculated difficulty accordingly.
        """
        from world.vitals.services import get_vitals_consequence_config

        cfg = get_vitals_consequence_config()

        # --- Default values match the constant-derived results ---
        # knockout at exactly 20% → pct_below = 0 → KNOCKOUT_BASE_DIFFICULTY
        self.assertEqual(calculate_knockout_difficulty(health_pct=0.20), KNOCKOUT_BASE_DIFFICULTY)
        # death at exactly 0% → pct_below = 0 → DEATH_BASE_DIFFICULTY
        self.assertEqual(calculate_death_difficulty(health_pct=0.0), DEATH_BASE_DIFFICULTY)
        # wound at exactly 50% damage of max → pct_over = 0 → WOUND_BASE_DIFFICULTY
        wound_diff = calculate_wound_difficulty(damage=50, max_health=100)
        self.assertEqual(wound_diff, WOUND_BASE_DIFFICULTY)

        # --- Authored override: bump knockout_base_difficulty and confirm new result ---
        cfg.knockout_base_difficulty = KNOCKOUT_BASE_DIFFICULTY + 10
        cfg.save(update_fields=["knockout_base_difficulty"])
        # Flush the identity-map cache so get_vitals_consequence_config re-fetches from DB.
        cfg.flush_from_cache()

        self.assertEqual(
            calculate_knockout_difficulty(health_pct=0.20),
            KNOCKOUT_BASE_DIFFICULTY + 10,
            "calculate_knockout_difficulty must read knockout_base_difficulty from config",
        )

        # --- Authored override: bump death_scaling_per_percent ---
        cfg = get_vitals_consequence_config()
        cfg.death_scaling_per_percent = DEATH_SCALING_PER_PERCENT + 2
        cfg.save(update_fields=["death_scaling_per_percent"])
        cfg.flush_from_cache()

        # 10% below 0 → pct_below=10 → base + (10 * new_scale)
        expected = DEATH_BASE_DIFFICULTY + 10 * (DEATH_SCALING_PER_PERCENT + 2)
        self.assertEqual(
            calculate_death_difficulty(health_pct=-0.10),
            expected,
            "calculate_death_difficulty must read death_scaling_per_percent from config",
        )

        # --- Authored override: bump wound_base_difficulty ---
        cfg = get_vitals_consequence_config()
        cfg.wound_base_difficulty = WOUND_BASE_DIFFICULTY + 5
        cfg.save(update_fields=["wound_base_difficulty"])
        cfg.flush_from_cache()

        self.assertEqual(
            calculate_wound_difficulty(damage=50, max_health=100),
            WOUND_BASE_DIFFICULTY + 5,
            "calculate_wound_difficulty must read wound_base_difficulty from config",
        )


class ResolveVitalsConsequenceTests(TestCase):
    """Tests for resolve_vitals_consequence — the pool-pipeline wrapper."""

    def test_applies_condition_on_failure_outcome(self) -> None:
        """A FAILURE-tier consequence with APPLY_CONDITION applies the condition to character."""
        from world.vitals.services import resolve_vitals_consequence

        # Build a character with vitals.
        vitals = CharacterVitalsFactory()
        character = vitals.character_sheet.character

        # Build a FAILURE CheckOutcome (success_level < 0 → tier matched by select_consequence).
        failure_outcome = CheckOutcomeFactory(name="VitalsTestFailure", success_level=-1)

        # Build a non-progressive ConditionTemplate (SQLite-safe; no stages).
        condition_template = ConditionTemplateFactory(
            name="VitalsTestCondition",
            has_progression=False,
        )

        # Build a Consequence in the FAILURE tier with an APPLY_CONDITION effect.
        consequence = ConsequenceFactory(outcome_tier=failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=condition_template,
            target="self",
        )

        # Build a ConsequencePool with that consequence as its only entry.
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        # Build a minimal CheckType.
        check_type = CheckTypeFactory()

        # Force perform_check to return failure_outcome, then call the wrapper.
        with force_check_outcome(failure_outcome):
            resolve_vitals_consequence(
                character.sheet_data, check_type, target_difficulty=20, pool=pool
            )

        # The condition should now be active on the character.
        active = get_active_conditions(character, condition=condition_template)
        self.assertTrue(
            active.exists(),
            "Expected condition to be active after resolve_vitals_consequence on FAILURE",
        )


class ProcessDamageConsequencesPoolTests(TestCase):
    """Tests for process_damage_consequences resolved through consequence pools."""

    def test_knockout_resolves_pool_applies_unconscious(self) -> None:
        """A knockout-eligible hit with a FAILURE-tier knockout pool applies Unconscious.

        SQLite-safe: Unconscious is non-progressive.
        """
        from world.vitals.services import get_vitals_consequence_config, process_damage_consequences

        # Health in the 0-20% band so the knockout difficulty gate fires.
        vitals = CharacterVitalsFactory(health=10, max_health=100)
        character = vitals.character_sheet.character

        failure_outcome = CheckOutcomeFactory(name="KO-Pool-Failure", success_level=-1)
        unconscious_template = UnconsciousConditionFactory()

        consequence = ConsequenceFactory(outcome_tier=failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=unconscious_template,
            target="self",
        )

        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        cfg = get_vitals_consequence_config()
        cfg.knockout_pool = pool
        cfg.save(update_fields=["knockout_pool"])

        with force_check_outcome(failure_outcome):
            result = process_damage_consequences(
                character_sheet=character.sheet_data,
                damage_dealt=5,
                damage_type=None,
            )

        self.assertTrue(result.knocked_out)
        self.assertTrue(
            get_active_conditions(character, condition=unconscious_template).exists(),
            "Expected Unconscious active after knockout pool resolution",
        )
        vitals.refresh_from_db()
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)

    @tag("postgres")
    def test_death_resolves_pool_applies_bleed_out(self) -> None:
        """A death-eligible hit with a FAILURE-tier death pool applies Bleeding Out.

        @tag("postgres") — applying a progressive condition hits PG DISTINCT ON.
        """
        from world.vitals.services import process_damage_consequences

        vitals = CharacterVitalsFactory(health=0, max_health=100)
        character = vitals.character_sheet.character

        failure_outcome = CheckOutcomeFactory(name="Death-Pool-Failure", success_level=-1)
        bleed_out_template = BleedingOutConditionFactory()
        ConditionStageFactory(condition=bleed_out_template, stage_order=1, name="Bleeding")

        consequence = ConsequenceFactory(outcome_tier=failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=bleed_out_template,
            target="self",
        )

        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)

        damage_type = DamageTypeFactory(death_pool=pool)

        with force_check_outcome(failure_outcome):
            result = process_damage_consequences(
                character_sheet=character.sheet_data,
                damage_dealt=10,
                damage_type=damage_type,
            )

        self.assertTrue(result.dying)
        self.assertTrue(
            get_active_conditions(character, condition=bleed_out_template).exists(),
            "Expected Bleeding Out active after death pool resolution",
        )
        vitals.refresh_from_db()
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)

    @tag("postgres")
    def test_loss_outcome_respects_rollmod_filter(self) -> None:
        """A positive rollmod substitutes the worst non-loss tier outcome for a
        character_loss outcome (the standard filter_character_loss step inside
        select_consequence), and build_outcome_display reflects the full pool.

        @tag("postgres") — applying progressive Bleeding Out hits PG DISTINCT ON.
        """
        from world.checks.consequence_resolution import (
            resolve_pool_consequences,
            select_consequence,
        )
        from world.vitals.services import process_damage_consequences

        vitals = CharacterVitalsFactory(health=0, max_health=100)
        character = vitals.character_sheet.character
        # Positive rollmod via the real source: CharacterSheet.rollmod (read by get_rollmod).
        sheet = vitals.character_sheet
        sheet.rollmod = 5
        sheet.save(update_fields=["rollmod"])

        failure_outcome = CheckOutcomeFactory(name="Failure", success_level=-1)

        # Terminal Bleeding Out (the character_loss tier outcome).
        bleed_out_template = BleedingOutConditionFactory()
        ConditionStageFactory(condition=bleed_out_template, stage_order=1, name="Bleeding")
        loss_consequence = ConsequenceFactory(
            outcome_tier=failure_outcome, character_loss=True, weight=1, label="Lethal"
        )
        ConsequenceEffectFactory(
            consequence=loss_consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=bleed_out_template,
            target="self",
        )

        # Milder non-loss tier outcome.
        survival_template = ConditionTemplateFactory(name="Survival", has_progression=False)
        survival_consequence = ConsequenceFactory(
            outcome_tier=failure_outcome, character_loss=False, weight=1, label="Survived"
        )
        ConsequenceEffectFactory(
            consequence=survival_consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=survival_template,
            target="self",
        )

        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=loss_consequence)
        ConsequencePoolEntryFactory(pool=pool, consequence=survival_consequence)

        damage_type = DamageTypeFactory(death_pool=pool)

        with force_check_outcome(failure_outcome):
            process_damage_consequences(
                character_sheet=character.sheet_data,
                damage_dealt=10,
                damage_type=damage_type,
            )

        # With a positive rollmod the filter substitutes the non-loss tier outcome.
        self.assertTrue(
            get_active_conditions(character, condition=survival_template).exists(),
            "Expected non-loss tier outcome applied when rollmod is positive",
        )
        self.assertFalse(
            get_active_conditions(character, condition=bleed_out_template).exists(),
            "character_loss tier outcome must not be applied when the rollmod filter substitutes",
        )

        # build_outcome_display reflects the full pool (all tiers), independent of selection.
        full_consequences = resolve_pool_consequences(pool)
        tier_items = [c for c in full_consequences if c.outcome_tier == failure_outcome]
        with force_check_outcome(failure_outcome):
            pending = select_consequence(character, _ensure_death_check_type(), 20, tier_items)
        display = build_outcome_display(tier_items, pending.selected_consequence)
        self.assertIn(
            "Lethal",
            [d.label for d in display],
            "Outcome display reflects the full pool (all tiers)",
        )

    def test_active_condition_modifier_affects_survivability_check(self) -> None:
        """An active condition with a positive Endurance modifier causes the character to
        survive a knockout tier they would otherwise fail, and result.modifier_breakdown
        carries the condition contribution.

        The condition grants +20 on the Endurance check type.  Without it the
        perform_check call receives extra_modifiers=0 and the mock returns a FAILURE
        outcome (knockout applied).  With the condition active, extra_modifiers=+20 and
        the mock returns a SUCCESS outcome (no pool entry → not knocked out).

        The mock gates on the extra_modifiers value so the test is deterministic and
        explicitly validates that the condition modifier reached perform_check.
        """
        from world.vitals.services import get_vitals_consequence_config, process_damage_consequences

        # Health in the 0-20% knockout band.
        vitals = CharacterVitalsFactory(health=10, max_health=100)
        character = vitals.character_sheet.character

        # Build two outcomes: failure (knockout) and success (no effect).
        failure_outcome = CheckOutcomeFactory(name="KO-ModTest-Failure", success_level=-1)
        success_outcome = CheckOutcomeFactory(name="KO-ModTest-Success", success_level=1)

        # Knockout pool: only a FAILURE-tier consequence that applies Unconscious.
        unconscious_template = UnconsciousConditionFactory()
        ko_consequence = ConsequenceFactory(outcome_tier=failure_outcome, character_loss=False)
        ConsequenceEffectFactory(
            consequence=ko_consequence,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=unconscious_template,
            target="self",
        )
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=ko_consequence)

        cfg = get_vitals_consequence_config()
        cfg.knockout_pool = pool
        cfg.save(update_fields=["knockout_pool"])

        # Ensure the Endurance check type exists so collect_check_modifiers uses it.
        endurance_check_type = _ensure_endurance_check_type()

        # Active condition with a large positive modifier (+20) on the Endurance check.
        buff_template = ConditionTemplateFactory(name="KO-ModTest-Buff", has_progression=False)
        ConditionCheckModifierFactory(
            condition=buff_template,
            check_type=endurance_check_type,
            modifier_value=20,
        )
        ConditionInstanceFactory(target=character, condition=buff_template)

        # Mock perform_check in consequence_resolution to return outcome based on
        # whether extra_modifiers carries the condition value (> 0 → success, else failure).
        def _mock_perform_check(char, check_type, target_difficulty, extra_modifiers=0):  # type: ignore[misc]
            outcome = success_outcome if extra_modifiers > 0 else failure_outcome
            return CheckResult(
                check_type=check_type,
                outcome=outcome,
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=extra_modifiers,
            )

        perform_check_path = "world.checks.consequence_resolution.perform_check"
        with patch(perform_check_path, side_effect=_mock_perform_check):
            result = process_damage_consequences(
                character_sheet=character.sheet_data,
                damage_dealt=5,
                damage_type=None,
            )

        # The condition's +20 modifier shifted the outcome to SUCCESS → not knocked out.
        self.assertFalse(
            result.knocked_out,
            "Active condition with positive modifier should prevent knockout",
        )
        self.assertFalse(
            get_active_conditions(character, condition=unconscious_template).exists(),
            "Unconscious condition must not be applied when condition modifier yields SUCCESS",
        )

        # modifier_breakdown must be populated and include the condition contribution.
        self.assertIsNotNone(
            result.modifier_breakdown,
            "result.modifier_breakdown must be set when a survivability tier fires",
        )
        condition_contribs = [
            c
            for c in result.modifier_breakdown.contributions  # type: ignore[union-attr]
            if c.source_kind == ModifierSourceKind.CONDITION
        ]
        self.assertEqual(
            len(condition_contribs),
            1,
            "Exactly one CONDITION contribution expected in modifier_breakdown",
        )
        self.assertEqual(
            condition_contribs[0].value,
            20,
            "CONDITION contribution value must match the ConditionCheckModifier modifier_value",
        )
