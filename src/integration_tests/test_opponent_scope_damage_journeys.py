"""Journeys for a damage modifier narrowed by who it lands on (#4823).

Hobb is a fighter in the Yard against a bandit and an archer, each with 200 health and no
resistances. Every check in the round is forced to Success (success level 1, damage multiplier
1), and each technique's damage profile has no intensity or extra-level scaling, so a profile
deals exactly its ``base_damage``. Hobb declares a technique through the web client's combat
dispatch, the round resolves, and the health an opponent lost is what the hit dealt. A
"+N damage against X" modifier is a ModifierTarget in the maneuver effect category with the
damage effect kind and an opponent scope, granted to Hobb through a distinction.

Expected values come from the spec, not from running the code:

* "+5 damage against abyssal" lifts an area Fire hit of 6 to 11 on the abyssal archer and
  leaves the bandit at 6.
* An opponent whose abyssal comes from an active condition (the condition template grants the
  property) counts: 6 + 5 = 11. While that condition is suppressed it does not: 6.
* "+2 damage against Bleeding" lifts a hit of 6 to 8 while the bandit has the Bleeding
  condition, and back to 6 once it is gone.
* A player character fought as an opponent (a mirror whose object is the PC's Character) with
  an abyssal tag on the primary persona counts: 6 + 5 = 11.
* The bonus counts once per damage profile, as the technique's other damage modifiers do: a
  Fire profile of 6 and a Cold profile of 4 against an abyssal opponent deal
  (6 + 5) + (4 + 5) = 20.
* With no opponent-scoped target in the game, no opponent's facts are read.
"""

from __future__ import annotations

from unittest.mock import patch

from actions.constants import ActionTargetType
from integration_tests.test_technique_effect_damage_journeys import (
    _DamageField,
    grant_damage_modifier,
)
from world.combat.factories import CombatOpponentFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.mechanics.effect_targets import opponent_facts
from world.mechanics.factories import ObjectPropertyFactory, PropertyFactory


class OpponentScopedDamage(_DamageField):
    """Hobb strikes opponents that carry (or do not carry) what a modifier names."""

    def setUp(self) -> None:
        super().setUp()
        self.abyssal = PropertyFactory(name="Abyssal")
        self.bleeding = ConditionTemplateFactory(name="Bleeding")
        self.archer = CombatOpponentFactory(
            encounter=self.encounter, name="Archer", health=200, max_health=200
        )
        self.sweep = self.technique(self.ember, (6, self.fire), target_type=ActionTargetType.AREA)

    def lost_health(self, opponent) -> int:
        return 200 - self.health_of(opponent)

    def test_vs_abyssal_only_raises_the_abyssal_opponent(self) -> None:
        grant_damage_modifier(self.sheet, "Vs abyssal", 5, scope_opponent_property=self.abyssal)
        ObjectPropertyFactory(object=self.archer.objectdb, property=self.abyssal)

        self.strike(self.sweep)

        self.assertEqual(self.lost_health(self.archer), 6 + 5)
        self.assertEqual(self.lost_health(self.bandit), 6)

    def test_condition_granted_abyssal_counts(self) -> None:
        grant_damage_modifier(self.sheet, "Vs abyssal", 5, scope_opponent_property=self.abyssal)
        marked = ConditionTemplateFactory(name="Marked by the Abyss")
        marked.properties.add(self.abyssal)
        instance = ConditionInstanceFactory(
            target=self.archer.objectdb, condition=marked, rounds_remaining=50
        )

        self.strike(self.sweep)
        self.assertEqual(self.lost_health(self.archer), 6 + 5)
        self.assertEqual(self.lost_health(self.bandit), 6)

        instance.is_suppressed = True
        instance.save(update_fields=["is_suppressed"])
        self.strike(self.sweep)
        self.assertEqual(self.lost_health(self.archer), (6 + 5) + 6)

    def test_vs_bleeding_applies_only_while_bleeding(self) -> None:
        grant_damage_modifier(self.sheet, "Vs bleeding", 2, scope_opponent_condition=self.bleeding)
        blow = self.technique(self.ember, (6, self.fire))
        wound = ConditionInstanceFactory(
            target=self.bandit.objectdb, condition=self.bleeding, rounds_remaining=50
        )

        self.assertEqual(self.strike(blow), 6 + 2)

        wound.delete()
        self.assertEqual(self.strike(blow), 6)

    def test_a_pc_opponent_with_an_abyssal_tag_counts(self) -> None:
        grant_damage_modifier(self.sheet, "Vs abyssal", 5, scope_opponent_property=self.abyssal)
        vex = self.make_player("Vex", room=self.yard)
        vex.sheet_data.primary_persona.properties.add(self.abyssal)
        mirror = CombatOpponentFactory(
            encounter=self.encounter,
            name="Vex",
            persona=vex.sheet_data.primary_persona,
            health=200,
            max_health=200,
        )

        self.strike(self.sweep)

        self.assertEqual(self.lost_health(mirror), 6 + 5)
        self.assertEqual(self.lost_health(self.bandit), 6)

    def test_the_bonus_counts_once_per_profile(self) -> None:
        grant_damage_modifier(self.sheet, "Vs abyssal", 5, scope_opponent_property=self.abyssal)
        ObjectPropertyFactory(object=self.bandit.objectdb, property=self.abyssal)
        twin = self.technique(self.ember, (6, self.fire), (4, self.cold))

        self.assertEqual(self.strike(twin), (6 + 5) + (4 + 5))

    def test_no_opponent_scope_reads_no_opponent_facts(self) -> None:
        grant_damage_modifier(self.sheet, "Any damage", 2)

        with patch(
            "world.combat.services.techniques.technique_resolver.opponent_facts",
            wraps=opponent_facts,
        ) as read:
            self.strike(self.sweep)

        read.assert_not_called()
        self.assertEqual(self.lost_health(self.bandit), 6 + 2)

    def test_an_opponent_scope_reads_each_opponent_once(self) -> None:
        grant_damage_modifier(self.sheet, "Vs abyssal", 5, scope_opponent_property=self.abyssal)
        twin_area = self.technique(
            self.ember, (6, self.fire), (4, self.cold), target_type=ActionTargetType.AREA
        )

        with patch(
            "world.combat.services.techniques.technique_resolver.opponent_facts",
            wraps=opponent_facts,
        ) as read:
            self.strike(twin_area)

        self.assertEqual(read.call_count, 2)
        self.assertEqual(self.lost_health(self.bandit), 6 + 4)
