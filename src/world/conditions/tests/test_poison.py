from django.test import TestCase, tag

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.constants import (
    BLEED_OUT_CONDITION_NAME,
    POISON_DAMAGE_TYPE_NAME,
    POISONED_CONDITION_NAME,
    SLOW_POISON_CONDITION_NAME,
    UNCONSCIOUS_CONDITION_NAME,
    DamageTickTiming,
)
from world.conditions.factories import (
    BleedingOutConditionFactory,
    ConditionDamageOverTimeFactory,
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.models import ConditionStage, ConditionTemplate, DamageType
from world.conditions.services import (
    _process_round_tick,
    apply_condition,
    batch_chronic_effect_tick,
    ensure_poison_content,
    get_active_conditions,
)
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.round_services import advance_scene_round
from world.traits.factories import CheckOutcomeFactory
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import tick_round_for_targets


class AcuteTickExcludesLongTermTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.target = cls.sheet.character
        cls.template = ConditionTemplateFactory(name="Poisoned-test")
        # Two distinct damage types: ConditionDamageOverTime has a unique
        # constraint on (condition, damage_type), so the acute and long-term
        # DoT rows on the same template must use different damage types.
        cls.acute_dtype = DamageTypeFactory(name="poison-acute")
        cls.long_term_dtype = DamageTypeFactory(name="poison-long-term")
        ConditionDamageOverTimeFactory(
            condition=cls.template,
            damage_type=cls.acute_dtype,
            base_damage=5,
            tick_timing=DamageTickTiming.END_OF_ROUND,
            is_long_term=False,
        )
        ConditionDamageOverTimeFactory(
            condition=cls.template,
            damage_type=cls.long_term_dtype,
            base_damage=99,
            tick_timing=DamageTickTiming.END_OF_ROUND,
            is_long_term=True,
        )
        ConditionInstanceFactory(target=cls.target, condition=cls.template)

    def test_acute_tick_ignores_long_term_rows(self):
        result = _process_round_tick(self.target, DamageTickTiming.END_OF_ROUND)
        amounts = [amt for _dt, amt in result.damage_dealt]
        self.assertIn(5, amounts)
        self.assertNotIn(99, amounts)


class AcuteDotDamagesHealthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.target = cls.sheet.character
        cls.vitals = CharacterVitalsFactory(character_sheet=cls.sheet, health=100, max_health=100)
        cls.dtype = DamageTypeFactory(name="poison-dmg")
        cls.template = ConditionTemplateFactory(name="Poisoned-dmg")
        ConditionDamageOverTimeFactory(
            condition=cls.template,
            damage_type=cls.dtype,
            base_damage=10,
            tick_timing=DamageTickTiming.END_OF_ROUND,
            is_long_term=False,
            scales_with_severity=False,
            scales_with_stacks=False,
        )
        ConditionInstanceFactory(target=cls.target, condition=cls.template)

    def test_end_tick_reduces_health_by_dot(self):
        tick_round_for_targets([self.target], timing="end")
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.health, 90)


class EnsurePoisonContentTests(TestCase):
    def test_seeds_idempotently(self):
        from world.conditions.constants import (
            POISON_DAMAGE_TYPE_NAME,
            POISONED_CONDITION_NAME,
            SLOW_POISON_CONDITION_NAME,
        )
        from world.conditions.models import (
            ConditionDamageOverTime,
            ConditionTemplate,
            DamageType,
        )
        from world.conditions.services import ensure_poison_content

        ensure_poison_content()
        ensure_poison_content()  # must not duplicate

        self.assertEqual(DamageType.objects.filter(name=POISON_DAMAGE_TYPE_NAME).count(), 1)
        acute = ConditionTemplate.objects.get(name=POISONED_CONDITION_NAME)
        slow = ConditionTemplate.objects.get(name=SLOW_POISON_CONDITION_NAME)
        self.assertTrue(acute.has_progression)
        self.assertEqual(acute.stages.count(), 2)
        self.assertTrue(
            ConditionDamageOverTime.objects.filter(condition=acute, is_long_term=False).exists()
        )
        self.assertTrue(
            ConditionDamageOverTime.objects.filter(condition=slow, is_long_term=True).exists()
        )


@tag("postgres")
class AcutePoisonSceneRoundTests(TestCase):
    """Test A — acute poison ticks health when a SCENE round resolves out of combat.

    @tag("postgres") — applying the progressive Poisoned condition and ticking it via
    the round path exercises the PG ``.distinct("condition_id")`` query that errors on SQLite.
    """

    def test_scene_round_resolution_ticks_acute_poison_health(self) -> None:
        ensure_poison_content()
        sheet = CharacterSheetFactory()
        character = sheet.character
        vitals = CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)

        poisoned = ConditionTemplate.get_by_name(POISONED_CONDITION_NAME)
        apply_condition(target=character, condition=poisoned)

        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=1)
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)

        advance_scene_round(rnd)

        vitals.refresh_from_db()
        self.assertLess(
            vitals.health,
            100,
            "Resolving a scene round must apply acute poison DoT to participant health",
        )


@tag("postgres")
class PoisonStagingScalesDotTests(TestCase):
    """Test B — condition staging drives the DoT: stage 2 deals more than stage 1.

    @tag("postgres") — staged progressive condition ticking hits the PG DISTINCT ON query.
    """

    def test_higher_stage_deals_more_poison_damage(self) -> None:
        ensure_poison_content()
        poisoned = ConditionTemplate.get_by_name(POISONED_CONDITION_NAME)
        stage1 = ConditionStage.objects.get(condition=poisoned, stage_order=1)
        stage2 = ConditionStage.objects.get(condition=poisoned, stage_order=2)

        sheet1 = CharacterSheetFactory()
        char1 = sheet1.character
        vitals1 = CharacterVitalsFactory(character_sheet=sheet1, health=100, max_health=100)
        apply_condition(target=char1, condition=poisoned)
        inst1 = get_active_conditions(char1, condition=poisoned).get()
        inst1.current_stage = stage1
        inst1.save(update_fields=["current_stage"])

        sheet2 = CharacterSheetFactory()
        char2 = sheet2.character
        vitals2 = CharacterVitalsFactory(character_sheet=sheet2, health=100, max_health=100)
        apply_condition(target=char2, condition=poisoned)
        inst2 = get_active_conditions(char2, condition=poisoned).get()
        inst2.current_stage = stage2
        inst2.save(update_fields=["current_stage"])

        # Confirm the raw DoT scales with stage (stage 2 multiplier 2.00 vs stage 1's 1.00).
        def tick_damage(char):
            result = _process_round_tick(char, DamageTickTiming.END_OF_ROUND)
            return sum(amt for _dt, amt in result.damage_dealt)

        dmg1 = tick_damage(char1)
        dmg2 = tick_damage(char2)
        # Staging scales the DoT: the higher stage deals strictly more damage. We assert the
        # monotonic intent rather than an exact ratio because _process_round_tick composes the
        # stage multiplier with effective_severity (which itself folds in the stage multiplier
        # — preexisting #230 behavior), so a severity-scaling staged DoT does not scale by a
        # clean 2x. The mechanic that matters here is "higher stage => more DoT".
        self.assertGreater(dmg2, dmg1, "Stage 2 must compute more DoT than stage 1")

        # And the health loss through the real tick path reflects the staging.
        tick_round_for_targets([char1], timing="end")
        tick_round_for_targets([char2], timing="end")
        vitals1.refresh_from_db()
        vitals2.refresh_from_db()
        loss1 = 100 - vitals1.health
        loss2 = 100 - vitals2.health
        self.assertGreater(loss2, loss1, "Stage-2 character must lose more health than stage-1")


@tag("postgres")
class AcutePoisonCrossesDeathThresholdTests(TestCase):
    """Test C — acute poison crossing the death threshold applies Bleeding-Out (#523).

    @tag("postgres") — applying the progressive Bleeding-Out condition hits the PG
    DISTINCT ON query, mirroring vitals' ``test_death_resolves_pool_applies_bleed_out``.
    """

    def test_lethal_poison_tick_applies_bleeding_out(self) -> None:
        ensure_poison_content()
        sheet = CharacterSheetFactory()
        character = sheet.character
        # Low health so a single poison tick crosses DEATH_HEALTH_THRESHOLD (0.0).
        vitals = CharacterVitalsFactory(character_sheet=sheet, health=2, max_health=100)

        # Seed a FAILURE-tier death pool that applies Bleeding-Out, wired to the poison
        # DamageType's death_pool (the damage_type threaded through _apply_round_tick_damage).
        failure_outcome = CheckOutcomeFactory(name="Poison-Death-Failure", success_level=-1)
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

        poison_dtype = DamageType.objects.get(name=POISON_DAMAGE_TYPE_NAME)
        poison_dtype.death_pool = pool
        poison_dtype.save(update_fields=["death_pool"])

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


@tag("postgres")
class ChronicPoisonTickTests(TestCase):
    """Capped long-term chronic-effect tier (#520 §5.3 + §6).

    @tag("postgres") — applying the long-term Slow Poison condition exercises the
    PG-only DISTINCT ON query in the conditions apply/active path.
    """

    def _slow_poisoned(self, *, health: int, max_health: int = 100):
        ensure_poison_content()
        sheet = CharacterSheetFactory()
        character = sheet.character
        vitals = CharacterVitalsFactory(character_sheet=sheet, health=health, max_health=max_health)
        slow = ConditionTemplate.get_by_name(SLOW_POISON_CONDITION_NAME)
        apply_condition(target=character, condition=slow)
        return sheet, character, vitals

    def test_chronic_poison_reduces_health(self) -> None:
        _sheet, _character, vitals = self._slow_poisoned(health=100)
        summary = batch_chronic_effect_tick()
        vitals.refresh_from_db()
        self.assertLess(vitals.health, 100)
        self.assertEqual(summary.ticked, 1)

    def test_cap_never_kills_or_knocks_out(self) -> None:
        _sheet, character, vitals = self._slow_poisoned(health=25)
        for _ in range(50):
            batch_chronic_effect_tick()
        vitals.refresh_from_db()
        self.assertGreater(vitals.health_percentage, 0.2)
        active_names = {inst.condition.name for inst in get_active_conditions(character)}
        self.assertNotIn(BLEED_OUT_CONDITION_NAME, active_names)
        self.assertNotIn(UNCONSCIOUS_CONDITION_NAME, active_names)

    def test_skips_character_in_active_round(self) -> None:
        sheet, _character, vitals = self._slow_poisoned(health=100)
        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=1)
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)

        summary = batch_chronic_effect_tick()

        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 100, "Active-round targets are owned by the acute tier")
        self.assertEqual(summary.active_round_skipped, 1)

    def test_acute_poison_not_advanced_by_chronic_tick(self) -> None:
        ensure_poison_content()
        sheet = CharacterSheetFactory()
        character = sheet.character
        vitals = CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
        poisoned = ConditionTemplate.get_by_name(POISONED_CONDITION_NAME)
        apply_condition(target=character, condition=poisoned)

        summary = batch_chronic_effect_tick()

        vitals.refresh_from_db()
        self.assertEqual(vitals.health, 100, "Acute poison (is_long_term=False) is not chronic")
        self.assertEqual(summary.examined, 0)


@tag("postgres")
class SlowPoisonTierSplitTests(TestCase):
    """End-to-end split: Slow Poison advances ONLY via the long-term tier (#520/#1050).

    A long-term (``is_long_term=True``) DoT row is owned by the capped chronic tier, not
    the acute round tick. This proves both directions of that ownership:
    - an acute scene round does NOT advance Slow Poison (the acute tick skips long-term rows);
    - the chronic daily tick DOES advance it.

    @tag("postgres") — applying the progressive Slow Poison condition and resolving a scene
    round exercise the PG-only DISTINCT ON query in the conditions apply/active path.
    """

    def test_slow_poison_advanced_only_by_long_term_tier(self) -> None:
        ensure_poison_content()
        slow = ConditionTemplate.get_by_name(SLOW_POISON_CONDITION_NAME)

        # Character A: in an ACTIVE scene round — the acute tick must NOT touch Slow Poison.
        sheet_round = CharacterSheetFactory()
        char_round = sheet_round.character
        vitals_round = CharacterVitalsFactory(
            character_sheet=sheet_round, health=100, max_health=100
        )
        apply_condition(target=char_round, condition=slow)
        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=1)
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet_round)

        advance_scene_round(rnd)

        vitals_round.refresh_from_db()
        self.assertEqual(
            vitals_round.health,
            100,
            "An acute scene round must NOT advance a long-term Slow Poison DoT row",
        )

        # Character B: NOT in any round — the chronic tier DOES advance Slow Poison.
        sheet_chronic = CharacterSheetFactory()
        char_chronic = sheet_chronic.character
        vitals_chronic = CharacterVitalsFactory(
            character_sheet=sheet_chronic, health=100, max_health=100
        )
        apply_condition(target=char_chronic, condition=slow)

        batch_chronic_effect_tick()

        vitals_chronic.refresh_from_db()
        self.assertLess(
            vitals_chronic.health,
            100,
            "The chronic long-term tier must advance Slow Poison and reduce health",
        )
