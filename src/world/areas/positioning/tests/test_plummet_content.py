"""Tests for the plummet content seed service (#1228, Task 3).

``ensure_fall_content`` idempotently seeds the fall ``DamageType`` and the
staged "Plummeting" ``ConditionTemplate`` (descent-depth stages, no DoT — the
impact is applied explicitly at the bottom in Task 6). The fall DamageType
leaves its wound/death pools null so the config-default survivability pools
apply, exactly like the poison DamageType.
"""

from django.test import TestCase

from world.areas.positioning.constants import (
    FALL_DAMAGE_TYPE_NAME,
    FALLING_CATEGORY_NAME,
    PLUMMETING_CONDITION_NAME,
)
from world.areas.positioning.plummet_content import ensure_fall_content
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

    def test_seeds_plummeting_condition_progressive(self):
        ensure_fall_content()
        tmpl = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
        self.assertTrue(tmpl.has_progression)
        self.assertFalse(tmpl.is_stackable)

    def test_plummeting_has_severity_ramping_stages(self):
        ensure_fall_content()
        tmpl = ConditionTemplate.get_by_name(PLUMMETING_CONDITION_NAME)
        stages = list(tmpl.stages.order_by("stage_order"))
        self.assertGreaterEqual(len(stages), 2)
        # severity_multiplier strictly increases with descent depth.
        multipliers = [s.severity_multiplier for s in stages]
        self.assertEqual(multipliers, sorted(multipliers))
        self.assertLess(multipliers[0], multipliers[-1])
        # Non-terminal stages advance one stage per round (the descent cadence);
        # the terminal stage has no successor.
        for stage in stages[:-1]:
            self.assertEqual(stage.rounds_to_next, 1)
        self.assertIsNone(stages[-1].rounds_to_next)

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
