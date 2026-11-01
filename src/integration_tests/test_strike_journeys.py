"""Journeys for the basic Strike (#4858, slice 1 of #4844).

Hobb has no techniques. In a fight at the Steading he Strikes a bandit through the web
dispatch (``combat_strike``) and through telnet, with his equipped sword or his bare hands.
The round resolves with each roll forced to the outcome a test names; what is read back is
the bandit's lost health, the two roll records the turn panel shows (hit roll, then damage
roll) through the consequence-outcomes REST endpoint, and Hobb's engagement intensity.

Expected values come from the spec and the catalog defaults, not from the code: a landed
Strike deals the weapon's damage times the damage multiplier for the damage roll (Success
is x1 here), never below the Strike's base damage of 3; bare hands deal 2; a vow scaling
"Strike: base damage" by +1 a level at thread level 3 adds 3; a miss adds 1 intensity, and
each point of intensity adds 1 to the next hit roll. The sword is a one-handed blade, so
the hit roll is Melee Combat with Agility; bare hands are Unarmed Combat with the check's
own stat, Strength.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatOpponent, CombatRoundAction
from world.combat.services import begin_declaration_phase, resolve_round
from world.combat.tests.test_mounted_combat import _equip_weapon
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory, CovenantRoleFactory, engage_vow_with_thread
from world.covenants.models import VowStatScaling
from world.items.constants import GearArchetype
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, ManeuverEffectKey
from world.mechanics.engagement import CharacterEngagement
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierCategory
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

if TYPE_CHECKING:
    from collections.abc import Iterator

SWORD_DAMAGE = 6
BASE_DAMAGE = 3
BARE_HANDS_DAMAGE = 2


class _StrikeField(JourneyCase):
    """Hobb, unskilled in magic, facing a bandit at the Steading."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        ensure_maneuver_effects()
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("2.00"), label="Double"
        )
        strength = StatTraitFactory(name="strength")
        StatTraitFactory(name="agility")
        self.melee = CheckTypeFactory(name="Melee Combat")
        CheckTypeTraitFactory(check_type=self.melee, trait=strength, weight=1)
        self.unarmed = CheckTypeFactory(name="Unarmed Combat")
        CheckTypeTraitFactory(check_type=self.unarmed, trait=strength, weight=1)

        self.steading = self.make_room("The Steading")
        self.hobb = self.make_player("Hobb", room=self.steading)
        self.sheet = self.hobb.sheet_data
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=100, max_health=100, base_max_health=100
        )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.BETWEEN_ROUNDS, round_number=0, room=self.steading
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        self.bandit = CombatOpponentFactory(
            encounter=self.encounter, name="Bandit", health=200, max_health=200
        )
        # Opening the round gives Hobb his combat engagement, as a real fight does.
        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()

    def equip_sword(self):
        return _equip_weapon(self.hobb, archetype=GearArchetype.MELEE_ONE_HAND, damage=SWORD_DAMAGE)

    @contextmanager
    def forced_rolls(self, *outcome_names: str) -> Iterator[list[dict[str, Any]]]:
        """Each strike roll lands at the next named outcome; the list gets each roll's
        check type and the modifiers it was rolled with (hit roll, then damage roll)."""
        outcomes = [CheckOutcome.objects.get(name=name) for name in outcome_names]
        rolled: list[dict[str, Any]] = []

        def forced(character, check_type, *args, **kwargs):
            rolled.append({"check_type": check_type, **kwargs})
            outcome = outcomes[min(len(rolled), len(outcomes)) - 1]
            with force_check_outcome(outcome):
                return perform_check(character, check_type, *args, **kwargs)

        with patch("world.combat.services.perform_check", side_effect=forced):
            yield rolled

    def strike(self, **kwargs: Any):
        return self.web(self.hobb, "combat_strike", opponent_id=self.bandit.pk, **kwargs)

    def strike_and_resolve(self, *outcome_names: str, **kwargs: Any) -> tuple[int, list[dict]]:
        """Declare the Strike, resolve the round; return (damage dealt, the rolls)."""
        result = self.strike(**kwargs)
        self.assertTrue(result.detail.success, result.detail.message)
        before = CombatOpponent.objects.get(pk=self.bandit.pk).health
        with self.forced_rolls(*outcome_names) as rolled:
            resolve_round(self.encounter)
        after = CombatOpponent.objects.get(pk=self.bandit.pk).health
        return before - after, rolled

    def shown_rolls(self) -> list[dict[str, Any]]:
        """The roll records the turn panel reads for Hobb in this fight, oldest first."""
        response = self.api(self.account_of(self.hobb)).get(
            "/api/checks/consequence-outcomes/",
            {"character": self.sheet.pk, "encounter": self.encounter.pk},
        )
        self.assertEqual(response.status_code, 200, response.content)
        return list(reversed(response.json()["results"]))

    def intensity(self) -> int:
        return CharacterEngagement.objects.get(character=self.sheet).intensity_modifier


class StrikeWithAWeapon(_StrikeField):
    def test_a_landed_strike_rolls_to_hit_then_for_damage(self) -> None:
        sword = self.equip_sword()

        damage, rolled = self.strike_and_resolve("Success", "Success", weapon_id=sword.pk)

        self.assertEqual(damage, SWORD_DAMAGE)
        self.assertEqual([roll["check_type"] for roll in rolled], [self.melee, self.melee])
        # The hit roll is opposed by the bandit; the damage roll is not.
        self.assertEqual(rolled[1]["target_difficulty"], 0)
        self.assertEqual(rolled[0]["stat_override"], "agility")
        summaries = [row["summary"] for row in self.shown_rolls()]
        self.assertEqual(len(summaries), 2)
        self.assertIn("Hit roll against Bandit: Melee Combat with Agility. Success.", summaries[0])
        self.assertIn("Damage roll:", summaries[1])
        self.assertIn(f"{SWORD_DAMAGE} damage.", summaries[1])

    def test_a_poor_damage_roll_still_deals_the_base_damage(self) -> None:
        sword = self.equip_sword()

        damage, _rolled = self.strike_and_resolve("Success", "Failure", weapon_id=sword.pk)

        self.assertEqual(damage, BASE_DAMAGE)

    def test_a_great_damage_roll_multiplies_the_weapon(self) -> None:
        sword = self.equip_sword()

        damage, _rolled = self.strike_and_resolve("Success", "Critical Success", weapon_id=sword.pk)

        self.assertEqual(damage, 2 * SWORD_DAMAGE)

    def test_the_room_reads_the_strike(self) -> None:
        sword = self.equip_sword()
        self.watch(self.hobb)

        self.strike_and_resolve("Success", "Success", weapon_id=sword.pk)

        self.assertShownRow(self.hobb, "strikes Bandit with a")

    def test_the_turn_panel_offers_each_equipped_weapon_and_bare_hands(self) -> None:
        sword = self.equip_sword()

        response = self.api(self.account_of(self.hobb)).get(f"/api/combat/{self.encounter.pk}/")

        self.assertEqual(response.status_code, 200, response.content)
        own = next(
            p for p in response.json()["participants"] if p["character_sheet_id"] == self.sheet.pk
        )
        self.assertEqual(
            own["strike_weapons"],
            [
                {
                    "item_instance_id": sword.pk,
                    "name": sword.display_name,
                    "gear_kind": "One-Handed Melee",
                    "strike_skill": "Melee Combat",
                },
                {
                    "item_instance_id": None,
                    "name": "bare hands",
                    "gear_kind": "Unarmed",
                    "strike_skill": "Unarmed Combat",
                },
            ],
        )

    def test_a_weapon_not_equipped_is_refused(self) -> None:
        result = self.strike(weapon_id=999_999)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "You have no such weapon equipped.")
        self.assertFalse(CombatRoundAction.objects.filter(participant__encounter=self.encounter))

    def test_a_vow_on_strike_base_damage_adds_to_every_landed_strike(self) -> None:
        sword = self.equip_sword()
        category = ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME)
        target = ModifierTargetFactory(
            category=category,
            name="Strike damage vow",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.STRIKE_BASE_DAMAGE),
        )
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        engage_vow_with_thread(
            self.sheet,
            role,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=3,
        )
        VowStatScaling.objects.create(covenant_role=role, modifier_target=target, bonus_per_level=1)

        damage, _rolled = self.strike_and_resolve("Success", "Success", weapon_id=sword.pk)

        self.assertEqual(damage, SWORD_DAMAGE + 3)


class StrikeBareHanded(_StrikeField):
    def test_bare_hands_hit_for_the_bare_hands_damage(self) -> None:
        damage, rolled = self.strike_and_resolve("Success", "Success")

        self.assertEqual(damage, BARE_HANDS_DAMAGE)
        self.assertEqual(rolled[0]["check_type"], self.unarmed)
        summaries = [row["summary"] for row in self.shown_rolls()]
        self.assertIn("Unarmed Combat with Strength", summaries[0])
        self.assertIn(f"bare hands {BARE_HANDS_DAMAGE}", summaries[1])

    def test_a_strike_with_no_strike_skill_set_up_is_refused(self) -> None:
        self.unarmed.delete()

        result = self.strike()

        self.assertFalse(result.detail.success)
        self.assertEqual(
            result.detail.message,
            "Cannot strike with bare hands: Unarmed Combat is not set up yet.",
        )


class MissesBuildIntensity(_StrikeField):
    def test_a_miss_raises_intensity_and_it_adds_to_the_next_hit_roll(self) -> None:
        sword = self.equip_sword()
        self.assertEqual(self.intensity(), 0)

        damage, rolled = self.strike_and_resolve("Failure", weapon_id=sword.pk)

        self.assertEqual(damage, 0)
        self.assertEqual(len(rolled), 1)  # no damage roll after a miss
        self.assertEqual(self.intensity(), 1)
        missed_with = rolled[0]["extra_modifiers"]

        begin_declaration_phase(self.encounter)
        self.encounter.refresh_from_db()
        _damage, rolled = self.strike_and_resolve("Success", "Success", weapon_id=sword.pk)

        self.assertEqual(rolled[0]["extra_modifiers"], missed_with + 1)
        latest_hit = self.shown_rolls()[-2]
        self.assertIn(
            {"source_kind": "character", "source_label": "Intensity", "value": 1},
            latest_hit["modifiers"],
        )


class StrikeThroughTelnet(_StrikeField):
    def test_strike_with_a_named_weapon(self) -> None:
        sword = self.equip_sword()

        told = self.telnet(self.hobb, f"strike bandit with {sword.display_name}")

        self.assertIn(f"You ready a strike at Bandit with {sword.display_name}.", told)
        before = CombatOpponent.objects.get(pk=self.bandit.pk).health
        with self.forced_rolls("Success", "Success"):
            resolve_round(self.encounter)
        self.assertEqual(before - CombatOpponent.objects.get(pk=self.bandit.pk).health, 6)
        self.assertIn("Melee Combat with Agility", self.shown_rolls()[0]["summary"])

    def test_combat_strike_with_no_weapon_is_bare_handed(self) -> None:
        told = self.telnet(self.hobb, "combat strike bandit")

        self.assertIn("You ready a strike at Bandit with your bare hands.", told)
        before = CombatOpponent.objects.get(pk=self.bandit.pk).health
        with self.forced_rolls("Success", "Success"):
            resolve_round(self.encounter)
        self.assertEqual(
            before - CombatOpponent.objects.get(pk=self.bandit.pk).health, BARE_HANDS_DAMAGE
        )

    def test_a_weapon_you_do_not_carry_is_refused(self) -> None:
        told = self.telnet(self.hobb, "strike bandit with halberd")

        self.assertIn("You have no such weapon equipped.", told)
