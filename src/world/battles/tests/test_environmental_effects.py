"""Tests for battle-scope environmental effects (#1715).

Two-tier weather: Battle-wide ambient/cast weather is the default; BattlePlace
carries a local-exception override that beats the battle-wide value at one
front only. See world.battles.resolution.effective_weather.
"""

from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.areas.factories import AreaFactory
from world.battles.constants import (
    SET_ENVIRONMENT_BASE_ROUNDS,
    SET_ENVIRONMENT_VP,
    BattleActionKind,
    BattleActionScope,
)
from world.battles.factories import BattleFactory, BattlePlaceFactory
from world.conditions.factories import CapabilityTypeFactory
from world.magic.factories import TechniqueFactory
from world.mechanics.factories import PropertyFactory
from world.weather.factories import WeatherTypeFactory

# NOTE for every subsequent task in this plan: this file's imports are added
# INCREMENTALLY, one task at a time, each import appearing exactly once at
# the point it's first needed — never re-import a name a prior task already
# imported. Each task's "Step 1" below shows only the NEW import lines that
# task introduces.


class EnvironmentConstantsTests(TestCase):
    def test_set_environment_action_kind_exists(self) -> None:
        self.assertEqual(BattleActionKind.SET_ENVIRONMENT, "set_environment")

    def test_battle_scope_exists(self) -> None:
        self.assertEqual(BattleActionScope.BATTLE, "battle")

    def test_tuning_constants_are_positive(self) -> None:
        self.assertGreaterEqual(SET_ENVIRONMENT_BASE_ROUNDS, 1)
        self.assertGreater(SET_ENVIRONMENT_VP, 0)


class WeatherFieldsExistTests(TestCase):
    def test_battle_has_region_and_weather_override_fields(self) -> None:
        area = AreaFactory()
        weather_type = WeatherTypeFactory()
        battle = BattleFactory(
            region=area, weather_override=weather_type, weather_override_expires_round=5
        )
        battle.refresh_from_db()
        self.assertEqual(battle.region_id, area.pk)
        self.assertEqual(battle.weather_override_id, weather_type.pk)
        self.assertEqual(battle.weather_override_expires_round, 5)

    def test_battle_weather_fields_default_to_none(self) -> None:
        battle = BattleFactory()
        self.assertIsNone(battle.region_id)
        self.assertIsNone(battle.weather_override_id)
        self.assertIsNone(battle.weather_override_expires_round)

    def test_battle_place_has_weather_override_fields(self) -> None:
        weather_type = WeatherTypeFactory()
        place = BattlePlaceFactory(weather_override=weather_type, weather_override_expires_round=3)
        place.refresh_from_db()
        self.assertEqual(place.weather_override_id, weather_type.pk)
        self.assertEqual(place.weather_override_expires_round, 3)

    def test_battle_place_weather_fields_default_to_none(self) -> None:
        place = BattlePlaceFactory()
        self.assertIsNone(place.weather_override_id)
        self.assertIsNone(place.weather_override_expires_round)


class TechniqueTargetWeatherTypeTests(TestCase):
    def test_technique_can_hold_a_target_weather_type(self) -> None:
        weather_type = WeatherTypeFactory()
        technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), target_weather_type=weather_type
        )
        technique.refresh_from_db()
        self.assertEqual(technique.target_weather_type_id, weather_type.pk)

    def test_technique_target_weather_type_defaults_to_none(self) -> None:
        technique = TechniqueFactory(action_template=ActionTemplateFactory())
        self.assertIsNone(technique.target_weather_type_id)


class WeatherEffectModelsTests(TestCase):
    def test_weather_type_property_effect_creation(self) -> None:
        from world.battles.models import WeatherTypePropertyEffect

        weather_type = WeatherTypeFactory()
        prop = PropertyFactory()
        row = WeatherTypePropertyEffect.objects.create(
            weather_type=weather_type, property=prop, modifier=15
        )
        self.assertEqual(row.modifier, 15)

    def test_weather_type_property_effect_unique_per_pair(self) -> None:
        from world.battles.models import WeatherTypePropertyEffect

        weather_type = WeatherTypeFactory()
        prop = PropertyFactory()
        WeatherTypePropertyEffect.objects.create(
            weather_type=weather_type, property=prop, modifier=15
        )
        with self.assertRaises(IntegrityError):
            WeatherTypePropertyEffect.objects.create(
                weather_type=weather_type, property=prop, modifier=-5
            )

    def test_weather_type_capability_challenge_creation(self) -> None:
        from world.battles.models import WeatherTypeCapabilityChallenge

        weather_type = WeatherTypeFactory()
        capability = CapabilityTypeFactory()
        row = WeatherTypeCapabilityChallenge.objects.create(
            weather_type=weather_type, capability=capability, threshold=1, modifier=-20
        )
        self.assertEqual(row.threshold, 1)
        self.assertEqual(row.modifier, -20)

    def test_weather_type_capability_challenge_unique_per_pair(self) -> None:
        from world.battles.models import WeatherTypeCapabilityChallenge

        weather_type = WeatherTypeFactory()
        capability = CapabilityTypeFactory()
        WeatherTypeCapabilityChallenge.objects.create(
            weather_type=weather_type, capability=capability, threshold=1, modifier=-20
        )
        with self.assertRaises(IntegrityError):
            WeatherTypeCapabilityChallenge.objects.create(
                weather_type=weather_type, capability=capability, threshold=2, modifier=-10
            )
