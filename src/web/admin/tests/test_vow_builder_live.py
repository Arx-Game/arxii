"""The vow page's reads: budget per level and what an unsaved edit does to holders (#4880).

Holder rows are built straight from factories: ``CharacterVowFocusPick`` runs its rules
in ``clean()`` only, and the warning has to see a holder whatever their level. Built in
``setUp``: the sheet factories create Evennia objects, which ``setUpTestData`` cannot
deepcopy.
"""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from web.admin.vow_builder import live
from world.covenants.constants import FocusPickLimitKind
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CharacterVowFocusPickFactory,
    CovenantRoleFactory,
    VowFocusPickConfigFactory,
    VowFocusPickFactory,
    VowFocusPickLimitFactory,
)
from world.covenants.models import VowFocusPickConfig


class BudgetRowsTests(TestCase):
    def setUp(self) -> None:
        self.role = CovenantRoleFactory(name="Fulmination")
        VowFocusPickFactory(covenant_role=self.role, pick_level=1, name="Arcing Charge", value=4)
        under = VowFocusPickFactory(
            covenant_role=self.role, pick_level=2, name="Under Open Sky", value=4
        )
        VowFocusPickLimitFactory(pick=under, kind=FocusPickLimitKind.SETTING, frequency_tenths=6)
        VowFocusPickFactory(covenant_role=self.role, pick_level=3, name="Kneel", value=4)
        VowFocusPickFactory(covenant_role=self.role, pick_level=3, name="Static Halo", value=2)

    def test_offered_prices_per_level_against_the_default_budget(self) -> None:
        rows = live.budget_rows(self.role)
        self.assertEqual(
            [(r.level, r.offered, r.budget) for r in rows], [(1, 4, 4), (2, 2, 4), (3, 6, 4)]
        )

    def test_reading_the_budget_never_creates_the_config(self) -> None:
        live.budget_rows(self.role)
        self.assertFalse(VowFocusPickConfig.objects.exists())

    def test_a_saved_budget_is_read(self) -> None:
        VowFocusPickConfigFactory(budget_per_level=6)
        self.assertEqual({r.budget for r in live.budget_rows(self.role)}, {6})


class HolderImpactTests(TestCase):
    def setUp(self) -> None:
        self.role = CovenantRoleFactory(name="Fulmination")
        self.kneel = VowFocusPickFactory(
            covenant_role=self.role, pick_level=3, name="Kneel", value=4
        )
        VowFocusPickLimitFactory(
            pick=self.kneel, kind=FocusPickLimitKind.TARGET, frequency_tenths=5
        )  # price 2
        self.halo = VowFocusPickFactory(
            covenant_role=self.role, pick_level=3, name="Static Halo", value=2
        )
        self.ysolde = CharacterCovenantRoleFactory(
            covenant_role=self.role, character_sheet__character__db_key="Ysolde"
        )
        self.corvin = CharacterCovenantRoleFactory(
            covenant_role=self.role, character_sheet__character__db_key="Corvin"
        )
        CharacterVowFocusPickFactory(character_role=self.ysolde, pick=self.kneel)
        CharacterVowFocusPickFactory(character_role=self.corvin, pick=self.kneel)
        CharacterVowFocusPickFactory(character_role=self.corvin, pick=self.halo)

    def _by_name(self, impacts: list[live.HolderImpact]) -> dict[str, live.HolderImpact]:
        return {impact.holder_name: impact for impact in impacts}

    def test_an_unchanged_price_moves_nobody(self) -> None:
        self.assertEqual(live.holder_impact(self.role, {self.kneel.pk: 2}), [])

    def test_a_raise_within_budget_and_one_going_over(self) -> None:
        impacts = self._by_name(live.holder_impact(self.role, {self.kneel.pk: 3}))
        ysolde, corvin = impacts["Ysolde"], impacts["Corvin"]
        self.assertEqual((ysolde.level, ysolde.old_total, ysolde.new_total), (3, 2, 3))
        self.assertFalse(ysolde.over)
        self.assertEqual((corvin.old_total, corvin.new_total, corvin.budget), (4, 5, 4))
        self.assertTrue(corvin.over)

    def test_a_deleted_pick_refunds_its_price(self) -> None:
        impacts = self._by_name(live.holder_impact(self.role, {self.kneel.pk: None}))
        self.assertEqual((impacts["Corvin"].old_total, impacts["Corvin"].new_total), (4, 2))
        self.assertEqual(impacts["Ysolde"].new_total, 0)

    def test_a_holder_who_left_the_vow_is_not_counted(self) -> None:
        self.ysolde.left_at = timezone.now()
        self.ysolde.save(update_fields=["left_at"])
        impacts = self._by_name(live.holder_impact(self.role, {self.kneel.pk: 3}))
        self.assertEqual(set(impacts), {"Corvin"})
