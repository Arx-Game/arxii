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

# NEW imports for this task only — BattleFactory, BattleSideFactory,
# TechniqueFactory, ActionTemplateFactory, WeatherTypeFactory, BattleActionKind,
# BattleActionScope were already imported by Tasks 1-3. CharacterTechniqueFactory
# is new here and is reused (without re-import) by every later task.
from world.battles.exceptions import (
    InvalidEnvironmentScopeError,
    MissingEnvironmentTargetError,
    NoCommandHierarchyError,
)

# NEW imports for this task only — BattleFactory, BattlePlaceFactory, AreaFactory,
# WeatherTypeFactory were already imported by Task 2; CapabilityTypeFactory,
# PropertyFactory already imported by Task 4. Do not re-import them.
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleRoundFactory,
    BattleSideFactory,
    BattleUnitFactory,
    WeatherTypeCapabilityChallengeFactory,
    WeatherTypePropertyEffectFactory,
)
from world.battles.resolution import (
    _weather_capability_modifier,
    _weather_property_modifier,
    effective_weather,
)
from world.battles.services import declare_battle_action
from world.conditions.factories import CapabilityTypeFactory
from world.magic.factories import CharacterTechniqueFactory, TechniqueFactory
from world.mechanics.factories import PropertyFactory
from world.scenes.constants import RoundStatus
from world.weather.factories import RegionWeatherStateFactory, WeatherTypeFactory

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


class EffectiveWeatherTests(TestCase):
    def test_place_override_wins_over_everything(self) -> None:
        area = AreaFactory()
        ambient = WeatherTypeFactory()
        battle_cast = WeatherTypeFactory()
        local = WeatherTypeFactory()
        RegionWeatherStateFactory(area=area, weather_type=ambient)
        battle = BattleFactory(region=area, weather_override=battle_cast)
        place = BattlePlaceFactory(battle=battle, weather_override=local)

        self.assertEqual(effective_weather(place), local)

    def test_battle_override_wins_when_no_place_override(self) -> None:
        area = AreaFactory()
        ambient = WeatherTypeFactory()
        battle_cast = WeatherTypeFactory()
        RegionWeatherStateFactory(area=area, weather_type=ambient)
        battle = BattleFactory(region=area, weather_override=battle_cast)
        place = BattlePlaceFactory(battle=battle)

        self.assertEqual(effective_weather(place), battle_cast)

    def test_ambient_wins_when_no_overrides(self) -> None:
        area = AreaFactory()
        ambient = WeatherTypeFactory()
        RegionWeatherStateFactory(area=area, weather_type=ambient)
        battle = BattleFactory(region=area)
        place = BattlePlaceFactory(battle=battle)

        self.assertEqual(effective_weather(place), ambient)

    def test_none_when_no_overrides_and_no_region(self) -> None:
        battle = BattleFactory()
        place = BattlePlaceFactory(battle=battle)

        self.assertIsNone(effective_weather(place))

    def test_none_when_place_is_none(self) -> None:
        self.assertIsNone(effective_weather(None))


class WeatherModifierTests(TestCase):
    def test_weather_property_modifier_sums_matching_rows(self) -> None:
        weather_type = WeatherTypeFactory()
        battle = BattleFactory(weather_override=weather_type)
        place = BattlePlaceFactory(battle=battle)
        side = BattleSideFactory(battle=battle)
        unit = BattleUnitFactory(battle=battle, side=side, place=place)
        prop = PropertyFactory()
        unit.properties.add(prop)
        WeatherTypePropertyEffectFactory(weather_type=weather_type, property=prop, modifier=15)

        self.assertEqual(_weather_property_modifier(place, unit), 15)

    def test_weather_property_modifier_zero_when_no_weather(self) -> None:
        battle = BattleFactory()
        place = BattlePlaceFactory(battle=battle)
        side = BattleSideFactory(battle=battle)
        unit = BattleUnitFactory(battle=battle, side=side, place=place)

        self.assertEqual(_weather_property_modifier(place, unit), 0)

    def test_weather_capability_modifier_applies_below_threshold(self) -> None:
        from world.battles.models import BattleUnitCapability

        weather_type = WeatherTypeFactory()
        battle = BattleFactory(weather_override=weather_type)
        place = BattlePlaceFactory(battle=battle)
        side = BattleSideFactory(battle=battle)
        unit = BattleUnitFactory(battle=battle, side=side, place=place)
        capability = CapabilityTypeFactory()
        BattleUnitCapability.objects.create(unit=unit, capability=capability, value=0)
        WeatherTypeCapabilityChallengeFactory(
            weather_type=weather_type, capability=capability, threshold=1, modifier=-20
        )

        self.assertEqual(_weather_capability_modifier(place, unit), -20)

    def test_weather_capability_modifier_zero_when_at_or_above_threshold(self) -> None:
        from world.battles.models import BattleUnitCapability

        weather_type = WeatherTypeFactory()
        battle = BattleFactory(weather_override=weather_type)
        place = BattlePlaceFactory(battle=battle)
        side = BattleSideFactory(battle=battle)
        unit = BattleUnitFactory(battle=battle, side=side, place=place)
        capability = CapabilityTypeFactory()
        BattleUnitCapability.objects.create(unit=unit, capability=capability, value=1)
        WeatherTypeCapabilityChallengeFactory(
            weather_type=weather_type, capability=capability, threshold=1, modifier=-20
        )

        self.assertEqual(_weather_capability_modifier(place, unit), 0)


class DeclareEnvironmentValidationTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle)
        self.participant = BattleParticipantFactory(battle=self.battle, side=self.side)
        BattleRoundFactory(battle=self.battle, status=RoundStatus.DECLARING)

    def test_unit_scope_rejected_for_set_environment(self) -> None:
        technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), target_weather_type=WeatherTypeFactory()
        )
        CharacterTechniqueFactory(character=self.participant.character_sheet, technique=technique)
        with self.assertRaises(InvalidEnvironmentScopeError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.SET_ENVIRONMENT,
                technique=technique,
                scope=BattleActionScope.UNIT,
            )

    def test_side_scope_rejected_for_set_environment(self) -> None:
        technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), target_weather_type=WeatherTypeFactory()
        )
        CharacterTechniqueFactory(character=self.participant.character_sheet, technique=technique)
        with self.assertRaises(InvalidEnvironmentScopeError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.SET_ENVIRONMENT,
                technique=technique,
                scope=BattleActionScope.SIDE,
                target_side=self.side,
            )

    def test_missing_target_weather_type_rejected(self) -> None:
        technique = TechniqueFactory(action_template=ActionTemplateFactory())
        CharacterTechniqueFactory(character=self.participant.character_sheet, technique=technique)
        with self.assertRaises(MissingEnvironmentTargetError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.SET_ENVIRONMENT,
                technique=technique,
                scope=BattleActionScope.BATTLE,
            )

    def test_battle_scope_requires_command_hierarchy(self) -> None:
        technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), target_weather_type=WeatherTypeFactory()
        )
        CharacterTechniqueFactory(character=self.participant.character_sheet, technique=technique)
        with self.assertRaises(NoCommandHierarchyError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.SET_ENVIRONMENT,
                technique=technique,
                scope=BattleActionScope.BATTLE,
            )
