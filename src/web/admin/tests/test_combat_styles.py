"""Which combat styles work with a vow, and what a mismatch costs (#4932, slice 7 of #4843).

The reads the vow page's style module and the kit view's Style row share. Whether a style
works is ``style_fit``'s rule; these check the batched form agrees with it, the holder
count and the cost wording.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from web.admin.authoring import combat_styles
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CombatStyleFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.models import CombatStyle
from world.covenants.style_fit import style_lists_vow, style_vow_ids, styles_listing_vow
from world.skills.factories import SkillFactory


class StylesForVowTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.vow = CovenantRoleFactory(name="Style Vow", slug="style-vow")
        cls.other = CovenantRoleFactory(name="Style Other", slug="style-other")
        cls.sub = SubroleCovenantRoleFactory(
            name="Style Vow Choir", slug="style-vow-choir", parent_role=cls.vow
        )
        cls.skill = SkillFactory(trait__name="Footwork Drill")
        cls.listed = CombatStyleFactory(name="Listed Style", skill=cls.skill)
        cls.listed.compatible_roles.add(cls.vow)
        cls.unlisted = CombatStyleFactory(name="Unlisted Style")
        cls.unlisted.compatible_roles.add(cls.other)
        cls.sub_only = CombatStyleFactory(name="Sub Only Style")
        cls.sub_only.compatible_roles.add(cls.sub)

    def test_the_batched_form_agrees_with_the_single_one(self) -> None:
        for role in (self.vow, self.other, self.sub):
            listing = styles_listing_vow(role)
            for style in (self.listed, self.unlisted, self.sub_only):
                with self.subTest(role=role.name, style=style.name):
                    self.assertEqual(style.pk in listing, style_lists_vow(style, role))
        # A sub-role counts by its anchor; the anchor does not count by a sub-role.
        self.assertEqual(styles_listing_vow(self.sub), {self.listed.pk, self.sub_only.pk})
        self.assertEqual(styles_listing_vow(self.vow), {self.listed.pk})

    def test_rows_by_name_with_works_skill_and_url(self) -> None:
        rows = combat_styles.styles_for_vow(self.vow)
        self.assertEqual(
            [(r.name, r.works, r.skill_name) for r in rows],
            [
                ("Listed Style", True, "Footwork Drill"),
                ("Sub Only Style", False, None),
                ("Unlisted Style", False, None),
            ],
        )
        self.assertEqual(
            rows[0].url, reverse("admin:arxii_combatstyle_change", args=[self.listed.pk])
        )
        self.assertEqual(rows[0].mismatch, "")

    def test_the_mismatch_names_the_skill_or_says_there_is_none(self) -> None:
        row = combat_styles.StyleRow(
            name="x", url="", works=False, skill_name="Footwork Drill", holders=0
        )
        self.assertEqual(
            row.mismatch,
            "A holder fighting this style loses Footwork Drill on attack and defense rolls; "
            "its hit stat and defense type still apply.",
        )
        bare = combat_styles.StyleRow(name="x", url="", works=False, skill_name=None, holders=0)
        self.assertEqual(
            bare.mismatch, "No style skill to lose; its hit stat and defense type apply as usual."
        )

    def test_an_inactive_skill_has_nothing_to_lose(self) -> None:
        style = CombatStyleFactory(
            name="Retired Skill Style", skill=SkillFactory(trait__name="Old Drill", is_active=False)
        )
        row = next(r for r in combat_styles.styles_for_vow(self.vow) if r.name == style.name)
        self.assertIsNone(row.skill_name)

    def test_holders_count_live_primary_holders_of_this_vow_once(self) -> None:
        live = CharacterCovenantRoleFactory(covenant_role=self.vow)
        live.character_sheet.combat_style = self.listed
        live.character_sheet.save()
        # The same character in a second covenant counts once.
        CharacterCovenantRoleFactory(covenant_role=self.vow, character_sheet=live.character_sheet)
        left = CharacterCovenantRoleFactory(covenant_role=self.vow, left_at=timezone.now())
        secondary = CharacterCovenantRoleFactory(covenant_role=self.vow, is_secondary=True)
        elsewhere = CharacterCovenantRoleFactory(covenant_role=self.other)
        for membership in (left, secondary, elsewhere):
            membership.character_sheet.combat_style = self.listed
            membership.character_sheet.save()
        rows = {r.name: r.holders for r in combat_styles.styles_for_vow(self.vow)}
        self.assertEqual(rows, {"Listed Style": 1, "Sub Only Style": 0, "Unlisted Style": 0})

    def test_the_query_count_is_flat_in_the_number_of_styles(self) -> None:
        with CaptureQueriesContext(connection) as few:
            combat_styles.styles_for_vow(self.vow)
        for index in range(4):
            style = CombatStyleFactory(
                name=f"Flat Style {index}", skill=SkillFactory(trait__name=f"Flat Drill {index}")
            )
            style.compatible_roles.add(self.vow)
        with CaptureQueriesContext(connection) as many:
            rows = combat_styles.styles_for_vow(self.vow)
        self.assertEqual(len(rows), 7)
        self.assertEqual(len(many), len(few))
        self.assertEqual(len(many), 3)

    def test_no_styles_no_rows(self) -> None:
        CombatStyle.objects.all().delete()
        self.assertEqual(combat_styles.styles_for_vow(self.vow), [])

    def test_the_kit_line_against_one_vow(self) -> None:
        works = combat_styles.style_on_vow(self.listed, self.vow, style_vow_ids(self.listed))
        self.assertEqual((works.works, works.text), (True, "works with Style Vow"))
        skilled = CombatStyleFactory(name="Skilled Elsewhere", skill=SkillFactory())
        self.assertEqual(
            combat_styles.style_on_vow(skilled, self.vow, style_vow_ids(skilled)).text,
            "not a style for Style Vow: its skill does not count on attack and defense rolls",
        )
        self.assertEqual(
            combat_styles.style_on_vow(self.unlisted, self.vow, style_vow_ids(self.unlisted)).text,
            "not a style for Style Vow",
        )
