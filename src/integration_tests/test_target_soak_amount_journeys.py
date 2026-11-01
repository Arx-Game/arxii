"""Journeys for a technique damage modifier that grows with its target's soak (#4892).

The owner's ruling on #4824: the target's soak input works only on technique damage, Charge
included, read against the opponent being hit at the damage step. Hobb holds "Plate-breaker",
"+1 damage per 5 of the target's soak, at most +6". Every check lands at Success with a
damage multiplier of 1, and each technique profile deals exactly its ``base_damage``. The
health an opponent loses is the hit after its soak comes off.

Expected values come from the ruling and the spec, not from running the code:

* A 100-damage strike on a bandit with soak 20: 20 // 5 = 4 steps, +4; it loses
  100 + 4 - 20 = 84. Against soak 80: 16 steps held at the cap, +6; it loses 100 + 6 - 80 = 26.
  Against soak 0: no step; it loses 100.
* One area sweep on a soak 20 bandit and a soak 0 archer: the bandit loses 84, the archer 100.
* A bandit with soak 20 that is vulnerable soaks nothing, so the input reads 0: it loses 100.
* A condition on Hobb carrying the same input adds the same +4 against soak 20: 84.
* Hobb's Charge (5 damage) with a 100-damage technique and the row on Charge damage: against
  soak 20 the bandit loses 100 + 5 + 4 - 20 = 89.
* In a duel, Vex's mirror is hit through her worn armor, soak 10: +2, and she loses
  100 + 2 - 10 = 92. Reading her soak for the row wears no armor; only the hit does.
* Read away from the damage step (the modifier breakdown on its own), the row reads 0.
* Staff cannot give the input to a to-hit target or a check target.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse

from actions.constants import ActionBackend, ActionTargetType
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.test_charge_effect_journeys import DAMAGE
from integration_tests.test_facet_effect_bonus_journeys import _WolfFangField
from integration_tests.test_technique_effect_damage_journeys import _DamageField
from integration_tests.test_vow_added_effects_in_combat_journeys import every_check_succeeds
from world.checks.factories import CheckTypeFactory
from world.combat.duels import create_pvp_duel
from world.combat.factories import CombatOpponentFactory
from world.combat.models import CombatOpponent, CombatParticipant
from world.combat.services import resolve_round
from world.combat.services.damage.soak import target_soak_of
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionModifierEffect
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.models import DistinctionEffect
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.fatigue.constants import EffortLevel
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.magic.models import TechniqueDamageProfile
from world.mechanics.constants import (
    MANEUVER_EFFECT_CATEGORY_NAME,
    AmountInput,
    EffectKind,
    ManeuverEffectKey,
)
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.maneuver_effects import get_maneuver_effect
from world.mechanics.models import ModifierCategory
from world.mechanics.services import get_modifier_breakdown

PER = 5
CAP = 6
STRIKE = 100
# The refusal reads "...the target's soak."; the admin page escapes the apostrophe.
SOAK_REFUSAL_SHOWN = "Only a damage modifier can read the target"


def _soak_menu() -> dict[str, object]:
    return {"amount_input": AmountInput.TARGET_SOAK, "amount_per": PER, "amount_cap": CAP}


def _grant_plate_breaker(sheet, target) -> None:
    """``sheet`` holds "+1 damage per 5 of the target's soak, at most +6" on ``target``."""
    distinction = DistinctionFactory(name="Plate-breaker", slug="plate-breaker")
    DistinctionEffectFactory(
        distinction=distinction, target=target, value_per_rank=1, **_soak_menu()
    )
    grant_distinction(sheet, distinction, origin=DistinctionOrigin.GM_AWARD)


def _technique_damage_target(name: str = "Any damage"):
    category = ModifierCategory.objects.get_or_create(name=MANEUVER_EFFECT_CATEGORY_NAME)[0]
    return ModifierTargetFactory(category=category, name=name, scope_effect_kind=EffectKind.DAMAGE)


def _set_soak(opponent: CombatOpponent, soak: int) -> None:
    opponent.soak_value = soak
    opponent.save(update_fields=["soak_value"])


class APlateBreakerStrikes(_DamageField):
    """Hobb strikes armored and unarmored opponents with the row on technique damage."""

    def setUp(self) -> None:
        super().setUp()
        self.damage = _technique_damage_target()
        self.blow = self.technique(self.ember, (STRIKE, self.fire))

    def test_soak_twenty_adds_four(self) -> None:
        _grant_plate_breaker(self.sheet, self.damage)
        _set_soak(self.bandit, 20)

        self.assertEqual(self.strike(self.blow), STRIKE + 4 - 20)

    def test_soak_eighty_is_held_at_the_cap(self) -> None:
        _grant_plate_breaker(self.sheet, self.damage)
        _set_soak(self.bandit, 80)

        self.assertEqual(self.strike(self.blow), STRIKE + CAP - 80)

    def test_an_unarmored_bandit_gives_nothing(self) -> None:
        _grant_plate_breaker(self.sheet, self.damage)

        self.assertEqual(self.strike(self.blow), STRIKE)

    def test_each_opponent_of_an_area_sweep_gets_its_own_number(self) -> None:
        _grant_plate_breaker(self.sheet, self.damage)
        _set_soak(self.bandit, 20)
        archer = CombatOpponentFactory(
            encounter=self.encounter, name="Archer", health=200, max_health=200, soak_value=0
        )
        sweep = self.technique(self.ember, (STRIKE, self.fire), target_type=ActionTargetType.AREA)

        self.strike(sweep)

        self.assertEqual(200 - self.health_of(self.bandit), STRIKE + 4 - 20)
        self.assertEqual(200 - self.health_of(archer), STRIKE)

    def test_a_vulnerable_bandit_soaks_nothing_so_the_row_adds_nothing(self) -> None:
        _grant_plate_breaker(self.sheet, self.damage)
        _set_soak(self.bandit, 20)
        self.bandit.vulnerability_rounds_remaining = 3
        self.bandit.save(update_fields=["vulnerability_rounds_remaining"])

        self.assertEqual(self.strike(self.blow), STRIKE)

    def test_a_condition_with_the_input_adds_the_same(self) -> None:
        condition = ConditionTemplateFactory(name="Sundering rage")
        ConditionModifierEffect.objects.create(
            condition=condition, modifier_target=self.damage, value=1, **_soak_menu()
        )
        ConditionInstanceFactory(target=self.hobb, condition=condition, rounds_remaining=50)
        _set_soak(self.bandit, 20)

        self.assertEqual(self.strike(self.blow), STRIKE + 4 - 20)

    def test_away_from_the_damage_step_the_row_reads_nothing(self) -> None:
        _grant_plate_breaker(self.sheet, self.damage)

        self.assertEqual(get_modifier_breakdown(self.sheet, self.damage).total, 0)


class APlateBreakerCharges(_WolfFangField):
    """Hobb charges an armored bandit with the row on Charge damage."""

    def test_the_charge_adds_four_against_soak_twenty(self) -> None:
        profile = TechniqueDamageProfile.objects.get(technique=self.technique)
        profile.base_damage = STRIKE
        profile.save(update_fields=["base_damage"])
        _grant_plate_breaker(self.sheet, self.charge_damage)
        _set_soak(self.bandit, 20)

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, STRIKE + DAMAGE + 4 - 20)


class APlateBreakerInADuel(_DamageField):
    """Hobb duels Vex, who wears armor with soak 10; he strikes her mirror."""

    def setUp(self) -> None:
        super().setUp()
        # Hobb leaves the bandit fight for the duel.
        CombatParticipant.objects.get(encounter=self.encounter, character_sheet=self.sheet).delete()
        self.vex = self.make_player("Vex", room=self.yard)
        self.plate = ItemInstanceFactory(
            template=ItemTemplateFactory(
                gear_archetype=GearArchetype.HEAVY_ARMOR,
                base_armor_soak=10,
                max_durability=30,
                name="Vex's plate",
            ),
            durability=30,
        )
        EquippedItemFactory(
            character=self.vex.sheet_data,
            item_instance=self.plate,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.vex.equipped_items.invalidate()
        self.duel = create_pvp_duel(self.sheet, self.vex.sheet_data, self.yard)
        self.mirror = self.duel.opponents.get(
            mirrors_participant__character_sheet=self.vex.sheet_data
        )
        _grant_plate_breaker(self.sheet, _technique_damage_target())
        # A mirror's health comes from her vitals; give it room so one hit does not end the duel.
        self.mirror.health = self.mirror.max_health = 500
        self.mirror.save(update_fields=["health", "max_health"])

    def test_her_mirror_takes_the_row_through_her_armor(self) -> None:
        blow = self.technique(self.ember, (STRIKE, self.fire))
        before = self.health_of(self.mirror)
        ref = ActionRef(backend=ActionBackend.COMBAT, technique_id=blow.pk, action_slot="focused")
        declared = dispatch_player_action(
            self.hobb,
            ref,
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": self.mirror.pk},
        )
        self.assertTrue(declared.deferred, declared)

        with every_check_succeeds():
            resolve_round(self.duel)

        self.assertEqual(before - self.health_of(self.mirror), STRIKE + 2 - 10)

    def test_reading_her_soak_wears_no_armor(self) -> None:
        self.assertEqual(target_soak_of(self.mirror), 10)

        self.assertEqual(ItemInstance.objects.get(pk=self.plate.pk).durability, 30)


class TheSoakInputOnTheEffectAdminPage(_WolfFangField):
    """Staff give the input to Charge damage, and are refused on to-hit and on a check."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        self.distinction = DistinctionFactory(name="Plate-breaker", slug="plate-breaker")

    def save_effect(self, target):
        data = {
            "distinction": self.distinction.pk,
            "target": target.pk,
            "value_per_rank": "1",
            "amplifies_sources_by": "",
            "modifier_size": "",
            "description": "",
            "amount_input": AmountInput.TARGET_SOAK,
            "amount_per": str(PER),
            "amount_cap": str(CAP),
            "amount_check_type": "",
            "amount_thread_trait": "",
            "amount_thread_facet": "",
            "rank_sizes-TOTAL_FORMS": "0",
            "rank_sizes-INITIAL_FORMS": "0",
            "rank_sizes-MIN_NUM_FORMS": "0",
            "rank_sizes-MAX_NUM_FORMS": "1000",
        }
        return self.client.post(reverse("admin:arxii_distinctioneffect_add"), data)

    def test_charge_damage_takes_the_input(self) -> None:
        response = self.save_effect(self.charge_damage)

        self.assertEqual(response.status_code, 302, response.content)
        effect = DistinctionEffect.objects.get(distinction=self.distinction)
        self.assertEqual(
            (effect.amount_input, effect.amount_per, effect.amount_cap),
            (AmountInput.TARGET_SOAK, PER, CAP),
        )

    def test_a_to_hit_target_is_refused(self) -> None:
        to_hit = ModifierTargetFactory(
            category=ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME),
            name="Charge: to hit",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.CHARGE_TO_HIT),
        )

        response = self.save_effect(to_hit)

        self.assertContains(response, SOAK_REFUSAL_SHOWN)
        self.assertFalse(DistinctionEffect.objects.filter(distinction=self.distinction).exists())

    def test_a_check_target_is_refused(self) -> None:
        check_target = ModifierTargetFactory(
            name="Athletics",
            category=ModifierCategoryFactory(name="check"),
            target_check_type=CheckTypeFactory(name="Athletics"),
        )

        response = self.save_effect(check_target)

        self.assertContains(response, SOAK_REFUSAL_SHOWN)
        self.assertFalse(DistinctionEffect.objects.filter(distinction=self.distinction).exists())
