"""Tests for the CompanionAbility and CompanionOrder models (#1921)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.constants import ActionCategory
from world.companions.constants import CompanionAbilityKind, CompanionOrderKind
from world.companions.factories import CompanionArchetypeFactory
from world.companions.models import CompanionAbility, CompanionOrder


class CompanionAbilityModelTests(TestCase):
    def setUp(self):
        self.archetype = CompanionArchetypeFactory(name="Test Beast")

    def test_attack_ability_creates_clean(self):
        ability = CompanionAbility.objects.create(
            archetype=self.archetype,
            name="Rend",
            ability_kind=CompanionAbilityKind.ATTACK,
            attack_category=ActionCategory.PHYSICAL,
            base_damage=8,
        )
        ability.full_clean()
        self.assertEqual(ability.name, "Rend")
        self.assertEqual(ability.ability_kind, CompanionAbilityKind.ATTACK)

    def test_utility_ability_creates_clean(self):
        from world.mechanics.factories import PropertyFactory

        prop = PropertyFactory()
        ability = CompanionAbility.objects.create(
            archetype=self.archetype,
            name="Take Flight",
            ability_kind=CompanionAbilityKind.UTILITY,
            grants_property=prop,
        )
        ability.full_clean()
        self.assertEqual(ability.ability_kind, CompanionAbilityKind.UTILITY)

    def test_attack_ability_without_category_is_invalid(self):
        ability = CompanionAbility(
            archetype=self.archetype,
            name="Bad Attack",
            ability_kind=CompanionAbilityKind.ATTACK,
        )
        with self.assertRaises(ValidationError):
            ability.full_clean()

    def test_utility_ability_without_property_is_invalid(self):
        ability = CompanionAbility(
            archetype=self.archetype,
            name="Bad Utility",
            ability_kind=CompanionAbilityKind.UTILITY,
        )
        with self.assertRaises(ValidationError):
            ability.full_clean()

    def test_str_includes_archetype(self):
        ability = CompanionAbility.objects.create(
            archetype=self.archetype,
            name="Rend",
            ability_kind=CompanionAbilityKind.ATTACK,
            attack_category="PHYSICAL",
        )
        self.assertEqual(str(ability), "Rend (Test Beast)")

    def test_unique_ability_per_archetype(self):
        CompanionAbility.objects.create(
            archetype=self.archetype,
            name="Rend",
            ability_kind=CompanionAbilityKind.ATTACK,
            attack_category="PHYSICAL",
        )
        with self.assertRaises(Exception):  # noqa: B017
            CompanionAbility.objects.create(
                archetype=self.archetype,
                name="Rend",
                ability_kind=CompanionAbilityKind.ATTACK,
                attack_category="PHYSICAL",
            )


class CompanionOrderModelTests(TestCase):
    def test_hold_order_creates_with_encounter(self):
        from world.combat.factories import CombatEncounterFactory
        from world.companions.factories import CompanionFactory

        encounter = CombatEncounterFactory()
        companion = CompanionFactory()
        order = CompanionOrder.objects.create(
            companion=companion,
            encounter=encounter,
            round_number=1,
            order_kind=CompanionOrderKind.HOLD,
        )
        self.assertEqual(order.order_kind, CompanionOrderKind.HOLD)
        self.assertEqual(order.encounter, encounter)

    def test_clean_requires_encounter_or_battle(self):
        from world.companions.factories import CompanionFactory

        companion = CompanionFactory()
        order = CompanionOrder(
            companion=companion,
            round_number=1,
            order_kind=CompanionOrderKind.HOLD,
        )
        with self.assertRaises(ValidationError):
            order.full_clean()

    def test_clean_rejects_both_encounter_and_battle(self):
        from world.battles.factories import BattleFactory
        from world.combat.factories import CombatEncounterFactory
        from world.companions.factories import CompanionFactory

        encounter = CombatEncounterFactory()
        battle = BattleFactory()
        companion = CompanionFactory()
        order = CompanionOrder(
            companion=companion,
            encounter=encounter,
            battle=battle,
            round_number=1,
            order_kind=CompanionOrderKind.HOLD,
        )
        with self.assertRaises(ValidationError):
            order.full_clean()
