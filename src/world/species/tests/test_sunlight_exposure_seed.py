"""Sunlight Exposure condition seed: stages, stage-level DoT, penalties (#1588, #2846)."""

from django.test import TestCase

from world.conditions.factories import ensure_radiant_damage_type
from world.conditions.models import (
    ConditionCheckModifier,
    ConditionDamageOverTime,
    ConditionStage,
    ConditionTemplate,
)
from world.species.factories import (
    SUNLIGHT_EXPOSURE_DAMAGE,
    SUNLIGHT_SEARING_DAMAGE,
    SUNLIGHT_STAGE_BURNING,
    SUNLIGHT_STAGE_SEARING,
    ensure_sunlight_distinctions,
    ensure_sunlight_exposure_content,
)
from world.species.sun_constants import (
    BURNING_SEVERITY_THRESHOLD,
    SUN_ALLERGY_TAG,
    SUN_BANE_TAG,
)


class EnsureSunlightExposureContentTest(TestCase):
    def test_creates_staged_template_with_stage_level_radiant_dot(self):
        """Damage lives ONLY on the Burning/Searing stages — never the bare template."""
        radiant = ensure_radiant_damage_type()
        tpl = ensure_sunlight_exposure_content()
        self.assertEqual(tpl.name, "Sunlight Exposure")
        self.assertEqual(
            ConditionDamageOverTime.objects.filter(condition=tpl).count(),
            0,
            "No template-level DoT: sub-Burning severities must not damage",
        )
        stages = {s.name: s for s in ConditionStage.objects.filter(condition=tpl)}
        self.assertEqual(len(stages), 3)
        burning_dot = ConditionDamageOverTime.objects.get(stage=stages[SUNLIGHT_STAGE_BURNING])
        self.assertEqual(burning_dot.damage_type, radiant)
        self.assertEqual(burning_dot.base_damage, SUNLIGHT_EXPOSURE_DAMAGE)
        self.assertFalse(burning_dot.scales_with_severity)
        searing_dot = ConditionDamageOverTime.objects.get(stage=stages[SUNLIGHT_STAGE_SEARING])
        self.assertEqual(searing_dot.base_damage, SUNLIGHT_SEARING_DAMAGE)
        self.assertEqual(
            stages[SUNLIGHT_STAGE_BURNING].severity_threshold,
            BURNING_SEVERITY_THRESHOLD,
        )

    def test_check_penalties_cover_existing_categories(self):
        """Every existing CheckCategory gets a severity-scaled penalty row."""
        from world.checks.factories import CheckCategoryFactory

        CheckCategoryFactory(name="TestPhysical")
        CheckCategoryFactory(name="TestSocial")
        tpl = ensure_sunlight_exposure_content()
        rows = ConditionCheckModifier.objects.filter(condition=tpl)
        self.assertGreaterEqual(rows.count(), 2)
        for row in rows:
            self.assertTrue(row.scales_with_severity)
            self.assertLess(row.modifier_value, 0)

    def test_idempotent(self):
        ensure_radiant_damage_type()
        first = ensure_sunlight_exposure_content()
        second = ensure_sunlight_exposure_content()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ConditionTemplate.objects.filter(name="Sunlight Exposure").count(), 1)
        self.assertEqual(ConditionStage.objects.filter(condition=first).count(), 3)
        self.assertEqual(
            ConditionDamageOverTime.objects.filter(stage__condition=first).count(),
            2,
        )


class EnsureSunlightDistinctionsTest(TestCase):
    def test_creates_tagged_mutually_exclusive_reimbursing_pair(self):
        bane, allergy = ensure_sunlight_distinctions()
        self.assertLess(bane.cost_per_rank, allergy.cost_per_rank)
        self.assertLess(allergy.cost_per_rank, 0)
        self.assertEqual(set(bane.tags.values_list("slug", flat=True)), {SUN_BANE_TAG})
        self.assertEqual(set(allergy.tags.values_list("slug", flat=True)), {SUN_ALLERGY_TAG})
        self.assertIn(allergy, bane.mutually_exclusive_with.all())
        self.assertIn(bane, allergy.mutually_exclusive_with.all())

    def test_idempotent(self):
        first_bane, _ = ensure_sunlight_distinctions()
        second_bane, _ = ensure_sunlight_distinctions()
        self.assertEqual(first_bane.pk, second_bane.pk)
