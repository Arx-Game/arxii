"""Intoxication + restoration effects (#2852). SQLite tier — apply_condition /
advance_condition_severity are patched where PG-only machinery would fire."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.intoxication_content import (
    BLACKOUT_THRESHOLD,
    ensure_intoxication_content,
)
from world.conditions.intoxication_service import imbibe
from world.fatigue.services import get_or_create_fatigue_pool, recover_fatigue


class RecoverFatigueTest(TestCase):
    def test_recovers_partially_and_floors_at_zero(self):
        sheet = CharacterSheetFactory()
        pool = get_or_create_fatigue_pool(sheet)
        pool.set_current("physical", 5)
        pool.save()
        self.assertEqual(recover_fatigue(sheet, "physical", 3), 3)
        self.assertEqual(get_or_create_fatigue_pool(sheet).get_current("physical"), 2)
        self.assertEqual(recover_fatigue(sheet, "physical", 10), 2)
        self.assertEqual(get_or_create_fatigue_pool(sheet).get_current("physical"), 0)
        self.assertEqual(recover_fatigue(sheet, "physical", 10), 0)


class IntoxicationContentTest(TestCase):
    def test_seed_creates_staged_intoxicated_and_hungover(self):
        from world.conditions.models import ConditionTemplate

        ensure_intoxication_content()
        intoxicated = ConditionTemplate.objects.get(name="Intoxicated")
        self.assertTrue(intoxicated.has_progression)
        self.assertEqual(intoxicated.stages.count(), 4)
        hungover = ConditionTemplate.objects.get(name="Hungover")
        self.assertFalse(hungover.has_progression)

    def test_hungover_carries_the_willpower_penalty(self):
        """The #2845 moon impairment predicate reads exactly this row."""
        from world.conditions.models import ConditionModifierEffect, ConditionTemplate
        from world.traits.factories import TraitFactory
        from world.traits.models import TraitType

        TraitFactory(name="willpower", trait_type=TraitType.STAT)
        ensure_intoxication_content()
        hungover = ConditionTemplate.objects.get(name="Hungover")
        effect = ConditionModifierEffect.objects.get(condition=hungover)
        self.assertLess(effect.value, 0)
        self.assertEqual(effect.modifier_target.name, "willpower")


class ImbibeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_intoxication_content()

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def test_first_drink_applies_at_potency(self):
        with (
            patch("world.conditions.services.apply_condition") as apply,
            patch("world.conditions.services.get_active_conditions", return_value=[]),
        ):
            result = imbibe(self.character, potency=2)
        self.assertTrue(result.applied)
        self.assertEqual(result.severity, 2)
        self.assertFalse(result.passed_out)
        self.assertEqual(apply.call_args.kwargs.get("severity"), 2)

    def test_further_drinks_advance_severity(self):
        from world.conditions.models import ConditionTemplate

        template = ConditionTemplate.objects.get(name="Intoxicated")
        instance = MagicMock()
        instance.condition_id = template.pk
        instance.severity = 3
        with (
            patch(
                "world.conditions.services.get_active_conditions",
                return_value=[instance],
            ),
            patch("world.conditions.services.advance_condition_severity") as advance,
        ):
            result = imbibe(self.character, potency=2)
        advance.assert_called_once_with(instance, 2)
        self.assertTrue(result.applied)

    def test_blackout_drink_rolls_the_stomach_and_drops_the_drinker(self):
        from world.conditions.models import ConditionTemplate

        template = ConditionTemplate.objects.get(name="Intoxicated")
        instance = MagicMock()
        instance.condition_id = template.pk
        instance.severity = BLACKOUT_THRESHOLD
        with (
            patch(
                "world.conditions.services.get_active_conditions",
                return_value=[instance],
            ),
            patch("world.conditions.services.advance_condition_severity"),
            patch(
                "world.conditions.intoxication_service._stomach_holds",
                return_value=False,
            ),
            patch("world.conditions.intoxication_service._pass_out") as drop,
        ):
            result = imbibe(self.character, potency=1)
        drop.assert_called_once()
        self.assertTrue(result.passed_out)

    def test_iron_stomach_stays_up(self):
        from world.conditions.models import ConditionTemplate

        template = ConditionTemplate.objects.get(name="Intoxicated")
        instance = MagicMock()
        instance.condition_id = template.pk
        instance.severity = BLACKOUT_THRESHOLD
        with (
            patch(
                "world.conditions.services.get_active_conditions",
                return_value=[instance],
            ),
            patch("world.conditions.services.advance_condition_severity"),
            patch(
                "world.conditions.intoxication_service._stomach_holds",
                return_value=True,
            ),
            patch("world.conditions.intoxication_service._pass_out") as drop,
        ):
            result = imbibe(self.character, potency=1)
        drop.assert_not_called()
        self.assertFalse(result.passed_out)

    def test_pass_out_applies_unconscious_and_hungover(self):
        from world.conditions.intoxication_service import _pass_out

        with patch("world.conditions.services.apply_condition") as apply:
            _pass_out(self.character)
        applied_names = {call.args[1].name for call in apply.call_args_list}
        self.assertIn("Hungover", applied_names)


class RestorationEffectHandlerTest(TestCase):
    def _effect(self, **kwargs):
        effect = MagicMock()
        for key, value in kwargs.items():
            setattr(effect, key, value)
        effect.target = "self"
        return effect

    def _context(self, character):
        context = MagicMock()
        context.character = character
        context.target = None
        return context

    def test_restore_fatigue_effect_recovers(self):
        from world.mechanics.effect_handlers import _restore_fatigue

        sheet = CharacterSheetFactory()
        pool = get_or_create_fatigue_pool(sheet)
        pool.set_current("physical", 4)
        pool.save()
        effect = self._effect(fatigue_amount=3, fatigue_category="physical")
        applied = _restore_fatigue(effect, self._context(sheet.character))
        self.assertTrue(applied.applied)
        self.assertEqual(get_or_create_fatigue_pool(sheet).get_current("physical"), 1)

    def test_restore_anima_clamps_to_maximum(self):
        from world.magic.models.anima import CharacterAnima
        from world.mechanics.effect_handlers import _restore_anima

        sheet = CharacterSheetFactory()
        CharacterAnima.objects.update_or_create(
            character=sheet, defaults={"current": 8, "maximum": 10}
        )
        effect = self._effect(anima_amount=5)
        applied = _restore_anima(effect, self._context(sheet.character))
        self.assertTrue(applied.applied)
        self.assertEqual(CharacterAnima.objects.get(character=sheet).current, 10)

    def test_intoxicate_effect_routes_through_imbibe(self):
        from world.mechanics.effect_handlers import _intoxicate

        sheet = CharacterSheetFactory()
        effect = self._effect(intoxication_potency=2)
        with patch("world.conditions.intoxication_service.imbibe") as drink:
            drink.return_value = MagicMock(applied=True, description="ok")
            applied = _intoxicate(effect, self._context(sheet.character))
        drink.assert_called_once()
        self.assertEqual(drink.call_args.kwargs.get("potency"), 2)
        self.assertTrue(applied.applied)


class SubstanceLaddersTest(TestCase):
    """Dusted/Hazed (#2862): the intoxicant override + pass-out ladder gate."""

    @classmethod
    def setUpTestData(cls):
        ensure_intoxication_content()

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character

    def test_seed_creates_the_drug_ladders(self):
        from world.conditions.models import ConditionTemplate

        dusted = ConditionTemplate.objects.get(name="Dusted")
        hazed = ConditionTemplate.objects.get(name="Hazed")
        self.assertEqual(dusted.stages.count(), 4)
        self.assertEqual(hazed.stages.count(), 2)

    def test_override_advances_the_named_ladder(self):
        from world.conditions.models import ConditionTemplate

        dusted = ConditionTemplate.objects.get(name="Dusted")
        with (
            patch("world.conditions.services.apply_condition") as apply,
            patch("world.conditions.services.get_active_conditions", return_value=[]),
        ):
            result = imbibe(self.character, potency=3, condition_template=dusted)
        self.assertTrue(result.applied)
        self.assertEqual(apply.call_args.args[1], dusted)

    def test_dusted_reaches_the_pass_out_roll(self):
        from world.conditions.intoxication_content import BLACKOUT_THRESHOLD
        from world.conditions.models import ConditionTemplate

        dusted = ConditionTemplate.objects.get(name="Dusted")
        instance = MagicMock()
        instance.condition_id = dusted.pk
        instance.severity = BLACKOUT_THRESHOLD
        with (
            patch(
                "world.conditions.services.get_active_conditions",
                return_value=[instance],
            ),
            patch("world.conditions.services.advance_condition_severity"),
            patch(
                "world.conditions.intoxication_service._stomach_holds",
                return_value=False,
            ),
            patch("world.conditions.intoxication_service._pass_out") as drop,
        ):
            result = imbibe(self.character, potency=1, condition_template=dusted)
        drop.assert_called_once()
        self.assertTrue(result.passed_out)

    def test_hazed_can_never_drop_anyone(self):
        """Hazed tops out at Blissed — no stage reaches the pass-out depth."""
        from world.conditions.intoxication_content import BLACKOUT_THRESHOLD
        from world.conditions.models import ConditionTemplate

        hazed = ConditionTemplate.objects.get(name="Hazed")
        instance = MagicMock()
        instance.condition_id = hazed.pk
        instance.severity = BLACKOUT_THRESHOLD + 5
        with (
            patch(
                "world.conditions.services.get_active_conditions",
                return_value=[instance],
            ),
            patch("world.conditions.services.advance_condition_severity"),
            patch("world.conditions.intoxication_service._pass_out") as drop,
        ):
            result = imbibe(self.character, potency=1, condition_template=hazed)
        drop.assert_not_called()
        self.assertFalse(result.passed_out)
