"""Tests for the plummet content seed service (#1228, Task 3).

``ensure_fall_content`` idempotently seeds the fall ``DamageType`` and the
"Plummeting" ``ConditionTemplate`` — a simple non-progressive, non-expiring
(``PERMANENT``) marker with no stages and no DoT (impact is applied explicitly
at the bottom in Task 6, and depth lives in the instance's ``severity``
accumulator, not stage multipliers). The fall DamageType leaves its wound/death
pools null so the config-default survivability pools apply, exactly like poison.
"""

from django.test import TestCase

from world.areas.positioning.constants import (
    FALL_DAMAGE_TYPE_NAME,
    FALLING_CATEGORY_NAME,
    PLUMMETING_CONDITION_NAME,
)
from world.areas.positioning.plummet_content import ensure_fall_content
from world.conditions.constants import DurationType
from world.conditions.models import (
    ConditionCategory,
    ConditionDamageOverTime,
    ConditionStage,
    ConditionTemplate,
    DamageType,
)


class EnsureFallContentTests(TestCase):
    def test_seeds_fall_damage_type(self):
        ensure_fall_content()
        dt = DamageType.objects.get(name=FALL_DAMAGE_TYPE_NAME)
        # Null pools → config-default survivability pools apply (override).
        self.assertIsNone(dt.wound_pool)
        self.assertIsNone(dt.death_pool)

    def test_seeds_falling_category(self):
        ensure_fall_content()
        category = ConditionCategory.objects.get(name=FALLING_CATEGORY_NAME)
        self.assertTrue(category.is_negative)

    def test_seeds_plummeting_condition_non_progressive(self):
        ensure_fall_content()
        tmpl = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
        # Non-progressive marker: depth lives in the instance's severity
        # accumulator, not in stage progression.
        self.assertFalse(tmpl.has_progression)
        self.assertFalse(tmpl.is_stackable)

    def test_plummeting_is_non_expiring_permanent(self):
        # PERMANENT leaves rounds_remaining=None on apply, so the end-of-round
        # duration countdown never expires it mid-air (the I1 regression): the
        # descent loop alone removes it on impact / clean catch.
        ensure_fall_content()
        tmpl = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
        self.assertEqual(tmpl.default_duration_type, DurationType.PERMANENT)

    def test_plummeting_has_no_stages(self):
        # The stage severity_multiplier bands were dead data — descent depth is
        # the raw per-round severity accumulator, so no stages are seeded.
        ensure_fall_content()
        tmpl = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
        self.assertFalse(ConditionStage.objects.filter(condition=tmpl).exists())

    def test_plummeting_has_no_damage_over_time(self):
        # Impact is applied explicitly at the bottom (Task 6), not per-round DoT.
        ensure_fall_content()
        tmpl = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
        self.assertFalse(ConditionDamageOverTime.objects.filter(condition=tmpl).exists())

    def test_is_idempotent(self):
        ensure_fall_content()
        ensure_fall_content()
        self.assertEqual(DamageType.objects.filter(name=FALL_DAMAGE_TYPE_NAME).count(), 1)
        self.assertEqual(
            ConditionTemplate.objects.filter(name=PLUMMETING_CONDITION_NAME).count(),
            1,
        )
        tmpl = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
        # Stages not duplicated on the second call.
        self.assertEqual(
            tmpl.stages.count(),
            ConditionStage.objects.filter(condition=tmpl).count(),
        )
        first_orders = list(tmpl.stages.values_list("stage_order", flat=True))
        self.assertEqual(len(first_orders), len(set(first_orders)))
