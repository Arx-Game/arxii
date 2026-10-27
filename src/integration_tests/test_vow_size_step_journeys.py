"""Journeys for a vowed caster's size step on her buffs and debuffs (#4747).

Slice 9 of #4551. Selene (level 6) holds a Sword vow whose role carries a technique
specialty for Defense Buff. When she casts a sized buff whose technique carries that
function, the buff counts one size step stronger, valued at her vow thread's shown
level, and that extra part is never tapered. Points only: no outcome floor or ceiling.

Every cast goes the way the web client sends it (``cast_technique`` through dispatch),
or, for the fight, a declared combat action resolved by ``resolve_round``. The rows are
the example seed (``world.seeds.modifier_values``), so every expected number below is
worked by hand from it:

* check and stat lane values: Large = 3 at level 1, 10 at level 6, 16 at level 11;
  Exceptional = 1.5 x Large, rounded half to even: 4 at level 1 (4.5), 15 at level 6,
  24 at level 11. A level reads the row at the highest seeded level at or below it, so
  level 4 reads level 1's row.
* the step at thread level 6 is 15 - 10 = 5; at thread level 4 it is 4 - 3 = 1.
* the taper: the k-th largest of a pile counts (7/8)^(k-1), never below 2/3.
* cast power to level: 0-7 is level 1, 16-29 level 6, 30-44 level 11; a Success
  shifts nothing.

Selene's vow role has no blend weight on Crown (the techniques' axis) and her
specialty's power multiplier is 0, so the vow adds nothing to her cast's power and her
buff lands at the level her intensity alone gives. That isolates the size step from
the specialty's power bonus (#2443), which is covered elsewhere.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from evennia.objects.models import ObjectDB

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.checks.constants import ModifierSize
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import (
    collect_check_modifiers,
    level_opposition,
    perform_check,
    perform_check_with_modifiers,
)
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.combat.constants import ActionCategory, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import resolve_round
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
    DamageSuccessLevelMultiplierFactory,
)
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CovenantFactory,
    CovenantRoleFactory,
    CovenantRoleTechniqueSpecialtyFactory,
    engage_vow_with_thread,
)
from world.fatigue.constants import EffortLevel
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.magic.models import Technique
from world.magic.models.modifier_level import CastPowerLevel
from world.magic.models.techniques import ConditionTargetKind
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.modifier_values import seed_modifier_value_tables
from world.traits.constants import PrimaryStat
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

# What each buff condition authors flat; a sized buff never adds this.
FLAT_AUTHORED = 5


def _vow_role() -> object:
    """A Sword vow: no Crown weight, so it adds no blend power to a Crown technique."""
    return CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1, crown_weight=0)


class AVowedCastersBuffsStep(JourneyCase):
    """Selene buffs Vesper's Ward Reading beside three buffs from Aldric (level 11)."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_modifier_value_tables()
        self.room = self.make_room("The Lantern Gallery")
        SceneFactory(room=self.room)
        self.ward_reading = CheckTypeFactory(name="Ward Reading")
        self.stat = StatTraitFactory()
        CheckTypeTraitFactory(check_type=self.ward_reading, trait=self.stat, weight=1)
        self.strength = StatTraitFactory(name=PrimaryStat.STRENGTH.value)
        self.strength_target = ModifierTargetFactory(
            name="strength",
            category=ModifierCategoryFactory(name="stat"),
            target_trait=self.strength,
        )
        self.casting = ActionTemplateFactory(check_type=CheckTypeFactory(name="Casting"))
        self.character_class = CharacterClassFactory()
        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)

        self.selene = self.player("Selene", level=6)
        self.aldric = self.player("Aldric", level=11)
        self.vesper = self.player("Vesper", level=6)

        # Selene's buff: intensity 20 lands at level 6.
        self.warding_word = self.buff_technique("Warding Word", intensity=20)
        # A weak casting of the same kind: intensity 5 lands at level 1.
        self.faint_ward = self.buff_technique("Faint Ward", intensity=5)
        # Aldric's three buffs: intensity 30 lands at level 11.
        self.aldric_buffs = [
            self.buff_technique(f"Lantern Sight {index + 1}", intensity=30) for index in range(3)
        ]
        for technique in (self.warding_word, self.faint_ward):
            grant_technique(self.selene.sheet_data.primary_persona, technique)
        for technique in self.aldric_buffs:
            grant_technique(self.aldric.sheet_data.primary_persona, technique)

    # -- setup helpers ----------------------------------------------------------

    def player(self, name: str, *, level: int) -> ObjectDB:
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterClassLevelFactory(
            character=sheet, character_class=self.character_class, level=level, is_primary=True
        )
        sheet.invalidate_class_level_cache()
        CharacterAnimaFactory(character=sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        character.traits.set_trait_value(self.stat.name, 20)
        character.traits.set_trait_value(self.strength.name, 20)
        return character

    def technique(self, name: str, *, intensity: int, condition: ConditionTemplate) -> Technique:
        """A Defense Buff technique whose whole effect is one Large ally buff."""
        technique = TechniqueFactory(
            name=name,
            gift=GiftFactory(),
            intensity=intensity,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=self.casting,
        )
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.DEFENSE_BUFF)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
            modifier_size=ModifierSize.LARGE,
        )
        return technique

    def buff_technique(self, name: str, *, intensity: int) -> Technique:
        condition = ConditionTemplateFactory(name=name)
        ConditionCheckModifierFactory(
            condition=condition, check_type=self.ward_reading, modifier_value=FLAT_AUTHORED
        )
        return self.technique(name, intensity=intensity, condition=condition)

    def swear(self, *, thread_level: int, function: str = TechniqueFunction.DEFENSE_BUFF) -> None:
        """Selene engages her vow, whose role specializes in ``function``."""
        role = _vow_role()
        # Multiplier 0: the specialty names the function and adds no cast power.
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=function, multiplier_tenths=0
        )
        engage_vow_with_thread(
            self.selene.sheet_data, role, covenant=self.covenant, thread_level=thread_level
        )

    def cast(self, caster: ObjectDB, target: ObjectDB, technique: Technique) -> None:
        with force_check_outcome(CheckOutcome.objects.get(name="Success")):
            result = self.web(
                caster,
                "cast_technique",
                technique_id=technique.pk,
                target_persona_id=target.sheet_data.primary_persona.pk,
            )
        self.assertTrue(result.detail.success, result.detail.message)

    def landed(self, technique: Technique) -> ConditionInstance:
        return ConditionInstance.objects.get(
            target=self.vesper, condition=technique.condition_applications.get().condition
        )

    def ward_check(self) -> CheckResult:
        return perform_check_with_modifiers(self.vesper, self.ward_reading, target_difficulty=50)

    def buff_vesper_beside_aldric(self) -> int:
        """Aldric's three buffs, then Selene's; returns the check's gain."""
        before = self.ward_check().total_points
        for technique in self.aldric_buffs:
            self.cast(self.aldric, self.vesper, technique)
        self.cast(self.selene, self.vesper, self.warding_word)
        for technique in self.aldric_buffs:
            self.assertEqual(self.landed(technique).modifier_level, 11)
        self.assertEqual(self.landed(self.warding_word).modifier_level, 6)
        return self.ward_check().total_points - before

    # -- journeys -----------------------------------------------------------------

    def test_her_step_at_thread_six_counts_whole_beside_a_tapered_pile(self) -> None:
        self.swear(thread_level=6)

        gain = self.buff_vesper_beside_aldric()

        selene = self.landed(self.warding_word)
        self.assertEqual(selene.modifier_vow_level, 6)
        # The pile: Aldric's three Large at level 11 (16 each) and Selene's Large at
        # level 6 (10), tapered together: 16 + 16 x 7/8 + 16 x (7/8)^2 + 10 x (7/8)^3
        # = 16 + 14 + 12.25 + 6.69921875 = 48.94921875. Her step, Exceptional minus
        # Large at level 6 = 15 - 10 = 5, counts whole: 53.94921875, which rounds to 54.
        # Tapered as part of a 15 it would be 42.25 + 15 x (7/8)^3 = 52.30, so 52.
        self.assertEqual(gain, 54)
        breakdown = collect_check_modifiers(self.vesper.sheet_data, self.ward_reading)
        (contribution,) = [c for c in breakdown.contributions if c.vow_part]
        self.assertEqual((contribution.value, contribution.vow_part), (15, 5))

    def test_at_thread_four_the_step_is_smaller(self) -> None:
        self.swear(thread_level=4)

        gain = self.buff_vesper_beside_aldric()

        self.assertEqual(self.landed(self.warding_word).modifier_vow_level, 4)
        # Level 4 reads level 1's row: Exceptional 4 minus Large 3 = 1.
        # 48.94921875 + 1 = 49.94921875, which rounds to 50.
        self.assertEqual(gain, 50)

    def test_a_vow_without_the_functions_specialty_adds_nothing(self) -> None:
        self.swear(thread_level=6, function=TechniqueFunction.STRIKE)

        gain = self.buff_vesper_beside_aldric()

        self.assertIsNone(self.landed(self.warding_word).modifier_vow_level)
        # The tapered pile alone: 48.94921875, which rounds to 49.
        self.assertEqual(gain, 49)

    def test_a_weak_cast_from_a_deep_vow_still_steps_at_the_vows_level(self) -> None:
        self.swear(thread_level=6)
        before = self.ward_check().total_points

        self.cast(self.selene, self.vesper, self.faint_ward)

        faint = self.landed(self.faint_ward)
        # Intensity 5 sits in the 0-7 power row: level 1. The step is valued at her
        # thread's level 6, never at the buff's own level 1.
        self.assertEqual((faint.modifier_level, faint.modifier_vow_level), (1, 6))
        # Large at level 1 = 3, plus the level-6 step 15 - 10 = 5: 8.
        # (Capped at the buff's level the step would be 4 - 3 = 1, for 4.)
        self.assertEqual(self.ward_check().total_points - before, 8)

    def test_recasting_without_the_vow_keeps_the_step(self) -> None:
        self.swear(thread_level=6)
        self.cast(self.selene, self.vesper, self.warding_word)
        grant_technique(self.aldric.sheet_data.primary_persona, self.warding_word)

        self.cast(self.aldric, self.vesper, self.warding_word)

        # Aldric has no vow; the re-application keeps the higher step level, as it
        # keeps the higher modifier level (his intensity-20 cast is level 6 too).
        self.assertEqual(self.landed(self.warding_word).modifier_vow_level, 6)

    def test_a_stat_buff_steps_in_the_stat_lane(self) -> None:
        self.swear(thread_level=6)
        condition = ConditionTemplateFactory(name="Iron Grip")
        ConditionModifierEffectFactory(
            condition=condition, modifier_target=self.strength_target, value=FLAT_AUTHORED
        )
        iron_grip = self.technique("Iron Grip", intensity=20, condition=condition)
        grant_technique(self.selene.sheet_data.primary_persona, iron_grip)
        before = self.vesper.traits.get_trait_value(self.strength.name)

        self.cast(self.selene, self.vesper, iron_grip)

        instance = ConditionInstance.objects.get(target=self.vesper, condition=condition)
        self.assertEqual((instance.modifier_level, instance.modifier_vow_level), (6, 6))
        # The stat lane's seed equals the check lane's: Large at level 6 = 10, and the
        # step 15 - 10 = 5, so strength gains 15 stored units.
        self.assertEqual(self.vesper.traits.get_trait_value(self.strength.name) - before, 15)


@contextmanager
def _every_check_succeeds() -> Iterator[None]:
    """Every combat check in the block lands at Success."""
    outcome = CheckOutcome.objects.get(name="Success")

    def forced(*args: object, **kwargs: object) -> CheckResult:
        with force_check_outcome(outcome):
            return perform_check(*args, **kwargs)

    with patch("world.combat.services.perform_check", side_effect=forced):
        yield


class AHexersDebuffStepsOnAnOpponent(JourneyCase):
    """Selene hexes an NPC opponent in a fight; the opponent's difficulty drops further."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        DamageSuccessLevelMultiplierFactory(min_success_level=1, multiplier=1)
        seed_modifier_value_tables()
        # One power row: every cast in this fight lands at level 6, whatever its power.
        CastPowerLevel.objects.all().delete()
        CastPowerLevel.objects.create(min_power=0, level=6)
        self.yard = self.make_room("The Yard")
        self.check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=self.check_type, trait=StatTraitFactory(), weight=1)
        self.hex = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=self.check_type),
        )
        TechniqueFunctionTagFactory(technique=self.hex, function=TechniqueFunction.WEAKEN)
        self.sapped = ConditionTemplateFactory(name="Sapped")
        ConditionCheckModifierFactory(
            condition=self.sapped, check_type=self.check_type, modifier_value=-FLAT_AUTHORED
        )
        TechniqueAppliedConditionFactory(
            technique=self.hex,
            condition=self.sapped,
            target_kind=ConditionTargetKind.ENEMY,
            minimum_success_level=1,
            modifier_size=ModifierSize.LARGE,
        )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.yard
        )
        self.selene = self.make_player("Selene", room=self.yard)
        sheet = self.selene.sheet_data
        CharacterTechniqueFactory(character=sheet, technique=self.hex)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter)

    def hex_the_opponent(self, *, specialty: str) -> int:
        """Selene's vow (thread 6) specializes in ``specialty``; returns the difficulty drop."""
        role = _vow_role()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=specialty, multiplier_tenths=0
        )
        engage_vow_with_thread(
            self.selene.sheet_data,
            role,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
            thread_level=6,
        )
        before = self.difficulty()
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=self.hex.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            self.selene,
            ref,
            {"effort_level": EffortLevel.MEDIUM, "focused_opponent_target_id": self.opponent.pk},
        )
        self.assertTrue(declared.deferred, declared)
        with _every_check_succeeds():
            resolve_round(self.encounter)
        instance = ConditionInstance.objects.get(
            target=self.opponent.objectdb, condition=self.sapped
        )
        self.assertEqual(instance.modifier_level, 6)
        # A second, heavier penalty from elsewhere, so the pile tapers.
        bruised = ConditionTemplateFactory(name="Bruised")
        ConditionCheckModifierFactory(
            condition=bruised, check_type=self.check_type, modifier_value=-20
        )
        ConditionInstanceFactory(target=self.opponent.objectdb, condition=bruised)
        return before - self.difficulty()

    def difficulty(self) -> int:
        return level_opposition(
            self.check_type, level=self.opponent.level, character=self.opponent.objectdb
        )

    def test_the_hex_steps_the_penalty_untapered(self) -> None:
        drop = self.hex_the_opponent(specialty=TechniqueFunction.WEAKEN)

        # The penalty pile: Bruised -20 leads, Sapped's Large at level 6 (-10) counts
        # 7/8: -20 - 8.75 = -28.75. The step, -(15 - 10) = -5, counts whole: -33.75,
        # which rounds half away from zero to -34.
        # Tapered as part of a -15 it would be -20 - 13.125 = -33.125, so -33.
        self.assertEqual(drop, 34)

    def test_without_the_specialty_the_hex_does_not_step(self) -> None:
        drop = self.hex_the_opponent(specialty=TechniqueFunction.STRIKE)

        # -20 - 8.75 = -28.75, which rounds to -29.
        self.assertEqual(drop, 29)
