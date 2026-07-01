"""Sunlight Exposure condition + radiant DoT seed (#1588)."""

from django.test import TestCase

from world.conditions.factories import ensure_radiant_damage_type
from world.conditions.models import ConditionDamageOverTime, ConditionTemplate
from world.species.factories import ensure_sunlight_exposure_content


class EnsureSunlightExposureContentTest(TestCase):
    def test_creates_template_with_radiant_dot(self):
        radiant = ensure_radiant_damage_type()
        tpl = ensure_sunlight_exposure_content()
        self.assertEqual(tpl.name, "Sunlight Exposure")
        dot = ConditionDamageOverTime.objects.get(condition=tpl)
        self.assertEqual(dot.damage_type, radiant)
        self.assertGreater(dot.base_damage, 0)

    def test_idempotent(self):
        ensure_radiant_damage_type()
        first = ensure_sunlight_exposure_content()
        second = ensure_sunlight_exposure_content()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            ConditionTemplate.objects.filter(name="Sunlight Exposure").count(),
            1,
        )
        self.assertEqual(
            ConditionDamageOverTime.objects.filter(condition=first).count(),
            1,
        )
