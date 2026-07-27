"""Aging cron services (#2756): birthday tick, decline checks, death sweep.

All check resolution goes through force_check_outcome — no dice in tests.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance, ConditionModifierEffect
from world.mechanics.factories import max_health_modifier_target
from world.species.factories import SpeciesFactory
from world.traits.factories import CheckOutcomeFactory
from world.vitals.aging import (
    run_birthday_tick,
    run_death_sweep,
    run_decline_checks,
)
from world.vitals.constants import (
    AGING_CHECK_TYPE_NAME,
    FRAILTY_CONDITION_NAME,
    CharacterLifeState,
)
from world.vitals.factories import CharacterVitalsFactory


def _aware(year, month, day):
    return timezone.make_aware(timezone.datetime(year, month, day))


class BirthdayTickTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mortal = SpeciesFactory(name="Human (tick test)")
        cls.elf = SpeciesFactory(name="Elf (tick test)", eternal_youth=True, decline_start_age=None)

    def _sheet(self, species=None, **kwargs):
        sheet = CharacterSheetFactory(
            character=CharacterFactory(),
            birthday_month=6,
            birthday_day=12,
            matured_years=kwargs.pop("matured_years", 24),
            withered_years=0,
            **kwargs,
        )
        sheet.species = species or self.mortal
        sheet.save()
        return sheet

    def test_birthday_in_window_advances_matured_years(self):
        sheet = self._sheet()
        aged = run_birthday_tick(ic_start=_aware(1020, 6, 1), ic_end=_aware(1020, 6, 30))
        sheet.refresh_from_db()
        self.assertEqual(aged, 1)
        self.assertEqual(sheet.matured_years, 25)

    def test_birthday_outside_window_is_untouched(self):
        sheet = self._sheet()
        run_birthday_tick(ic_start=_aware(1020, 7, 1), ic_end=_aware(1020, 7, 30))
        sheet.refresh_from_db()
        self.assertEqual(sheet.matured_years, 24)

    def test_time_skip_window_catches_every_birthday(self):
        sheet = self._sheet()
        run_birthday_tick(ic_start=_aware(1020, 6, 1), ic_end=_aware(1023, 6, 30))
        sheet.refresh_from_db()
        self.assertEqual(sheet.matured_years, 28)  # birthdays 1020-1023

    def test_paused_and_eternal_youth_are_skipped(self):
        paused = self._sheet(aging_paused=True)
        elf = self._sheet(species=self.elf)
        run_birthday_tick(ic_start=_aware(1020, 6, 1), ic_end=_aware(1020, 6, 30))
        paused.refresh_from_db()
        elf.refresh_from_db()
        self.assertEqual(paused.matured_years, 24)
        self.assertEqual(elf.matured_years, 24)


class DeclineCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mortal = SpeciesFactory(name="Human (decline test)")
        cls.check_type = CheckTypeFactory(name=AGING_CHECK_TYPE_NAME)
        cls.frailty = ConditionTemplateFactory(name=FRAILTY_CONDITION_NAME)
        ConditionModifierEffect.objects.create(
            condition=cls.frailty,
            modifier_target=max_health_modifier_target(),
            value=-1,
            scales_with_severity=True,
        )
        cls.fail_outcome = CheckOutcomeFactory(name="Failure (aging)", success_level=-1)
        cls.partial_outcome = CheckOutcomeFactory(name="Partial Success (aging)", success_level=0)
        cls.success_outcome = CheckOutcomeFactory(name="Success (aging)", success_level=1)

    def _elder(self, biological=70, base_health=100):
        character = CharacterFactory()
        sheet = CharacterSheetFactory(
            character=character, matured_years=biological, withered_years=0
        )
        sheet.species = self.mortal
        sheet.save()
        CharacterVitalsFactory(
            character_sheet=sheet,
            base_max_health=base_health,
            max_health=base_health,
            health=base_health,
        )
        return sheet

    def _frailty_severity(self, sheet):
        instance = ConditionInstance.objects.filter(
            target=sheet.character, condition=self.frailty
        ).first()
        return instance.severity if instance else 0

    def test_failure_deepens_frailty_and_difficulty_scales_with_age(self):
        sheet = self._elder(biological=70)
        with force_check_outcome(self.fail_outcome) as capture:
            checked = run_decline_checks(ic_now=_aware(1020, 1, 1))
        self.assertEqual(checked, 1)
        self.assertEqual(self._frailty_severity(sheet), 2)
        # PLACEHOLDER K=7: (70 - 60) years past threshold x 7 points.
        self.assertEqual(capture.target_difficulty, 70)
        sheet.vitals.refresh_from_db()
        self.assertEqual(sheet.vitals.max_health, 98)

    def test_partial_success_costs_one(self):
        sheet = self._elder()
        with force_check_outcome(self.partial_outcome):
            run_decline_checks(ic_now=_aware(1020, 1, 1))
        self.assertEqual(self._frailty_severity(sheet), 1)

    def test_success_costs_nothing(self):
        sheet = self._elder()
        with force_check_outcome(self.success_outcome):
            run_decline_checks(ic_now=_aware(1020, 1, 1))
        self.assertEqual(self._frailty_severity(sheet), 0)

    def test_under_threshold_is_not_checked(self):
        self._elder(biological=50)
        with force_check_outcome(self.fail_outcome):
            checked = run_decline_checks(ic_now=_aware(1020, 1, 1))
        self.assertEqual(checked, 0)

    def test_crossing_the_floor_opens_the_dying_window(self):
        sheet = self._elder(base_health=10)  # floor at 20% = 2
        ConditionInstance.objects.create(target=sheet.character, condition=self.frailty, severity=7)
        with force_check_outcome(self.fail_outcome):
            run_decline_checks(ic_now=_aware(1020, 1, 1))
        sheet.vitals.refresh_from_db()
        # severity 9 -> max health 1 <= floor 2: deadline stamped 30 IC days out.
        self.assertIsNotNone(sheet.vitals.aging_death_ic_deadline)
        self.assertEqual(
            sheet.vitals.aging_death_ic_deadline, _aware(1020, 1, 1) + timedelta(days=30)
        )


class DeathSweepTests(TestCase):
    def test_past_deadline_resolves_death(self):
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)
        vitals = CharacterVitalsFactory(
            character_sheet=sheet,
            aging_death_ic_deadline=_aware(1020, 1, 1),
        )
        deaths = run_death_sweep(ic_now=_aware(1020, 2, 1))
        vitals.refresh_from_db()
        self.assertEqual(deaths, 1)
        self.assertEqual(vitals.life_state, CharacterLifeState.DEAD)

    def test_future_deadline_holds(self):
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)
        vitals = CharacterVitalsFactory(
            character_sheet=sheet,
            aging_death_ic_deadline=_aware(1020, 3, 1),
        )
        deaths = run_death_sweep(ic_now=_aware(1020, 2, 1))
        vitals.refresh_from_db()
        self.assertEqual(deaths, 0)
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)
