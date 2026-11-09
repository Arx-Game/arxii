"""Journeys for thrown weapons, enchanted Strikes and armor by damage type (#5026).

Hobb carries a parrying dagger that can also be thrown. In a fight at the Steading the
positions run Lane - Barn - Yard: Hobb stands in the Lane, a bandit archer in the Yard, two
positions away. Every roll is forced to the outcome a test names, in the order the Strike
rolls them: the technique roll (an enchanted Strike only), the hit roll, the damage roll.

Expected values come from the spec and its owner rulings, not from the code:

* The dagger deals 8. A throw deals the catalog's "Strike: thrown damage" share, 75 percent
  to start: 8 x 75 / 100 = 6. It reaches anywhere in the room and rolls Thrown Combat; a
  slash cannot reach two positions. The dagger is still equipped after the throw.
* "Wreathe the blade" is a weapon technique: one Fire profile of 4 that uses the weapon,
  costing 4 anima, with a Moderate Strike to-hit size. The to-hit table here holds 2 for a
  Moderate modifier at level 1, and every cast is level 1. On a Success technique roll it
  adds +2 to hit and a 4-point fire part; the steel stays physical.
* An ordinary opponent's soak (1) stops physical only; its fire weakness (resistance -3)
  makes the fire part 4 + 3 = 7. So a thrown, enchanted Strike on the archer deals
  (6 - 1) physical + 7 fire = 12.
* A failed technique roll still costs the 4 anima; it adds nothing, and the Strike lands as
  a plain throw.
* With 2 anima and a 4-anima enchantment the Strike still goes off: the overspend is a
  deficit of 2 and anima ends at 0, never a refusal.
* Armor stands only against the types it covers: a coat that lists Fire soaks the fire part
  too (4 - 2 = 2 against a 2-soak coat).
* A boss's soak (3) is a wall against every type: the fire part meets it (4 - 3 = 1). Its
  break window drops soak and resistance to zero, as it does today.
* A player in plate (4 soak) hit by an NPC's 10-point fire blow takes all 10; a steel blow
  of 10 takes 6.
"""

from __future__ import annotations

from decimal import Decimal

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.test_combat_style_journeys import STYLE, _give_style, _style
from integration_tests.test_defense_style_journeys import (
    ARMOR,
    HEALTH,
    STRIKE,
    AVowTheStyleDoesNotListChangesOnlyTheArmorBucket,
    RollsInTurn,
    _TheYard,
)
from integration_tests.test_strike_journeys import _StrikeField
from integration_tests.test_technique_effect_damage_journeys import _DamageField
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position
from world.checks.constants import ModifierLane, ModifierSize
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.modifier_models import ModifierValue
from world.combat.constants import OpponentTier, StrikeDelivery, TargetingMode, TargetSelection
from world.combat.factories import (
    CombatOpponentFactory,
    CreatureTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponent, CombatRoundAction
from world.combat.services import resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionResistanceModifierFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.fatigue.constants import EffortLevel
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import EquippedItem
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterAnima
from world.magic.models.modifier_level import CastPowerLevel
from world.traits.factories import CharacterTraitValueFactory, SkillTraitFactory, StatTraitFactory
from world.traits.models import CharacterTraitValue, Trait
from world.vitals.services import get_vitals_consequence_config

DAGGER_DAMAGE = 8
THROWN_DAMAGE = 6  # 8 x 75 percent
FIRE_PART = 4
ENCHANT_COST = 4
ARCHER_SOAK = 1
FIRE_WEAKNESS = 3


class _ThrowingField(_StrikeField):
    """Hobb with a throwable dagger in the Lane; an archer, weak to fire, in the Yard."""

    def setUp(self) -> None:
        super().setUp()
        strength = Trait.objects.get(name="strength")
        thrown_skill = SkillTraitFactory(name="Thrown Combat")
        self.thrown_check = CheckTypeFactory(name="Thrown Attack")
        CheckTypeTraitFactory(check_type=self.thrown_check, trait=strength, weight=1)
        CheckTypeTraitFactory(check_type=self.thrown_check, trait=thrown_skill, weight=1)
        CharacterTraitValueFactory(character=self.sheet, trait=thrown_skill, value=20)
        config = get_vitals_consequence_config()
        self.physical = DamageTypeFactory(name="Physical")
        config.physical_damage_type = self.physical
        config.save(update_fields=["physical_damage_type"])
        self.fire = DamageTypeFactory(name="Fire")

        lane = PositionFactory(room=self.steading, name="Lane")
        barn = PositionFactory(room=self.steading, name="Barn")
        yard = PositionFactory(room=self.steading, name="Yard")
        connect_positions(lane, barn)
        connect_positions(barn, yard)
        place_in_position(self.hobb, lane)
        self.archer = CombatOpponentFactory(
            encounter=self.encounter,
            name="Bandit archer",
            health=200,
            max_health=200,
            soak_value=ARCHER_SOAK,
        )
        place_in_position(self.archer.objectdb, yard)
        weak = ConditionTemplateFactory(name="Tinder-dry")
        ConditionResistanceModifierFactory(
            condition=weak, damage_type=self.fire, modifier_value=-FIRE_WEAKNESS
        )
        ConditionInstanceFactory(condition=weak, target=self.archer.objectdb)

        template = ItemTemplateFactory(
            name="Parrying dagger",
            weapon=True,
            gear_archetype=GearArchetype.MELEE_ONE_HAND,
            base_weapon_damage=DAGGER_DAMAGE,
            max_durability=20,
            can_be_thrown=True,
        )
        self.dagger = ItemInstanceFactory(template=template, durability=20)
        EquippedItem.objects.create(
            character=self.sheet,
            item_instance=self.dagger,
            body_region=BodyRegion.RIGHT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.hobb.equipped_items.invalidate()

    def wreathe_the_blade(self, *, anima: int = 20):
        """Hobb knows the fire weapon technique and holds ``anima``."""
        CharacterAnimaFactory(character=self.sheet, current=anima, maximum=30)
        CastPowerLevel.objects.create(min_power=0, level=1)
        ModifierValue.objects.create(
            lane=ModifierLane.TO_HIT, level=1, size=ModifierSize.MODERATE, value=2
        )
        magic = CheckTypeFactory(name="Fire Magic Cast")
        CheckTypeTraitFactory(check_type=magic, trait=StatTraitFactory(name="Willpower"))
        technique = TechniqueFactory(
            name="Wreathe the blade",
            gift=GiftFactory(name="Ember"),
            anima_cost=ENCHANT_COST,
            intensity=1,
            control=1,
            strike_to_hit_size=ModifierSize.MODERATE,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_template=ActionTemplateFactory(check_type=magic),
        )
        TechniqueDamageProfileFactory(
            technique=technique,
            base_damage=FIRE_PART,
            damage_type=self.fire,
            damage_intensity_multiplier=Decimal(0),
            damage_per_extra_sl=0,
            minimum_success_level=1,
            uses_equipped_weapon=True,
        )
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        return technique

    def throw_at(self, opponent: CombatOpponent, *outcomes: str, **kwargs) -> int:
        """Throw the dagger at ``opponent`` and resolve; the health it lost."""
        result = self.web(
            self.hobb,
            "combat_strike",
            opponent_id=opponent.pk,
            weapon_id=self.dagger.pk,
            thrown=True,
            **kwargs,
        )
        self.assertTrue(result.detail.success, result.detail.message)
        before = CombatOpponent.objects.get(pk=opponent.pk).health
        with self.forced_rolls(*outcomes):
            resolve_round(self.encounter)
        return before - CombatOpponent.objects.get(pk=opponent.pk).health

    def anima(self) -> int:
        return CharacterAnima.objects.get(character=self.sheet).current


class ThrowingTheDagger(_ThrowingField):
    def test_the_dagger_is_offered_to_slash_and_to_throw(self) -> None:
        response = self.api(self.account_of(self.hobb)).get(f"/api/combat/{self.encounter.pk}/")
        own = next(
            p for p in response.json()["participants"] if p["character_sheet_id"] == self.sheet.pk
        )
        dagger_rows = [w for w in own["strike_weapons"] if w["item_instance_id"] == self.dagger.pk]
        self.assertEqual(
            [(w["strike_skill"], w["thrown"], w["damage_share"]) for w in dagger_rows],
            [("Melee Combat", False, None), ("Thrown Combat", True, 75)],
        )

    def test_a_throw_reaches_two_positions_for_its_share_and_stays_in_hand(self) -> None:
        refused = self.web(
            self.hobb, "combat_strike", opponent_id=self.archer.pk, weapon_id=self.dagger.pk
        )
        self.assertFalse(refused.detail.success)
        self.assertIn("out of reach", refused.detail.message)

        lost = self.throw_at(self.archer, "Success", "Success")

        self.assertEqual(lost, THROWN_DAMAGE - ARCHER_SOAK)
        self.assertTrue(
            EquippedItem.objects.filter(character=self.sheet, item_instance=self.dagger).exists()
        )
        hit_row, damage_row = self.shown_rolls()
        self.assertEqual(hit_row["roll_breakdown"]["lines"][0]["label"], "Thrown Combat")
        self.assertIn("thrown", damage_row["roll_breakdown"]["lines"][0]["label"])

    def test_a_weapon_that_cannot_be_thrown_is_refused_a_throw(self) -> None:
        sword = ItemInstanceFactory(
            template=ItemTemplateFactory(
                weapon=True, gear_archetype=GearArchetype.MELEE_ONE_HAND, base_weapon_damage=6
            )
        )
        EquippedItem.objects.create(
            character=self.sheet,
            item_instance=sword,
            body_region=BodyRegion.LEFT_HAND,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.hobb.equipped_items.invalidate()

        result = self.web(
            self.hobb, "combat_strike", opponent_id=self.archer.pk, weapon_id=sword.pk, thrown=True
        )

        self.assertFalse(result.detail.success)
        self.assertIn("not made for throwing", result.detail.message)

    def test_telnet_throws_and_enchants_with_words(self) -> None:
        self.wreathe_the_blade()
        self.connect_telnet(self.hobb)

        said = self.telnet(
            self.hobb, "strike Bandit archer with parrying dagger thrown using wreathe the blade"
        )

        self.assertIn("You ready a throw at Bandit archer", said)
        self.assertIn("enchanted with Wreathe the blade", said)
        action = CombatRoundAction.objects.get(participant__character_sheet=self.sheet)
        self.assertTrue(action.strike_thrown)
        self.assertEqual(action.focused_action.name, "Wreathe the blade")
        with self.forced_rolls("Success", "Success", "Success"):
            resolve_round(self.encounter)
        self.assertTold(self.hobb, "The Parrying dagger is back in your hand.")


class EnchantingTheStrike(_ThrowingField):
    def test_the_fire_part_meets_the_weakness_and_passes_physical_soak(self) -> None:
        technique = self.wreathe_the_blade()

        lost = self.throw_at(
            self.archer, "Success", "Success", "Success", technique_id=technique.pk
        )

        self.assertEqual(lost, (THROWN_DAMAGE - ARCHER_SOAK) + (FIRE_PART + FIRE_WEAKNESS))
        self.assertEqual(self.anima(), 20 - ENCHANT_COST)
        technique_row, hit_row, damage_row = self.shown_rolls()
        self.assertEqual(
            technique_row["roll_breakdown"]["heading"], "Technique roll: Wreathe the blade"
        )
        self.assertIn(
            {
                "label": "Anima",
                "value": str(ENCHANT_COST),
                "detail": "paid for this attack, hit or miss",
                "lapsed": False,
            },
            technique_row["roll_breakdown"]["lines"],
        )
        self.assertEqual(
            technique_row["roll_breakdown"]["result"], "Success: +2 to hit, fire damage"
        )
        self.assertEqual(hit_row["roll_breakdown"]["lines"][0]["label"], "Thrown Combat")
        self.assertIn(
            {
                "label": "Wreathe the blade",
                "value": "+2",
                "detail": "from the technique roll",
                "lapsed": False,
            },
            hit_row["roll_breakdown"]["lines"],
        )
        self.assertEqual(
            damage_row["roll_breakdown"]["result"],
            f"{lost} damage: {THROWN_DAMAGE - ARCHER_SOAK} physical, "
            f"{FIRE_PART + FIRE_WEAKNESS} fire",
        )

    def test_a_failed_technique_roll_still_pays_and_adds_nothing(self) -> None:
        technique = self.wreathe_the_blade()

        lost = self.throw_at(
            self.archer, "Failure", "Success", "Success", technique_id=technique.pk
        )

        self.assertEqual(lost, THROWN_DAMAGE - ARCHER_SOAK)
        self.assertEqual(self.anima(), 20 - ENCHANT_COST)
        self.assertEqual(
            self.shown_rolls()[0]["roll_breakdown"]["result"], "Failure: nothing added"
        )

    def test_a_missed_enchanted_strike_still_pays(self) -> None:
        technique = self.wreathe_the_blade()

        lost = self.throw_at(self.archer, "Success", "Failure", technique_id=technique.pk)

        self.assertEqual(lost, 0)
        self.assertEqual(self.anima(), 20 - ENCHANT_COST)

    def test_too_little_anima_overspends_instead_of_refusing(self) -> None:
        technique = self.wreathe_the_blade(anima=2)

        lost = self.throw_at(
            self.archer,
            "Success",
            "Success",
            "Success",
            technique_id=technique.pk,
            confirm_soulfray_risk=True,
        )

        self.assertEqual(lost, (THROWN_DAMAGE - ARCHER_SOAK) + (FIRE_PART + FIRE_WEAKNESS))
        self.assertEqual(self.anima(), 0)


class AKnifeStyleCountsOnAThrow(_ThrowingField):
    """A style that lists one-handed melee fits the dagger thrown too (owner ruling)."""

    def test_the_style_skill_counts_on_the_throw(self) -> None:
        style = _style(GearArchetype.MELEE_ONE_HAND)
        CharacterTraitValue.objects.create(character=self.sheet, trait=style.skill, value=20)
        _give_style(self.sheet, style)

        self.throw_at(self.archer, "Success", "Success")

        hit_row = self.shown_rolls()[0]
        self.assertIn(
            {"label": STYLE, "value": "20", "detail": "style skill", "lapsed": False},
            hit_row["roll_breakdown"]["lines"],
        )


class FireOnNPCsBeyondTheStrike(_DamageField):
    """A player's fire technique (6, not a weapon technique) through the round: an ordinary
    bandit's soak (2) stops physical only; a boss's soak is a wall against every type, until
    its break window opens."""

    def setUp(self) -> None:
        super().setUp()
        self.designate_physical()
        self.bolt = self.technique(self.ember, (6, self.fire))

    def test_fire_passes_an_ordinary_soak(self) -> None:
        self.bandit.soak_value = 2
        self.bandit.save(update_fields=["soak_value"])

        self.assertEqual(self.strike(self.bolt), 6)

    def test_fire_meets_a_boss_wall_until_it_breaks(self) -> None:
        self.bandit.tier = OpponentTier.BOSS
        self.bandit.soak_value = 2
        self.bandit.save(update_fields=["tier", "soak_value"])

        self.assertEqual(self.strike(self.bolt), 6 - 2)

        self.bandit.vulnerability_rounds_remaining = 2
        self.bandit.save(update_fields=["vulnerability_rounds_remaining"])
        self.assertEqual(self.strike(self.bolt), 6)


class AWeaponTechniqueIsCastOnlyIntoAStrike(_DamageField):
    """Declared on its own in the focused slot, a weapon technique is refused (#5026)."""

    def test_the_focused_slot_refuses_it(self) -> None:
        technique = self.technique(self.ember, (4, self.fire))
        profile = technique.damage_profiles.get()
        profile.uses_equipped_weapon = True
        profile.save(update_fields=["uses_equipped_weapon"])
        technique.__dict__.pop("cached_damage_profiles", None)
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=technique.pk, action_slot="focused"
        )

        with self.assertRaises(ActionDispatchError) as raised:
            dispatch_player_action(
                self.hobb,
                ref,
                {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": self.bandit.pk},
            )

        self.assertEqual(raised.exception.code, ActionDispatchError.CAST_INTO_STRIKE)
        self.assertFalse(CombatRoundAction.objects.filter(participant__encounter=self.encounter))


class ArmorByDamageType(_ThrowingField):
    """The armor rule on hits that are not a Strike: a player's fire technique on NPCs, and an
    NPC's fire blow on a player in plate."""

    def test_a_boss_wall_meets_fire_like_steel_until_its_window_opens(self) -> None:
        technique = self.wreathe_the_blade()
        boss = CombatOpponentFactory(
            encounter=self.encounter,
            name="Warden",
            tier=OpponentTier.BOSS,
            health=200,
            max_health=200,
            soak_value=3,
        )
        place_in_position(boss.objectdb, self.archer_position())

        lost = self.throw_at(boss, "Success", "Success", "Success", technique_id=technique.pk)

        # Steel 6 - 3, fire 4 - 3: the wall stands against both.
        self.assertEqual(lost, (THROWN_DAMAGE - 3) + (FIRE_PART - 3))

    def archer_position(self):
        from world.areas.positioning.services import position_of

        return position_of(self.archer.objectdb)


class ArmorOnAPlayer(_TheYard):
    """Mira in a 4-soak jerkin, struck by an NPC's blow of 10 through a real round; her
    defence roll is held at a plain failure, so the whole blow arrives."""

    def setUp(self) -> None:
        super().setUp()
        config = get_vitals_consequence_config()
        self.physical = DamageTypeFactory(name="Physical")
        config.physical_damage_type = self.physical
        config.save(update_fields=["physical_damage_type"])
        self.fire = DamageTypeFactory(name="Fire")

    def npc_blow(self, damage_type) -> None:
        pool = ThreatPoolFactory(name=f"{damage_type.name} attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name=f"{damage_type.name} bolt",
            base_damage=STRIKE,
            damage_type=damage_type,
            delivery=StrikeDelivery.MELEE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            defense_check_type=self.defense,
        )
        template = CreatureTemplateFactory(
            name=f"{damage_type.name} caster",
            tier=OpponentTier.MOOK,
            threat_pool=pool,
            speed_hops=0,
        )
        spawn_from_creature_template(self.encounter, template)

    def jerkin_of(self, character):
        return EquippedItem.objects.get(character=character.sheet_data).item_instance.template

    def test_steel_meets_the_armor(self) -> None:
        mira = self.fighter("Mira")
        self.npc_blow(self.physical)

        self.resolve(RollsInTurn({"Mira": [0]}))

        self.assertEqual(self.health(mira), HEALTH - (STRIKE - ARMOR))

    def test_fire_passes_armor_that_covers_physical_only(self) -> None:
        mira = self.fighter("Mira")
        self.npc_blow(self.fire)

        self.resolve(RollsInTurn({"Mira": [0]}))

        self.assertEqual(self.health(mira), HEALTH - STRIKE)

    def test_armor_that_lists_fire_soaks_fire(self) -> None:
        mira = self.fighter("Mira")
        self.jerkin_of(mira).also_protects_against.add(self.fire)
        self.npc_blow(self.fire)

        self.resolve(RollsInTurn({"Mira": [0]}))

        self.assertEqual(self.health(mira), HEALTH - (STRIKE - ARMOR))


class CovenantProtectionStandsAgainstFire(AVowTheStyleDoesNotListChangesOnlyTheArmorBucket):
    """A vow's resonant soak (1) is covenant protection: it stands against every type."""

    def setUp(self) -> None:
        super().setUp()
        config = get_vitals_consequence_config()
        config.physical_damage_type = DamageTypeFactory(name="Physical")
        config.save(update_fields=["physical_damage_type"])
        self.fire = DamageTypeFactory(name="Fire")

    def test_the_vow_soaks_a_fire_blow_the_jerkin_lets_through(self) -> None:
        vik = self.holder("Vik", self.unlisted_vow)
        pool = ThreatPoolFactory(name="Fire attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name="Fire bolt",
            base_damage=STRIKE,
            damage_type=self.fire,
            delivery=StrikeDelivery.MELEE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            defense_check_type=self.defense,
        )
        spawn_from_creature_template(
            self.encounter,
            CreatureTemplateFactory(
                name="Fire caster", tier=OpponentTier.MOOK, threat_pool=pool, speed_hops=0
            ),
        )

        self.resolve(RollsInTurn({"Vik": [0]}))

        # The jerkin covers physical only; the vow's 1 resonant soak covers every type.
        self.assertEqual(self.health(vik), HEALTH - (STRIKE - self.RESONANT))

    # The parent's tests rerun here unchanged; they are its own, not this rule's.
    test_a_listed_vow_makes_the_armor_stack_with_the_resonant_soak = None  # type: ignore[assignment]
    test_an_unlisted_vow_leaves_the_armor_competing_with_the_resonant_soak = None  # type: ignore[assignment]
