"""Tests for battle-scope environmental effects (#1715).

Two-tier weather: Battle-wide ambient/cast weather is the default; BattlePlace
carries a local-exception override that beats the battle-wide value at one
front only. See world.battles.resolution.effective_weather.
"""

from __future__ import annotations

# NEW imports for this task only — CharacterTechniqueFactory was already
# imported by Task 6; do not re-import it here.
import types
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.areas.factories import AreaFactory

# NEW import for Task 8 only — BattleSideRole; SET_ENVIRONMENT_BASE_ROUNDS,
# SET_ENVIRONMENT_VP, BattleActionKind, BattleActionScope were already imported
# by Tasks 1-3. Do not re-import them.
from world.battles.constants import (
    SET_ENVIRONMENT_BASE_ROUNDS,
    SET_ENVIRONMENT_VP,
    BattleActionKind,
    BattleActionScope,
    BattleSideRole,
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
    resolve_battle_round,
)
from world.battles.services import begin_battle_round, declare_battle_action
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.covenants.constants import CommandTier, CovenantType
from world.covenants.factories import CovenantFactory, CovenantRankFactory, CovenantRoleFactory
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import set_engaged_membership
from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory, TechniqueFactory
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
        unit.military_unit.properties.add(prop)
        WeatherTypePropertyEffectFactory(weather_type=weather_type, property=prop, modifier=15)

        self.assertEqual(_weather_property_modifier(place, unit), 15)

    def test_weather_property_modifier_zero_when_no_weather(self) -> None:
        battle = BattleFactory()
        place = BattlePlaceFactory(battle=battle)
        side = BattleSideFactory(battle=battle)
        unit = BattleUnitFactory(battle=battle, side=side, place=place)

        self.assertEqual(_weather_property_modifier(place, unit), 0)

    def test_weather_capability_modifier_applies_below_threshold(self) -> None:
        from world.military.models import MilitaryUnitCapability

        weather_type = WeatherTypeFactory()
        battle = BattleFactory(weather_override=weather_type)
        place = BattlePlaceFactory(battle=battle)
        side = BattleSideFactory(battle=battle)
        unit = BattleUnitFactory(battle=battle, side=side, place=place)
        capability = CapabilityTypeFactory()
        MilitaryUnitCapability.objects.create(
            unit=unit.military_unit, capability=capability, value=0
        )
        WeatherTypeCapabilityChallengeFactory(
            weather_type=weather_type, capability=capability, threshold=1, modifier=-20
        )

        self.assertEqual(_weather_capability_modifier(place, unit), -20)

    def test_weather_capability_modifier_zero_when_at_or_above_threshold(self) -> None:
        from world.military.models import MilitaryUnitCapability

        weather_type = WeatherTypeFactory()
        battle = BattleFactory(weather_override=weather_type)
        place = BattlePlaceFactory(battle=battle)
        side = BattleSideFactory(battle=battle)
        unit = BattleUnitFactory(battle=battle, side=side, place=place)
        capability = CapabilityTypeFactory()
        MilitaryUnitCapability.objects.create(
            unit=unit.military_unit, capability=capability, value=1
        )
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


def _success_result(level: int = 2) -> types.SimpleNamespace:
    return types.SimpleNamespace(success_level=level)


def _grant_command_tier(*, participant, side, covenant, tier) -> None:
    rank = CovenantRankFactory(covenant=covenant)
    role = CovenantRoleFactory(
        covenant_type=CovenantType.BATTLE,
        command_tier=tier,
        slug=f"env-e2e-{tier}-{participant.pk}",
    )
    membership = CharacterCovenantRole.objects.create(
        character_sheet=participant.character_sheet,
        covenant_role=role,
        covenant=covenant,
        rank=rank,
        engaged=False,
    )
    set_engaged_membership(membership=membership)


class SetEnvironmentSuccessTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.side = BattleSideFactory(battle=self.battle)
        self.covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.side.covenant = self.covenant
        self.side.save()
        self.character = CharacterSheetFactory()
        self.participant = BattleParticipantFactory(
            battle=self.battle, side=self.side, character_sheet=self.character
        )
        _grant_command_tier(
            participant=self.participant,
            side=self.side,
            covenant=self.covenant,
            tier=CommandTier.SUPREME,
        )
        self.weather_type = WeatherTypeFactory()
        self.technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), target_weather_type=self.weather_type
        )
        CharacterTechniqueFactory(character=self.character, technique=self.technique)
        CharacterAnimaFactory(character=self.character.character)

    def test_battle_scope_cast_sets_battle_weather_override(self) -> None:
        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SET_ENVIRONMENT,
            technique=self.technique,
            scope=BattleActionScope.BATTLE,
        )

        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(1)
            resolve_battle_round(battle_round=battle_round)

        self.battle.refresh_from_db()
        self.assertEqual(self.battle.weather_override_id, self.weather_type.pk)
        # round_number=1, SET_ENVIRONMENT_BASE_ROUNDS=1, success_level=1 -> expires at 3.
        self.assertEqual(self.battle.weather_override_expires_round, 3)

    def test_place_scope_cast_sets_local_exception_only(self) -> None:
        place = BattlePlaceFactory(battle=self.battle)
        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SET_ENVIRONMENT,
            technique=self.technique,
            scope=BattleActionScope.PLACE,
            target_place=place,
        )

        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(1)
            resolve_battle_round(battle_round=battle_round)

        place.refresh_from_db()
        self.battle.refresh_from_db()
        self.assertEqual(place.weather_override_id, self.weather_type.pk)
        self.assertIsNone(self.battle.weather_override_id)

    def test_place_local_exception_beats_active_battle_wide_override(self) -> None:
        other_weather = WeatherTypeFactory()
        self.battle.weather_override = other_weather
        self.battle.weather_override_expires_round = 99
        self.battle.save()
        place = BattlePlaceFactory(battle=self.battle)
        other_place = BattlePlaceFactory(battle=self.battle)
        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SET_ENVIRONMENT,
            technique=self.technique,
            scope=BattleActionScope.PLACE,
            target_place=place,
        )

        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(1)
            resolve_battle_round(battle_round=battle_round)

        self.assertEqual(effective_weather(place), self.weather_type)
        self.assertEqual(effective_weather(other_place), other_weather)

    def test_minimum_success_level_produces_at_least_two_active_rounds(self) -> None:
        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.SET_ENVIRONMENT,
            technique=self.technique,
            scope=BattleActionScope.BATTLE,
        )

        with patch("world.battles.resolution.perform_check") as mock_check:
            mock_check.return_value = _success_result(1)  # minimum possible success
            resolve_battle_round(battle_round=battle_round)

        self.battle.refresh_from_db()
        # Active for round_number (1) through weather_override_expires_round (3)
        # inclusive per the round-boundary-expiry rule in Task 8 — at least 2
        # rounds beyond the casting round itself.
        self.assertGreaterEqual(self.battle.weather_override_expires_round - 1, 2)


class RoundBoundaryExpiryTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory()
        self.weather_type = WeatherTypeFactory()

    def test_battle_override_clears_after_its_final_active_round(self) -> None:
        self.battle.weather_override = self.weather_type
        self.battle.weather_override_expires_round = 5
        self.battle.save()
        battle_round = BattleRoundFactory(
            battle=self.battle, round_number=5, status=RoundStatus.DECLARING
        )

        resolve_battle_round(battle_round=battle_round)

        self.battle.refresh_from_db()
        # Still active THROUGH round 5 (the expiry round itself) — not cleared yet.
        self.assertEqual(self.battle.weather_override_id, self.weather_type.pk)

    def test_battle_override_clears_entering_round_after_expiry(self) -> None:
        self.battle.weather_override = self.weather_type
        self.battle.weather_override_expires_round = 5
        self.battle.save()
        battle_round = BattleRoundFactory(
            battle=self.battle, round_number=6, status=RoundStatus.DECLARING
        )

        resolve_battle_round(battle_round=battle_round)

        self.battle.refresh_from_db()
        self.assertIsNone(self.battle.weather_override_id)
        self.assertIsNone(self.battle.weather_override_expires_round)

    def test_place_override_clears_independently_of_battle_tier(self) -> None:
        place = BattlePlaceFactory(
            battle=self.battle,
            weather_override=self.weather_type,
            weather_override_expires_round=3,
        )
        other_weather = WeatherTypeFactory()
        self.battle.weather_override = other_weather
        self.battle.weather_override_expires_round = 99  # battle tier still active
        self.battle.save()
        battle_round = BattleRoundFactory(
            battle=self.battle, round_number=4, status=RoundStatus.DECLARING
        )

        resolve_battle_round(battle_round=battle_round)

        place.refresh_from_db()
        self.battle.refresh_from_db()
        self.assertIsNone(place.weather_override_id)
        self.assertEqual(self.battle.weather_override_id, other_weather.pk)

    def test_set_environment_resolves_before_strike_in_same_round(self) -> None:
        """A BATTLE-scoped SET_ENVIRONMENT cast is visible to a STRIKE at any
        place resolved in the very same round (same-round-first, like REPEL)."""
        side_a = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        side_b = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        side_a.covenant = covenant
        side_a.save()
        # striker is created *before* caster, so it has the lower pk.
        # BattleActionDeclaration.Meta.ordering sorts by (battle_round,
        # participant) — i.e. by participant pk — so without this ordering,
        # the unsorted queryset would already put STRIKE (lower pk) ahead of
        # SET_ENVIRONMENT (higher pk), the same order the resolution sort is
        # meant to enforce. Only resolve_battle_round's explicit
        # SET_ENVIRONMENT-first `.sort(...)` — not incidental pk/insertion
        # order — can make the assertion below pass (Task 8 review finding;
        # same bug class as #1712 final review Finding 2, which motivated the
        # analogous ordering in RepelResolutionTests).
        striker = BattleParticipantFactory(battle=self.battle, side=side_a)
        caster = BattleParticipantFactory(battle=self.battle, side=side_a)
        _grant_command_tier(
            participant=caster, side=side_a, covenant=covenant, tier=CommandTier.SUPREME
        )
        place = BattlePlaceFactory(battle=self.battle)
        target_unit = BattleUnitFactory(battle=self.battle, side=side_b, place=place)
        prop = PropertyFactory()
        target_unit.military_unit.properties.add(prop)
        env_technique = TechniqueFactory(
            action_template=ActionTemplateFactory(), target_weather_type=self.weather_type
        )
        strike_technique = TechniqueFactory(action_template=ActionTemplateFactory())
        WeatherTypePropertyEffectFactory(weather_type=self.weather_type, property=prop, modifier=15)
        for participant, technique in (
            (caster, env_technique),
            (striker, strike_technique),
        ):
            CharacterTechniqueFactory(character=participant.character_sheet, technique=technique)
            CharacterAnimaFactory(character=participant.character_sheet.character)
        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=striker,
            action_kind=BattleActionKind.STRIKE,
            technique=strike_technique,
            target_unit=target_unit,
        )
        declare_battle_action(
            participant=caster,
            action_kind=BattleActionKind.SET_ENVIRONMENT,
            technique=env_technique,
            scope=BattleActionScope.BATTLE,
        )

        captured_modifiers: list[int] = []

        def _capture(character, check_type, extra_modifiers=0, situation_ctx=None):
            captured_modifiers.append(extra_modifiers)
            return _success_result(2)

        with patch("world.battles.resolution.perform_check", side_effect=_capture):
            resolve_battle_round(battle_round=battle_round)

        # SET_ENVIRONMENT resolves first (same-round-first sort): its own check
        # has no target_unit, so every unit-keyed modifier term is 0 for it.
        # STRIKE resolves second, same round, and must see the +15
        # weather-property modifier now that the battle-wide override is set.
        self.assertEqual(len(captured_modifiers), 2)
        self.assertEqual(captured_modifiers[0], 0)
        self.assertEqual(captured_modifiers[1], 15)
