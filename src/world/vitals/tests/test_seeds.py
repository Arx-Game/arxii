"""Tests for the survivability seed cluster (#2287)."""

from django.test import TestCase

from world.conditions.constants import (
    BLEED_OUT_CONDITION_NAME,
    UNCONSCIOUS_CONDITION_NAME,
    FoundationalCapability,
)
from world.conditions.models import CapabilityType, ConditionStage, ConditionTemplate
from world.vitals.constants import (
    DREAM_ROOM_TAG,
    DREAM_ROOM_TAG_CATEGORY,
    POOL_KNOCKOUT,
)
from world.vitals.models import VitalsConsequenceConfig
from world.vitals.seeds import seed_survivability_content


class SurvivabilitySeedTests(TestCase):
    """The seed cluster is idempotent and wires the config singleton."""

    def test_seed_survivability_idempotent(self) -> None:
        from actions.models import ConsequencePool, ConsequencePoolEntry
        from world.checks.models import Consequence, ConsequenceEffect

        seed_survivability_content()
        counts = (
            ConsequencePool.objects.count(),
            ConsequencePoolEntry.objects.count(),
            Consequence.objects.count(),
            ConsequenceEffect.objects.count(),
            ConditionTemplate.objects.count(),
            ConditionStage.objects.count(),
            CapabilityType.objects.count(),
        )
        seed_survivability_content()
        counts_after = (
            ConsequencePool.objects.count(),
            ConsequencePoolEntry.objects.count(),
            Consequence.objects.count(),
            ConsequenceEffect.objects.count(),
            ConditionTemplate.objects.count(),
            ConditionStage.objects.count(),
            CapabilityType.objects.count(),
        )
        self.assertEqual(counts, counts_after)

    def test_config_pools_wired(self) -> None:
        seed_survivability_content()
        config = VitalsConsequenceConfig.objects.get(pk=1)
        self.assertIsNotNone(config.knockout_pool)
        self.assertIsNotNone(config.default_death_pool)
        self.assertIsNotNone(config.default_wound_pool)
        self.assertIn("PLACEHOLDER", config.death_condolence_body)

    def test_bleeding_out_has_three_stages(self) -> None:
        seed_survivability_content()
        template = ConditionTemplate.objects.get(name=BLEED_OUT_CONDITION_NAME)
        self.assertTrue(template.has_progression)
        stages = list(template.stages.order_by("stage_order"))
        self.assertEqual(len(stages), 3)
        self.assertIsNone(stages[-1].rounds_to_next)
        for stage in stages:
            self.assertIsNotNone(stage.resist_check_type)

    def test_knockout_pool_applies_unconscious(self) -> None:
        from world.checks.constants import EffectType
        from world.checks.models import ConsequenceEffect

        seed_survivability_content()
        unconscious = ConditionTemplate.objects.get(name=UNCONSCIOUS_CONDITION_NAME)
        config = VitalsConsequenceConfig.objects.get(pk=1)
        effects = ConsequenceEffect.objects.filter(
            consequence__pool_entries__pool=config.knockout_pool,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=unconscious,
        )
        self.assertTrue(effects.exists())

    def test_awareness_capability_seeded_with_baseline(self) -> None:
        seed_survivability_content()
        awareness = CapabilityType.objects.get(name=FoundationalCapability.AWARENESS)
        self.assertGreaterEqual(awareness.innate_baseline, 1)
        unconscious = ConditionTemplate.objects.get(name=UNCONSCIOUS_CONDITION_NAME)
        effect = unconscious.conditioncapabilityeffect_set.get(capability=awareness)
        self.assertLessEqual(effect.value, -100)

    def test_dream_room_created_once(self) -> None:
        from evennia.utils.search import search_tag

        seed_survivability_content()
        seed_survivability_content()
        rooms = search_tag(key=DREAM_ROOM_TAG, category=DREAM_ROOM_TAG_CATEGORY)
        self.assertEqual(len(rooms), 1)

    def test_wound_pool_applies_lingering_ache_and_crippling(self) -> None:
        """The wound pool's central gap is closed (#2644): partial/failure apply real conditions."""
        from world.checks.constants import EffectType
        from world.checks.models import Consequence, ConsequenceEffect
        from world.vitals.constants import WOUND_CRIPPLING_NAME, WOUND_LINGERING_ACHE_NAME

        seed_survivability_content()
        lingering_ache = ConditionTemplate.objects.get(name=WOUND_LINGERING_ACHE_NAME)
        crippling = ConditionTemplate.objects.get(name=WOUND_CRIPPLING_NAME)
        config = VitalsConsequenceConfig.objects.get(pk=1)

        ache_effects = ConsequenceEffect.objects.filter(
            consequence__pool_entries__pool=config.default_wound_pool,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=lingering_ache,
        )
        self.assertTrue(ache_effects.exists())

        crippling_effects = ConsequenceEffect.objects.filter(
            consequence__pool_entries__pool=config.default_wound_pool,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=crippling,
        )
        self.assertTrue(crippling_effects.exists())

        # Best outcome (shaken_off) stays effect-free by design.
        shaken_off = Consequence.objects.get(label="shaken_off")
        self.assertFalse(shaken_off.effects.exists())

    def test_wound_treatment_content_seeded_once_per_wound(self) -> None:
        from world.conditions.models import TreatmentTemplate

        seed_survivability_content()
        self.assertEqual(
            TreatmentTemplate.objects.filter(
                key__in=[
                    "treat_lingering_ache",
                    "treat_crippling_wound",
                    "treat_bleeding_wound",
                ]
            ).count(),
            3,
        )
        for treatment in TreatmentTemplate.objects.filter(key__startswith="treat_"):
            self.assertTrue(treatment.once_per_wound_per_helper)
            self.assertFalse(treatment.once_per_scene_per_helper)

    def test_seed_preserves_staff_pool_override(self) -> None:
        from actions.models import ConsequencePool

        custom = ConsequencePool.objects.create(name="staff_custom_knockout")
        config, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)
        config.knockout_pool = custom
        config.save(update_fields=["knockout_pool"])

        seed_survivability_content()
        config.refresh_from_db()
        self.assertEqual(config.knockout_pool_id, custom.pk)
        # The standard pool still exists for staff to switch back to.
        self.assertTrue(ConsequencePool.objects.filter(name=POOL_KNOCKOUT).exists())
