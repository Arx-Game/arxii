"""A payload row on a focus pick applies only to holders who chose it (#4806, slice 2 of #4759).

The cast seam is covered end to end in
``integration_tests.test_vow_focus_picks_in_combat_journeys``. These tests cover
the two seams a fight journey reaches only indirectly: situational perk
collection (``applicable_perks``) and action scaling
(``covenant_role_action_scaling_bonus``), plus the static added-effect view.

Built in ``setUp`` rather than ``setUpTestData``: the sheet factories create
Evennia ``ObjectDB`` rows, which ``setUpTestData``'s deepcopy cannot copy (same
rationale as ``test_perk_resolution.py``).
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.added_effects import vow_added_effects_on_technique
from world.covenants.constants import CovenantScaledAction, CovenantType
from world.covenants.factories import (
    CharacterVowFocusPickFactory,
    CovenantFactory,
    CovenantRoleActionScalingFactory,
    CovenantRoleFactory,
    VowAddedEffectFactory,
    VowFocusPickFactory,
    VowSituationalPerkFactory,
    engage_vow_with_thread,
)
from world.covenants.focus_picks import chosen_pick_ids_by_holder
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
from world.covenants.perks.services import applicable_perks
from world.covenants.services import covenant_role_action_scaling_bonus
from world.magic.constants import TechniqueFunction
from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory


class FocusPickFilterBase(TestCase):
    """Two holders of one vow at thread level 2; only the chooser chose the pick."""

    def setUp(self) -> None:
        self.covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        self.vow = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        self.pick = VowFocusPickFactory(covenant_role=self.vow, name="Steady Shield")
        self.chooser = CharacterSheetFactory()
        self.other = CharacterSheetFactory()
        chooser_vow = engage_vow_with_thread(
            self.chooser, self.vow, covenant=self.covenant, thread_level=2
        )
        engage_vow_with_thread(self.other, self.vow, covenant=self.covenant, thread_level=2)
        CharacterVowFocusPickFactory(character_role=chooser_vow, pick=self.pick)


class ChosenPickIdsTests(FocusPickFilterBase):
    def test_reads_each_holders_picks_in_one_query(self) -> None:
        with self.assertNumQueries(1):
            chosen = chosen_pick_ids_by_holder({self.chooser.pk, self.other.pk})
        self.assertEqual(chosen, {self.chooser.pk: {self.pick.pk}})

    def test_a_pick_on_a_vow_the_holder_left_does_not_count(self) -> None:
        membership = self.chooser.character.covenant_roles.active_memberships[0]
        membership.left_at = membership.joined_at
        membership.save()
        self.assertEqual(chosen_pick_ids_by_holder({self.chooser.pk}), {})


class PerkOnAFocusPickTests(FocusPickFilterBase):
    def setUp(self) -> None:
        super().setUp()
        self.base_perk = VowSituationalPerkFactory(
            covenant_role=self.vow,
            name="Base Resolve",
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
        )
        self.pick_perk = VowSituationalPerkFactory(
            covenant_role=self.vow,
            name="Shield Resolve",
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            focus_pick=self.pick,
        )

    def fired_perks(self, sheet: object) -> set[object]:
        fired = applicable_perks(
            sheet, effect_kind=PerkEffectKind.POWER_BONUS, resolution=None, target=None
        )
        return {firing.perk for firing in fired}

    def test_the_chooser_gets_the_pick_perk_and_the_base(self) -> None:
        self.assertEqual(self.fired_perks(self.chooser), {self.base_perk, self.pick_perk})

    def test_a_holder_without_the_pick_gets_only_the_base(self) -> None:
        self.assertEqual(self.fired_perks(self.other), {self.base_perk})


class ActionScalingOnAFocusPickTests(FocusPickFilterBase):
    def setUp(self) -> None:
        super().setUp()
        CovenantRoleActionScalingFactory(
            covenant_role=self.vow,
            action_key=CovenantScaledAction.INTERPOSE,
            thread_level_multiplier=Decimal("0.5"),
        )
        CovenantRoleActionScalingFactory(
            covenant_role=self.vow,
            action_key=CovenantScaledAction.INTERPOSE,
            thread_level_multiplier=Decimal("0.25"),
            focus_pick=self.pick,
        )

    def bonus(self, sheet: object) -> float:
        return covenant_role_action_scaling_bonus(sheet.character, CovenantScaledAction.INTERPOSE)

    def test_the_chooser_scales_by_the_base_and_the_pick(self) -> None:
        # Thread stored at 20: 20 x 0.5 + 20 x 0.25.
        self.assertEqual(self.bonus(self.chooser), 15.0)

    def test_a_holder_without_the_pick_scales_by_the_base_only(self) -> None:
        self.assertEqual(self.bonus(self.other), 10.0)


class AddedEffectViewOnAFocusPickTests(FocusPickFilterBase):
    def test_the_static_view_lists_a_pick_row_only_for_the_chooser(self) -> None:
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.HOLD)
        base = VowAddedEffectFactory(covenant_role=self.vow, function=TechniqueFunction.HOLD)
        on_pick = VowAddedEffectFactory(
            covenant_role=self.vow, function=TechniqueFunction.HOLD, focus_pick=self.pick
        )
        self.assertEqual(
            set(vow_added_effects_on_technique(self.chooser, technique)), {base, on_pick}
        )
        self.assertEqual(set(vow_added_effects_on_technique(self.other, technique)), {base})
