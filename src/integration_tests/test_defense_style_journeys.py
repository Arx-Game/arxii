"""Journeys for how a combat style decides a character's defense (#4809, slice 5 of #4759).

The same NPC blow, a 10-damage strike that carries a defence check, lands on fighters who
each wear one piece of light armor with 4 soak. The defence roll is held at a plain
failure (success level 0, the full-damage rung), so every blow arrives at 10 and only the
defense style decides what comes off it.

- Evasion style counting half its armor (5 tenths): 2 of the 4 soak counts. 10 - 2 = 8.
- Mitigation style counting all of it: 4 soak. 10 - 4 = 6.
- Mitigation against a level 12 attacker, past the default level gap of 3: half (the
  default 50 percent) of the 4 the armor stopped leaks back. 10 - 4 + 2 = 8.
- Barrier style counting half its armor, behind a 10-point force field: the ward rolls the
  attack's own defence check. A partial success (level 1) takes half the blow (5), the
  armor takes 2 of the rest, 3 lands. A clean one (level 2) takes all of it. A failure
  takes none: 10 - 2 = 8, and the ward keeps its whole buffer.
- No style and no vow profile: all 4 soak counts, the field absorbs without a roll, and
  only the defence roll is rolled (the behavior before #4759).
- No style but an engaged vow whose defense profile is Barrier: the ward rolls (the vow
  profile is the fallback). A style on top of that vow wins.

Expected values come from the spec (#4759 Decisions 2 and 3, Verification 5) and the
MovementConfig field defaults (gap 3, leak 50 percent); the defence ladder is
``world.combat.constants`` (2 = no damage, 1 = half).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.combat.constants import (
    OpponentTier,
    ParticipantStatus,
    StrikeDelivery,
    TargetingMode,
    TargetSelection,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    OpponentTierTemplateFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import MovementConfig
from world.combat.services import resolve_round
from world.combat.services.boss.creature_spawn import spawn_from_creature_template
from world.conditions.constants import FORCE_FIELD_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.conditions.services import _install_reactive_side_effects
from world.covenants.constants import DefenseStyle
from world.covenants.defense import defense_style_for
from world.covenants.factories import (
    CombatStyleFactory,
    CovenantRoleDefenseProfileFactory,
    make_engaged_member,
)
from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.magic.effect_palette_content import ensure_force_field_content
from world.magic.factories import CharacterAnimaFactory
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.seeds.checks import seed_check_resolution_tables
from world.vitals.models import CharacterVitals

STRIKE = 10
ARMOR = 4
HEALTH = 100


class RollsInTurn:
    """A defence roll that hands out success levels per character, in the order rolled."""

    def __init__(self, levels: dict[str, list[int]]) -> None:
        self.levels = levels
        self.calls: dict[str, int] = {}

    def __call__(self, character: Any, *_args: object, **_kwargs: object) -> MagicMock:
        name = character.db_key
        self.calls[name] = self.calls.get(name, 0) + 1
        queue = self.levels.get(name, [])
        return MagicMock(success_level=queue.pop(0) if queue else 0)


def _clean_hit(*_args: object, **_kwargs: object) -> MagicMock:
    return MagicMock(success_level=2)


class _TheYard(JourneyCase):
    """One fighter in light armor, one blade, a fight in DECLARING round 1."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        ensure_force_field_content()
        OpponentTierTemplateFactory(tier=OpponentTier.MOOK, base_health=30, base_soak=0)
        self.room = self.make_room("The Yard")
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        self.defense = CheckTypeFactory(name="Parry")
        self.evasion = CombatStyleFactory(
            name="Duelist's Footwork", defense_style=DefenseStyle.EVASION, armor_share_tenths=5
        )
        self.mitigation = CombatStyleFactory(
            name="Shieldwall Drill", defense_style=DefenseStyle.GEAR_SOAK, armor_share_tenths=10
        )
        self.barrier = CombatStyleFactory(
            name="Warding Stance", defense_style=DefenseStyle.BARRIER, armor_share_tenths=5
        )

    def fighter(self, name: str, *, style=None):
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterVitals.objects.create(
            character_sheet=sheet, health=HEALTH, max_health=HEALTH, base_max_health=HEALTH
        )
        CharacterAnimaFactory(character=sheet, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet)
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        template = ItemTemplateFactory(
            name=f"{name}'s jerkin",
            gear_archetype=GearArchetype.LIGHT_ARMOR,
            base_armor_soak=ARMOR,
            max_durability=30,
        )
        EquippedItemFactory(
            character=sheet,
            item_instance=ItemInstanceFactory(template=template, durability=30),
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        character.equipped_items.invalidate()
        if style is not None:
            sheet.combat_style = style
            sheet.save(update_fields=["combat_style"])
        return character

    def ward(self, character, buffer: int = 10) -> ConditionInstance:
        template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)
        inst = ConditionInstanceFactory(condition=template, target=character)
        inst.absorb_remaining = buffer
        inst.save(update_fields=["absorb_remaining"])
        _install_reactive_side_effects(character, template, inst)
        character.trigger_handler.refresh()
        return inst

    def blade(self, *, level: int = 1) -> None:
        pool = ThreatPoolFactory(name="Blade attacks")
        ThreatPoolEntryFactory(
            pool=pool,
            name="Blade strike",
            base_damage=STRIKE,
            delivery=StrikeDelivery.MELEE,
            targeting_mode=TargetingMode.SINGLE,
            target_selection=TargetSelection.HIGHEST_THREAT,
            defense_check_type=self.defense,
        )
        template = CreatureTemplateFactory(
            name="Blade", tier=OpponentTier.MOOK, threat_pool=pool, speed_hops=0
        )
        opponent = spawn_from_creature_template(self.encounter, template)
        opponent.level = level
        opponent.save(update_fields=["level"])

    def resolve(self, roll: RollsInTurn) -> None:
        resolve_round(self.encounter, defense_check_fn=roll, offense_check_fn=_clean_hit)

    def health(self, character) -> int:
        return CharacterVitals.objects.get(character_sheet=character.sheet_data).health


class ArmorCountsAtEachStylesShare(_TheYard):
    def test_evasion_counts_half_its_armor(self) -> None:
        mira = self.fighter("Mira", style=self.evasion)
        self.blade()

        self.resolve(RollsInTurn({"Mira": [0]}))

        self.assertEqual(self.health(mira), HEALTH - (STRIKE - 2))

    def test_mitigation_counts_all_of_it(self) -> None:
        gorm = self.fighter("Gorm", style=self.mitigation)
        self.blade()

        self.resolve(RollsInTurn({"Gorm": [0]}))

        self.assertEqual(self.health(gorm), HEALTH - (STRIKE - ARMOR))

    def test_no_style_counts_all_armor_as_before(self) -> None:
        bram = self.fighter("Bram")
        self.blade()

        self.resolve(RollsInTurn({"Bram": [0]}))

        self.assertEqual(self.health(bram), HEALTH - (STRIKE - ARMOR))


class AMuchStrongerAttackerLeaksThroughMitigation(_TheYard):
    def test_past_the_level_gap_half_the_soak_leaks(self) -> None:
        gorm = self.fighter("Gorm", style=self.mitigation)
        self.blade(level=12)

        self.resolve(RollsInTurn({"Gorm": [0]}))

        self.assertEqual(self.health(gorm), HEALTH - (STRIKE - ARMOR + 2))

    def test_within_the_gap_nothing_leaks(self) -> None:
        gorm = self.fighter("Gorm", style=self.mitigation)
        self.blade(level=3)

        self.resolve(RollsInTurn({"Gorm": [0]}))

        self.assertEqual(self.health(gorm), HEALTH - (STRIKE - ARMOR))

    def test_the_gap_and_leak_are_read_from_the_config_row(self) -> None:
        MovementConfig.objects.create(
            pk=1, mitigation_level_gap_cap=15, mitigation_leak_percent=100
        )
        gorm = self.fighter("Gorm", style=self.mitigation)
        self.blade(level=12)

        self.resolve(RollsInTurn({"Gorm": [0]}))

        self.assertEqual(self.health(gorm), HEALTH - (STRIKE - ARMOR))  # 11 levels <= 15

    def test_an_evasion_fighter_does_not_leak(self) -> None:
        mira = self.fighter("Mira", style=self.evasion)
        self.blade(level=12)

        self.resolve(RollsInTurn({"Mira": [0]}))

        self.assertEqual(self.health(mira), HEALTH - (STRIKE - 2))


class TheBarrierRolls(_TheYard):
    def test_a_partial_roll_takes_half_the_blow(self) -> None:
        sel = self.fighter("Sel", style=self.barrier)
        ward = self.ward(sel)
        self.blade()
        roll = RollsInTurn({"Sel": [0, 1]})

        self.resolve(roll)

        self.assertEqual(roll.calls["Sel"], 2)  # the defence roll, then the ward's
        self.assertEqual(self.health(sel), HEALTH - (STRIKE - 5 - 2))
        self.assertEqual(ConditionInstance.objects.get(pk=ward.pk).absorb_remaining, 5)

    def test_a_clean_roll_takes_all_of_it(self) -> None:
        sel = self.fighter("Sel", style=self.barrier)
        self.ward(sel)
        self.blade()

        self.resolve(RollsInTurn({"Sel": [0, 2]}))

        self.assertEqual(self.health(sel), HEALTH)

    def test_a_failed_roll_takes_none(self) -> None:
        sel = self.fighter("Sel", style=self.barrier)
        ward = self.ward(sel)
        self.blade()

        self.resolve(RollsInTurn({"Sel": [0, 0]}))

        self.assertEqual(self.health(sel), HEALTH - (STRIKE - 2))
        self.assertEqual(ConditionInstance.objects.get(pk=ward.pk).absorb_remaining, 10)

    def test_with_no_style_the_ward_absorbs_without_a_roll(self) -> None:
        bram = self.fighter("Bram")
        ward = self.ward(bram, buffer=6)
        self.blade()
        roll = RollsInTurn({"Bram": [0]})

        self.resolve(roll)

        self.assertEqual(roll.calls["Bram"], 1)  # the defence roll only
        self.assertEqual(self.health(bram), HEALTH)  # 6 absorbed, 4 soaked
        self.assertFalse(ConditionInstance.objects.filter(pk=ward.pk).exists())  # spent


class TheVowProfileIsTheFallback(_TheYard):
    def _sworn(self, name: str, *, style=None):
        character = self.fighter(name, style=style)
        membership = make_engaged_member(character_sheet=character.sheet_data)
        character.covenant_roles.invalidate()
        CovenantRoleDefenseProfileFactory(
            covenant_role=membership.covenant_role,
            style=DefenseStyle.BARRIER,
            gear_additive_tenths=10,
        )
        return character

    def test_a_barrier_vow_with_no_style_rolls_the_ward(self) -> None:
        aud = self._sworn("Aud")
        self.ward(aud)
        self.blade()
        roll = RollsInTurn({"Aud": [0, 1]})

        self.resolve(roll)

        self.assertEqual(roll.calls["Aud"], 2)
        self.assertEqual(self.health(aud), HEALTH - (STRIKE - 5 - ARMOR))  # 1 lands

    def test_a_style_wins_over_the_vow(self) -> None:
        aud = self._sworn("Aud", style=self.evasion)
        self.assertEqual(defense_style_for(aud).style, DefenseStyle.EVASION)
        self.ward(aud)
        self.blade()
        roll = RollsInTurn({"Aud": [0]})

        self.resolve(roll)

        self.assertEqual(roll.calls["Aud"], 1)  # evasion: no ward roll
        self.assertEqual(self.health(aud), HEALTH)  # 10 absorbed outright
