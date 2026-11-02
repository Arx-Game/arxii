"""The kit view's reads for one character (#4918, slice 5 of #4843).

Tempest is a vow at thread level 2 with an Evasion defense profile. Its holder knows
Bolt (a strike), Watch (perception, which the vow adds nothing to) and Bare (no function
tag). The vow adds to strikes: a base row, a base row that unlocks at level 5, a row
riding covenant allies' casts, a row on the chosen Spark pick, and a row on Unchosen, a
pick the holder did not choose. At pick level 1 the holder chose Spark (4) and Gale (3):
7 of a budget of 4.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from web.admin.kit_view import live
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.covenants.constants import CovenantType, DefenseStyle
from world.covenants.factories import (
    CharacterVowFocusPickFactory,
    CovenantFactory,
    CovenantRoleDefenseProfileFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    VowAddedEffectFactory,
    VowFocusPickConfigFactory,
    VowFocusPickFactory,
    engage_vow_with_thread,
)
from world.covenants.perks.constants import PerkBeneficiary
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.progression.factories import CharacterPathHistoryFactory


def _technique(name: str, *functions: str):
    technique = TechniqueFactory(name=name)
    for function in functions:
        TechniqueFunctionTagFactory(technique=technique, function=function)
    return technique


def _know(sheet, *techniques) -> None:
    for technique in techniques:
        CharacterTechniqueFactory(character=sheet, technique=technique)


class KitLiveCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        VowFocusPickConfigFactory(budget_per_level=4)
        cls.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        cls.vow = CovenantRoleFactory(name="Tempest", covenant_type=CovenantType.DURANCE)
        CovenantRoleDefenseProfileFactory(covenant_role=cls.vow, style=DefenseStyle.EVASION)
        cls.spark = VowFocusPickFactory(covenant_role=cls.vow, name="Spark", value=4)
        cls.gale = VowFocusPickFactory(covenant_role=cls.vow, name="Gale", value=3)
        cls.unchosen = VowFocusPickFactory(covenant_role=cls.vow, name="Unchosen", value=2)

        strike = TechniqueFunction.STRIKE
        cls.base = VowAddedEffectFactory(covenant_role=cls.vow, function=strike)
        cls.locked = VowAddedEffectFactory(
            covenant_role=cls.vow, function=strike, unlock_thread_level=5
        )
        cls.allies = VowAddedEffectFactory(
            covenant_role=cls.vow,
            function=strike,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            unlock_thread_level=1,
        )
        cls.on_spark = VowAddedEffectFactory(
            covenant_role=cls.vow, function=strike, focus_pick=cls.spark
        )
        cls.on_unchosen = VowAddedEffectFactory(
            covenant_role=cls.vow, function=strike, focus_pick=cls.unchosen
        )

        cls.bolt = _technique("Bolt", strike)
        cls.watch = _technique("Watch", TechniqueFunction.PERCEPTION)
        cls.bare = _technique("Bare")

        cls.sheet = CharacterSheetFactory()
        membership = engage_vow_with_thread(
            cls.sheet, cls.vow, covenant=cls.covenant, thread_level=2
        )
        for pick in (cls.spark, cls.gale):
            CharacterVowFocusPickFactory(character_role=membership, pick=pick)
        _know(cls.sheet, cls.watch, cls.bolt, cls.bare)
        CharacterPathHistoryFactory(character=cls.sheet, path=PathFactory(name="Tomes"))
        CharacterGiftFactory(character=cls.sheet, gift=GiftFactory(name="Storms"))


class TechniqueLinesTest(KitLiveCase):
    def _line(self, name: str) -> live.TechniqueLine:
        kit = live.kit_for(self.sheet)
        return next(line for line in kit.techniques if line.technique.label == name)

    def test_techniques_are_ordered_by_name_and_linked(self) -> None:
        kit = live.kit_for(self.sheet)
        self.assertEqual(
            [line.technique.label for line in kit.techniques], ["Bare", "Bolt", "Watch"]
        )
        self.assertEqual(
            self._line("Bolt").technique.url,
            reverse("admin:arxii_technique_change", args=[self.bolt.pk]),
        )
        self.assertEqual(self._line("Bolt").functions, "Strike")
        self.assertEqual(self._line("Bolt").base, self.bolt.cached_effect_summary["summary"])

    def test_base_lines_then_the_chosen_pick(self) -> None:
        groups = self._line("Bolt").groups
        self.assertEqual([group.label for group in groups], ["Base", "Spark"])
        base_texts = [line.text for line in groups[0].lines]
        self.assertEqual(len(base_texts), 3)
        self.assertIn(self.base.cached_effect_summary, base_texts)
        self.assertEqual(
            [line.text for line in groups[1].lines], [self.on_spark.cached_effect_summary]
        )

    def test_a_pick_the_character_did_not_choose_is_absent(self) -> None:
        texts = [line.text for group in self._line("Bolt").groups for line in group.lines]
        self.assertEqual(len(texts), 4)
        self.assertNotIn("Unchosen", [group.label for group in self._line("Bolt").groups])

    def test_a_row_above_the_thread_level_is_marked_with_its_unlock(self) -> None:
        lines = self._line("Bolt").groups[0].lines
        marks = {line.text: line.unlocks_at for line in lines}
        self.assertEqual(marks[self.locked.cached_effect_summary], 5)
        self.assertIsNone(marks[self.base.cached_effect_summary])

    def test_a_row_riding_allies_casts_names_who_it_rides(self) -> None:
        lines = self._line("Bolt").groups[0].lines
        rides = {line.text: line.rides for line in lines}
        self.assertEqual(rides[self.allies.cached_effect_summary], "Covenant Allies")
        self.assertEqual(rides[self.base.cached_effect_summary], "")

    def test_a_technique_the_vow_adds_nothing_to_says_so(self) -> None:
        watch = self._line("Watch")
        self.assertEqual(watch.groups, [])
        self.assertEqual(watch.nothing, "nothing: Tempest adds nothing to Perception")
        self.assertEqual(self._line("Bare").nothing, "nothing: it carries no function tag")


class PicksAndSheetTest(KitLiveCase):
    def test_the_chosen_picks_by_level_with_the_spend_over_budget(self) -> None:
        (level,) = live.kit_for(self.sheet).picks
        self.assertEqual((level.vow, level.level, level.spent, level.budget), ("Tempest", 1, 7, 4))
        self.assertTrue(level.over)
        self.assertEqual([pick.label for pick in level.picks], ["Gale", "Spark"])
        self.assertEqual(
            level.picks[1].url, reverse("admin:arxii_vowfocuspick_change", args=[self.spark.pk])
        )

    def test_the_picks_link_searches_the_changelist_by_character(self) -> None:
        kit = live.kit_for(self.sheet)
        changelist = reverse("admin:arxii_charactervowfocuspick_changelist")
        self.assertEqual(kit.picks_url, f"{changelist}?q={self.sheet.character.db_key}")

    def test_the_sheet_names_path_gift_vow_level_and_defense(self) -> None:
        kit = live.kit_for(self.sheet)
        self.assertEqual(kit.sheet.path, "Tomes")
        self.assertEqual(kit.sheet.gifts, ["Storms"])
        (vow,) = kit.sheet.vows
        self.assertEqual(
            (vow.vow.label, vow.level, vow.defense, vow.is_secondary, vow.engaged),
            ("Tempest", 2, "Evasion", False, True),
        )
        self.assertEqual(vow.vow.url, reverse("admin_vow_builder", args=[self.vow.pk]))
        self.assertEqual(kit.level, 2)


class AbsentPartsTest(KitLiveCase):
    def test_a_character_with_no_vow_and_no_technique(self) -> None:
        kit = live.kit_for(CharacterSheetFactory())
        self.assertEqual((kit.techniques, kit.picks, kit.sheet.vows), ([], [], []))
        self.assertEqual((kit.sheet.path, kit.sheet.gifts, kit.level), ("", [], None))

    def test_a_character_with_no_vow_knows_techniques_the_vow_adds_nothing_to(self) -> None:
        sheet = CharacterSheetFactory()
        _know(sheet, self.bolt)
        (line,) = live.kit_for(sheet).techniques
        self.assertEqual(line.nothing, "nothing: no engaged vow")

    def test_a_secondary_vow_only(self) -> None:
        sheet = CharacterSheetFactory()
        engage_vow_with_thread(
            sheet, self.vow, covenant=self.covenant, thread_level=1, is_secondary=True
        )
        _know(sheet, self.bolt)
        kit = live.kit_for(sheet)
        self.assertEqual(kit.picks, [])
        (vow,) = kit.sheet.vows
        self.assertTrue(vow.is_secondary)
        self.assertIsNone(kit.level)
        # A secondary vow's base rows still ride the character's own casts.
        (line,) = kit.techniques
        self.assertEqual([group.label for group in line.groups], ["Base"])

    def test_a_sub_role_holder_counts_the_anchor_picks(self) -> None:
        choir = SubroleCovenantRoleFactory(name="Tempest Choir", parent_role=self.vow)
        sheet = CharacterSheetFactory()
        membership = engage_vow_with_thread(sheet, choir, covenant=self.covenant, thread_level=3)
        CharacterVowFocusPickFactory(character_role=membership, pick=self.gale)
        kit = live.kit_for(sheet)
        (level,) = kit.picks
        self.assertEqual((level.vow, level.spent, level.over), ("Tempest Choir", 3, False))
        (vow,) = kit.sheet.vows
        # The thread keys on the anchor; the sub-role has no profile, so the anchor's counts.
        self.assertEqual((vow.level, vow.defense), (3, "Evasion"))


class QueryCountTest(KitLiveCase):
    """The reads do not grow with techniques, added effects or picks."""

    _made = 0

    def _holder(self, *, techniques: int, picks: int):
        # Each call names its rows apart: two calls of one size would otherwise reuse a pick
        # and add a second identical effect on it, which Postgres's scope constraint refuses.
        QueryCountTest._made += 1
        run = QueryCountTest._made
        sheet = CharacterSheetFactory()
        membership = engage_vow_with_thread(sheet, self.vow, covenant=self.covenant, thread_level=2)
        for index in range(techniques):
            technique = _technique(f"Count {run} {index}", TechniqueFunction.STRIKE)
            _know(sheet, technique)
        for index in range(picks):
            pick = VowFocusPickFactory(
                covenant_role=self.vow, name=f"Count pick {run} {index}", pick_level=1
            )
            CharacterVowFocusPickFactory(character_role=membership, pick=pick)
            VowAddedEffectFactory(
                covenant_role=self.vow, function=TechniqueFunction.STRIKE, focus_pick=pick
            )
        return sheet

    def _count(self, sheet) -> int:
        with CaptureQueriesContext(connection) as queries:
            live.kit_for(sheet)
        return len(queries)

    def test_the_count_is_the_same_at_two_sizes(self) -> None:
        self._count(self._holder(techniques=1, picks=1))  # warm the shared rows
        small = self._count(self._holder(techniques=1, picks=1))
        large = self._count(self._holder(techniques=6, picks=4))
        self.assertEqual(small, large)
        self.assertEqual(large, KIT_QUERIES)


#: One primary vow with picks and techniques the vow adds to: the memberships, thread
#: levels, the techniques with six payload prefetches, their function tags, the
#: sub-role resolve, the added effects with four payload prefetches, the chosen picks
#: (twice: the filter and the picks module), the pick limits, path, gifts and defense.
KIT_QUERIES = 22
