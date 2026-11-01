"""Journeys for a combat style's skill and hit stat on the rolls (#4884, slice 2 of #4844).

Hobb was taught The Daring Dance, a style with its own Magic skill (he has 20 in it) that
hits with Strength. He fights a bandit at the Steading: the Strike goes through the web
dispatch (``combat_strike``) or telnet, each roll forced to a named outcome, and what is
read back is what the roll was handed and the breakdown the turn panel shows through the
consequence-outcomes REST endpoint. A technique cast goes through ``dispatch_player_action``
and the defense roll through a real NPC blow in ``resolve_round``.

Expected values come from the spec and the owner's rulings (2026-11-01), never from the
code's output:

- the Strike hit roll uses the style's hit stat and adds the style skill (weight 1, a
  skill like the strike skill) while the weapon and every held vow are on the style;
- a technique's hit roll adds the style skill only and keeps its own stat;
- the PC defense roll adds the style skill while the worn armor and vows are on the style;
- the bonus lapses on an unlisted weapon, armor or vow: the style skill stops counting,
  the hit stat and the defense type still apply, and the style's armor share is
  unchanged (an evasion style counting half of 4 soak takes 10 - 2 = 8 either way);
- the breakdown names the reason, the style struck through, and keeps the style's name
  as it was when the roll was made.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from integration_tests.test_defense_style_journeys import _TheYard
from integration_tests.test_strike_journeys import _StrikeField
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult, ExtraTraitTerm
from world.classes.factories import PathFactory
from world.combat.constants import ActionCategory, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatOpponent
from world.combat.services import resolve_round
from world.combat.tests.test_mounted_combat import _equip_weapon
from world.covenants.constants import CovenantType, DefenseStyle
from world.covenants.factories import (
    CombatStyleFactory,
    CombatStyleGearFactory,
    CovenantFactory,
    CovenantRoleFactory,
    engage_vow_with_thread,
)
from world.fatigue.constants import EffortLevel
from world.items.constants import GearArchetype
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.progression.factories import CharacterPathHistoryFactory
from world.scenes.constants import RoundStatus
from world.skills.factories import MagicSkillFactory, SkillFactory
from world.traits.factories import CheckSystemSetupFactory, SkillTraitFactory, StatTraitFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckOutcome,
    PointConversionRange,
    Trait,
    TraitType,
)
from world.vitals.models import CharacterVitals

STYLE = "The Daring Dance"
STYLE_RATING = 20
ONE = Decimal(1)


def _style(*gear: str, name: str = STYLE, **fields: Any):
    """A style with its own Magic skill and the given gear kinds."""
    style = CombatStyleFactory(name=name, skill=MagicSkillFactory(trait__name=name), **fields)
    for kind in gear:
        CombatStyleGearFactory(style=style, gear_archetype=kind)
    return style


def _give_style(sheet, style) -> None:
    sheet.combat_style = style
    sheet.save(update_fields=["combat_style"])


def _swear(sheet, role) -> None:
    engage_vow_with_thread(
        sheet,
        role,
        covenant=CovenantFactory(covenant_type=CovenantType.DURANCE),
        thread_level=1,
    )


class _StyledStriker(_StrikeField):
    """Hobb, taught The Daring Dance (Strength, 20 in its skill), at the Steading."""

    def setUp(self) -> None:
        super().setUp()
        self.strength = Trait.objects.get(name="strength")

    def styled(self, *gear: str):
        style = _style(*gear, hit_stat=self.strength)
        CharacterTraitValue.objects.create(
            character=self.sheet, trait=style.skill.trait, value=STYLE_RATING
        )
        _give_style(self.sheet, style)
        return style

    def style_term(self, style) -> ExtraTraitTerm:
        return ExtraTraitTerm(trait=style.skill.trait, weight=ONE)

    def hit_lines(self) -> list[dict[str, Any]]:
        hit_row = self.shown_rolls()[0]
        return hit_row["roll_breakdown"]["lines"]

    def style_line(self) -> dict[str, Any]:
        return next(line for line in self.hit_lines() if line["label"] == STYLE)


class StrikingInStyle(_StyledStriker):
    def test_a_listed_weapon_adds_the_style_skill_and_hits_with_the_style_stat(self) -> None:
        style = self.styled(GearArchetype.MELEE_ONE_HAND)
        sword = self.equip_sword()

        _damage, rolled = self.strike_and_resolve("Success", "Success", weapon_id=sword.pk)

        self.assertEqual(tuple(rolled[0]["extra_traits"]), (self.style_term(style),))
        self.assertEqual(rolled[0]["stat_override"], "strength")
        self.assertEqual(
            self.hit_lines(),
            [
                {
                    "label": "Melee Combat",
                    "value": "25",
                    "detail": "strike skill for one-handed melee",
                    "lapsed": False,
                },
                {
                    "label": "Strength",
                    "value": "",
                    "detail": "the style's hit stat",
                    "lapsed": False,
                },
                {"label": STYLE, "value": "20", "detail": "style skill", "lapsed": False},
            ],
        )

    def test_an_unlisted_weapon_lapses_the_skill_but_keeps_the_hit_stat(self) -> None:
        self.styled(GearArchetype.THROWN)
        sword = self.equip_sword()

        _damage, rolled = self.strike_and_resolve("Success", "Success", weapon_id=sword.pk)

        self.assertEqual(tuple(rolled[0]["extra_traits"]), ())
        self.assertEqual(rolled[0]["stat_override"], "strength")
        self.assertEqual(
            self.style_line(),
            {
                "label": STYLE,
                "value": "",
                "detail": "one-handed weapons are not this style's",
                "lapsed": True,
            },
        )

    def test_bare_hands_count_only_when_the_style_lists_unarmed(self) -> None:
        self.styled(GearArchetype.MELEE_ONE_HAND)

        _damage, rolled = self.strike_and_resolve("Success", "Success")

        self.assertEqual(tuple(rolled[0]["extra_traits"]), ())
        self.assertEqual(self.style_line()["detail"], "unarmed strikes are not this style's")
        self.assertTrue(self.style_line()["lapsed"])

    def test_bare_hands_in_an_unarmed_style_count(self) -> None:
        style = self.styled(GearArchetype.UNARMED)

        _damage, rolled = self.strike_and_resolve("Success", "Success")

        self.assertEqual(tuple(rolled[0]["extra_traits"]), (self.style_term(style),))
        self.assertEqual(self.style_line()["detail"], "style skill")

    def test_the_same_strike_through_telnet_lapses_the_same_way(self) -> None:
        self.styled(GearArchetype.MELEE_TWO_HAND)
        sword = self.equip_sword()

        self.telnet(self.hobb, f"strike bandit with {sword.display_name}")
        with self.forced_rolls("Success", "Success") as rolled:
            resolve_round(self.encounter)

        self.assertEqual(tuple(rolled[0]["extra_traits"]), ())
        self.assertEqual(rolled[0]["stat_override"], "strength")
        self.assertEqual(self.style_line()["detail"], "one-handed weapons are not this style's")

    def test_no_style_shows_no_style_line(self) -> None:
        sword = self.equip_sword()

        _damage, rolled = self.strike_and_resolve("Success", "Success", weapon_id=sword.pk)

        self.assertEqual(tuple(rolled[0]["extra_traits"]), ())
        self.assertEqual(rolled[0]["stat_override"], "agility")
        self.assertNotIn(STYLE, [line["label"] for line in self.hit_lines()])


class StrikingUnderAVow(_StyledStriker):
    def test_a_vow_the_style_lists_keeps_the_skill(self) -> None:
        style = self.styled(GearArchetype.MELEE_ONE_HAND)
        quicksilver = CovenantRoleFactory(name="Quicksilver")
        style.compatible_roles.add(quicksilver)
        _swear(self.sheet, quicksilver)
        sword = self.equip_sword()

        _damage, rolled = self.strike_and_resolve("Success", "Success", weapon_id=sword.pk)

        self.assertEqual(tuple(rolled[0]["extra_traits"]), (self.style_term(style),))
        self.assertEqual(self.style_line()["detail"], "style skill")

    def test_a_vow_the_style_does_not_list_lapses_the_skill(self) -> None:
        style = self.styled(GearArchetype.MELEE_ONE_HAND)
        style.compatible_roles.add(CovenantRoleFactory(name="Quicksilver"))
        _swear(self.sheet, CovenantRoleFactory(name="Bulwark"))
        sword = self.equip_sword()

        _damage, rolled = self.strike_and_resolve("Success", "Success", weapon_id=sword.pk)

        self.assertEqual(tuple(rolled[0]["extra_traits"]), ())
        self.assertEqual(
            self.style_line(),
            {
                "label": STYLE,
                "value": "",
                "detail": "Bulwark is not this style's vow",
                "lapsed": True,
            },
        )


class StrikeRecordsTheStyle(_StyledStriker):
    def test_renaming_the_style_later_does_not_rewrite_the_roll(self) -> None:
        style = self.styled(GearArchetype.MELEE_ONE_HAND)
        sword = self.equip_sword()
        self.strike_and_resolve("Success", "Success", weapon_id=sword.pk)

        style.name = "The Bold Dance"
        style.save(update_fields=["name"])

        self.assertEqual(self.style_line()["value"], "20")


class TechniquesInStyle(JourneyCase):
    """Ysmay, on a Path with a technique skill, casts a technique in a combat round: the
    technique hit roll keeps its own stat and adds the style skill. With no weapon in hand
    there is no weapon to test; a held vow still counts."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        self.path_skill = SkillFactory()
        yard = self.make_room("The Yard")
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.PHYSICAL,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        self.ysmay = self.make_player("Ysmay", room=yard)
        self.sheet = self.ysmay.sheet_data
        CharacterPathHistoryFactory(
            character=self.sheet, path=PathFactory(technique_skill=self.path_skill)
        )
        CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        CharacterAnimaFactory(character=self.sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=yard
        )
        CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.strength = StatTraitFactory(name="strength")

    def cast(self) -> dict[str, Any]:
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=self.technique.pk, action_slot="focused"
        )
        declared = dispatch_player_action(
            self.ysmay,
            ref,
            {
                "effort_level": EffortLevel.MEDIUM,
                "focused_opponent_target_id": self.opponent.pk,
            },
        )
        self.assertTrue(declared.deferred)
        rolls: list[dict] = []

        def spy(character, check_type, *args, **kwargs) -> CheckResult:
            rolls.append({"character": character, "check_type": check_type, **kwargs})
            return perform_check(character, check_type, *args, **kwargs)

        with patch("world.combat.services.perform_check", side_effect=spy):
            resolve_round(self.encounter)
        casts = [
            roll
            for roll in rolls
            if roll["character"] == self.ysmay and roll.get("effort_level") == EffortLevel.MEDIUM
        ]
        self.assertEqual(len(casts), 1)
        return casts[0]

    def path_term(self) -> ExtraTraitTerm:
        return ExtraTraitTerm(trait=self.path_skill.trait, weight=ONE)

    def test_the_hit_roll_adds_the_style_skill_and_keeps_its_own_stat(self) -> None:
        style = _style(GearArchetype.UNARMED, hit_stat=self.strength)
        _give_style(self.sheet, style)

        cast = self.cast()

        self.assertEqual(
            tuple(cast["extra_traits"]),
            (self.path_term(), ExtraTraitTerm(trait=style.skill.trait, weight=ONE)),
        )
        # No weapon in hand: the technique rolls its own check's stat, not Strength.
        self.assertIsNone(cast["stat_override"])

    def test_a_weapon_off_the_style_drops_only_the_style_skill(self) -> None:
        _give_style(self.sheet, _style(GearArchetype.MELEE_TWO_HAND, hit_stat=self.strength))
        _equip_weapon(self.ysmay, archetype=GearArchetype.MELEE_ONE_HAND)

        cast = self.cast()

        self.assertEqual(tuple(cast["extra_traits"]), (self.path_term(),))
        # The one-handed weapon's own stat, never the style's hit stat.
        self.assertEqual(cast["stat_override"], "agility")

    def test_with_no_weapon_in_hand_there_is_no_weapon_to_test(self) -> None:
        style = _style(GearArchetype.MELEE_TWO_HAND, hit_stat=self.strength)
        _give_style(self.sheet, style)

        cast = self.cast()

        self.assertEqual(
            tuple(cast["extra_traits"]),
            (self.path_term(), ExtraTraitTerm(trait=style.skill.trait, weight=ONE)),
        )

    def test_a_vow_off_the_style_still_lapses_a_weaponless_cast(self) -> None:
        _give_style(self.sheet, _style(GearArchetype.MELEE_TWO_HAND, hit_stat=self.strength))
        _swear(self.sheet, CovenantRoleFactory(name="Bulwark"))

        cast = self.cast()

        self.assertEqual(tuple(cast["extra_traits"]), (self.path_term(),))

    def test_a_style_skill_that_is_also_the_technique_skill_counts_once(self) -> None:
        style = CombatStyleFactory(name=STYLE, skill=self.path_skill)
        CombatStyleGearFactory(style=style, gear_archetype=GearArchetype.UNARMED)
        _give_style(self.sheet, style)

        cast = self.cast()

        self.assertEqual(tuple(cast["extra_traits"]), (self.path_term(),))


class _DefenseYard(_TheYard):
    """Each fighter wears light armor with 4 soak; the evasion style counts half of it."""

    def defend(self, fighter) -> dict[str, Any]:
        """Resolve one blade blow at ``fighter``, its defence roll a plain failure; return
        what the defence roll was handed."""
        rolled: list[dict[str, Any]] = []

        def defence(character, *_args: object, **kwargs: object) -> MagicMock:
            if character.pk == fighter.pk:
                rolled.append(dict(kwargs))
            return MagicMock(success_level=0)

        self.blade()
        resolve_round(
            self.encounter,
            defense_check_fn=defence,
            offense_check_fn=lambda *_a, **_k: MagicMock(success_level=2),
        )
        self.assertEqual(len(rolled), 1)
        return rolled[0]

    def styled(self, *gear: str):
        return _style(*gear, defense_style=DefenseStyle.EVASION, armor_share_tenths=5)


class DefendingInStyle(_DefenseYard):
    def test_listed_armor_adds_the_style_skill(self) -> None:
        style = self.styled(GearArchetype.MELEE_ONE_HAND, GearArchetype.LIGHT_ARMOR)
        mira = self.fighter("Mira", style=style)

        roll = self.defend(mira)

        self.assertEqual(
            tuple(roll["extra_traits"]), (ExtraTraitTerm(trait=style.skill.trait, weight=ONE),)
        )
        self.assertEqual(self.health(mira), 100 - (10 - 2))

    def test_unlisted_armor_lapses_the_skill_and_keeps_the_armor_share(self) -> None:
        mira = self.fighter(
            "Mira", style=self.styled(GearArchetype.MELEE_ONE_HAND, GearArchetype.HEAVY_ARMOR)
        )

        roll = self.defend(mira)

        self.assertEqual(tuple(roll["extra_traits"]), ())
        # The defense type still applies, and the style's share is unchanged: 2 of the 4.
        self.assertEqual(self.health(mira), 100 - (10 - 2))

    def test_a_vow_the_style_does_not_list_lapses_the_defense_too(self) -> None:
        mira = self.fighter("Mira", style=self.styled(GearArchetype.LIGHT_ARMOR))
        _swear(mira.sheet_data, CovenantRoleFactory(name="Bulwark"))

        roll = self.defend(mira)

        self.assertEqual(tuple(roll["extra_traits"]), ())


class ReadingTheDefenseRoll(_DefenseYard):
    """Mira's defense roll, as her Last Outcome card reads it (demo screen 5, "Defending in
    plate"). The Parry check weights Dodge, in which she has 15; she has 20 in the style
    skill. The defense roll lands at Partial Success, the full-damage rung, so the 10 blow
    lands on her armor: 2 of the 4 soak counts (5 of 10), and 8 lands. The result line is
    the roll's outcome, then the damage: "Partial Success, 8 damage"."""

    def setUp(self) -> None:
        super().setUp()
        self.dodge = SkillTraitFactory(name="Dodge")
        CheckTypeTraitFactory(check_type=self.defense, trait=self.dodge, weight=1)
        StatTraitFactory(name="agility")

    def defend(self, fighter, *, nameless: bool = False) -> dict[str, Any]:
        """Resolve one blade blow at ``fighter``; her real defence roll lands at Partial
        Success (success level 0, the full-damage rung). ``nameless`` blanks the
        attacker's name first."""
        del fighter  # she is the only fighter in the yard, so the blow is hers
        partial = CheckOutcome.objects.get(name="Partial Success")
        self.blade()
        if nameless:
            attacker = CombatOpponent.objects.get(encounter=self.encounter)
            attacker.name = ""
            attacker.save(update_fields=["name"])

        def defence(character, check_type, *args, **kwargs) -> CheckResult:
            with force_check_outcome(partial):
                return perform_check(character, check_type, *args, **kwargs)

        resolve_round(
            self.encounter,
            defense_check_fn=defence,
            offense_check_fn=lambda *_a, **_k: MagicMock(success_level=2),
        )
        return {}

    def mira(self, *gear: str):
        style = self.styled(*gear)
        mira = self.fighter("Mira", style=style)
        CharacterTraitValue.objects.create(character=mira.sheet_data, trait=self.dodge, value=15)
        CharacterTraitValue.objects.create(
            character=mira.sheet_data, trait=style.skill.trait, value=STYLE_RATING
        )
        return mira, style

    def rows_for(self, viewer, defender) -> list[dict[str, Any]]:
        response = self.api(self.account_of(viewer)).get(
            "/api/checks/consequence-outcomes/",
            {"character": defender.sheet_data.pk, "encounter": self.encounter.pk},
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def defense_row(self, defender) -> dict[str, Any]:
        rows = self.rows_for(defender, defender)
        self.assertEqual(len(rows), 1)
        return rows[0]

    def attacker(self) -> str:
        return CombatOpponent.objects.get(encounter=self.encounter).name

    def test_in_listed_armor_the_style_skill_counts(self) -> None:
        mira, _style = self.mira(GearArchetype.LIGHT_ARMOR)
        self.defend(mira)

        self.assertEqual(
            self.defense_row(mira)["roll_breakdown"],
            {
                "heading": f"Defense against {self.attacker()}",
                "lines": [
                    {"label": "Dodge", "value": "15", "detail": "defense skill", "lapsed": False},
                    {"label": STYLE, "value": "20", "detail": "style skill", "lapsed": False},
                    {
                        "label": "Armor, 5 of 10",
                        "value": "",
                        "detail": "the style's armor share",
                        "lapsed": False,
                    },
                ],
                "result": "Partial Success, 8 damage",
                "result_note": "",
            },
        )

    def test_in_unlisted_armor_the_style_is_struck_through_and_the_share_unchanged(self) -> None:
        mira, _style = self.mira(GearArchetype.HEAVY_ARMOR)
        self.defend(mira)

        lines = self.defense_row(mira)["roll_breakdown"]["lines"]
        self.assertEqual(
            lines[1],
            {
                "label": STYLE,
                "value": "",
                "detail": "light armor is not this style's",
                "lapsed": True,
            },
        )
        self.assertEqual(lines[2]["label"], "Armor, 5 of 10")
        self.assertEqual(self.health(mira), 100 - (10 - 2))

    def test_a_bystander_sees_no_breakdown(self) -> None:
        from world.scenes.factories import SceneParticipationFactory

        mira, _style = self.mira(GearArchetype.LIGHT_ARMOR)
        self.defend(mira)
        wren = self.make_player("Wren", room=self.room)
        SceneParticipationFactory(scene=self.encounter.scene, account=self.account_of(wren))

        rows = self.rows_for(wren, mira)

        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["roll_breakdown"])
        # Nor the numbers behind it, nor how much damage she took.
        self.assertEqual(rows[0]["modifiers"], [])
        self.assertEqual(rows[0]["modifier_total"], 0)
        self.assertEqual(rows[0]["summary"], "")
        self.assertEqual(self.defense_row(mira)["summary"], "Partial Success, 8 damage")
        self.assertIsNotNone(self.defense_row(mira)["roll_breakdown"])

    def test_a_nameless_attacker_still_gives_a_defense_row_kept_from_bystanders(self) -> None:
        from world.scenes.factories import SceneParticipationFactory

        mira, _style = self.mira(GearArchetype.LIGHT_ARMOR)
        self.defend(mira, nameless=True)
        wren = self.make_player("Wren", room=self.room)
        SceneParticipationFactory(scene=self.encounter.scene, account=self.account_of(wren))

        (seen,) = self.rows_for(wren, mira)
        self.assertIsNone(seen["roll_breakdown"])
        self.assertEqual((seen["modifiers"], seen["modifier_total"]), ([], 0))
        self.assertEqual(seen["summary"], "")
        own = self.defense_row(mira)["roll_breakdown"]
        self.assertEqual(own["heading"], "Defense roll")
        self.assertEqual(own["result"], "Partial Success, 8 damage")

    def test_renaming_the_style_later_does_not_rewrite_the_row(self) -> None:
        mira, style = self.mira(GearArchetype.LIGHT_ARMOR)
        self.defend(mira)

        style.name = "The Bold Dance"
        style.armor_share_tenths = 9
        style.save(update_fields=["name", "armor_share_tenths"])

        lines = self.defense_row(mira)["roll_breakdown"]["lines"]
        self.assertEqual(lines[1]["label"], STYLE)
        self.assertEqual(lines[2]["label"], "Armor, 5 of 10")
