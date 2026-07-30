"""Hazard-response prompt + AFK auto-flee tracking (#2846). SQLite tier —
ConditionInstance rows are created directly (no apply_condition PG path)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.hazard_prompt import (
    ensure_hazard_prompt,
    mark_endured,
    mark_responded,
    observe_hazard,
)
from world.conditions.models import ConditionInstance, HazardResponseState
from world.species.factories import ensure_sunlight_exposure_content
from world.vitals.factories import CharacterVitalsFactory


class HazardPromptTest(TestCase):
    def setUp(self):
        self.template = ensure_sunlight_exposure_content()
        self.sheet = CharacterSheetFactory()
        self.vitals = CharacterVitalsFactory(character_sheet=self.sheet, health=100, max_health=100)
        self.character = self.sheet.character
        self.instance = ConditionInstance.objects.create(
            target=self.character, condition=self.template, severity=7
        )

    def _drop_health(self, amount: int) -> None:
        self.vitals.health -= amount
        self.vitals.save(update_fields=["health"])

    def test_ensure_creates_state_once_with_health_snapshot(self):
        state = ensure_hazard_prompt(self.instance)
        self.assertEqual(state.last_health_snapshot, 100)
        again = ensure_hazard_prompt(self.instance)
        self.assertEqual(state.pk, again.pk)
        self.assertEqual(HazardResponseState.objects.count(), 1)

    def test_first_damage_instance_never_flees(self):
        ensure_hazard_prompt(self.instance)
        self._drop_health(5)
        calls = []
        fled = observe_hazard(
            self.instance, flee=lambda: calls.append(1) or True, auto_flee_after=2
        )
        self.assertFalse(fled)
        self.assertEqual(calls, [])

    def test_flees_after_second_unanswered_damage_instance(self):
        ensure_hazard_prompt(self.instance)
        self._drop_health(5)
        observe_hazard(self.instance, flee=lambda: True, auto_flee_after=2)
        self._drop_health(5)
        calls = []
        fled = observe_hazard(
            self.instance, flee=lambda: calls.append(1) or True, auto_flee_after=2
        )
        self.assertTrue(fled)
        self.assertEqual(calls, [1])
        state = HazardResponseState.objects.get(condition_instance=self.instance)
        self.assertIsNotNone(state.responded_at)

    def test_no_damage_observation_without_health_drop(self):
        ensure_hazard_prompt(self.instance)
        observe_hazard(self.instance, flee=lambda: True, auto_flee_after=2)
        observe_hazard(self.instance, flee=lambda: True, auto_flee_after=2)
        state = HazardResponseState.objects.get(condition_instance=self.instance)
        self.assertEqual(state.damage_observations, 0)

    def test_endure_window_suppresses_auto_flee(self):
        mark_endured(self.instance, until=timezone.now() + timedelta(hours=2))
        self._drop_health(5)
        observe_hazard(self.instance, flee=lambda: True, auto_flee_after=2)
        self._drop_health(5)
        calls = []
        fled = observe_hazard(
            self.instance, flee=lambda: calls.append(1) or True, auto_flee_after=2
        )
        self.assertFalse(fled)
        self.assertEqual(calls, [])

    def test_responded_player_never_auto_flees(self):
        mark_responded(self.instance)
        self._drop_health(5)
        observe_hazard(self.instance, flee=lambda: True, auto_flee_after=2)
        self._drop_health(5)
        calls = []
        fled = observe_hazard(
            self.instance, flee=lambda: calls.append(1) or True, auto_flee_after=2
        )
        self.assertFalse(fled)
        self.assertEqual(calls, [])

    def test_failed_flee_does_not_mark_responded(self):
        """No reachable refuge: the guard stays armed (abandonment pool backstop)."""
        ensure_hazard_prompt(self.instance)
        self._drop_health(5)
        observe_hazard(self.instance, flee=lambda: False, auto_flee_after=2)
        self._drop_health(5)
        fled = observe_hazard(self.instance, flee=lambda: False, auto_flee_after=2)
        self.assertFalse(fled)
        state = HazardResponseState.objects.get(condition_instance=self.instance)
        self.assertIsNone(state.responded_at)
