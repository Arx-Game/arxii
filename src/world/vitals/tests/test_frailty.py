"""Frailty condition → permanent max-health reduction (#2756).

Frailty is the old-age toll: its severity counts accumulated decline, and a
ConditionModifierEffect targeting MAX_HEALTH (-1, scales_with_severity) folds
into recompute_max_health — the first writer for that target.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionModifierEffect
from world.mechanics.factories import max_health_modifier_target
from world.vitals.constants import FRAILTY_CONDITION_NAME
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import frailty_floor_reached, recompute_max_health


class FrailtyMaxHealthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.vitals = CharacterVitalsFactory(
            character_sheet=cls.sheet, base_max_health=100, max_health=100, health=100
        )
        cls.template = ConditionTemplateFactory(name=FRAILTY_CONDITION_NAME)
        ConditionModifierEffect.objects.create(
            condition=cls.template,
            modifier_target=max_health_modifier_target(),
            value=-1,
            scales_with_severity=True,
        )

    def test_frailty_severity_reduces_max_health(self):
        ConditionInstanceFactory(target=self.character, condition=self.template, severity=15)

        new_max = recompute_max_health(self.sheet)

        self.assertEqual(new_max, 85)
        self.vitals.refresh_from_db()
        self.assertEqual(self.vitals.max_health, 85)
        self.assertEqual(self.vitals.health, 85)  # clamp-not-injure

    def test_no_frailty_leaves_max_health_alone(self):
        self.assertEqual(recompute_max_health(self.sheet), 100)

    def test_floor_detection_at_configured_fraction(self):
        # PLACEHOLDER floor fraction 0.20: floor is 20 of base 100.
        ConditionInstanceFactory(target=self.character, condition=self.template, severity=81)
        recompute_max_health(self.sheet)

        self.assertTrue(frailty_floor_reached(self.sheet))

    def test_floor_not_reached_above_fraction(self):
        ConditionInstanceFactory(target=self.character, condition=self.template, severity=15)
        recompute_max_health(self.sheet)

        self.assertFalse(frailty_floor_reached(self.sheet))
