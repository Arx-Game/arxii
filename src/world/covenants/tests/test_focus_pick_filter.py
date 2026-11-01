"""A payload row on a focus pick applies only to holders who chose it (#4806, slice 2 of #4759).

The cast seam is covered end to end in
``integration_tests.test_vow_focus_picks_in_combat_journeys``. These tests cover
the two seams a fight journey reaches only indirectly: situational perk
collection (``applicable_perks``) and vow stat scaling
(``vow_stat_scaling_bonus``), plus the static added-effect view.

Built in ``setUp`` rather than ``setUpTestData``: the sheet factories create
Evennia ``ObjectDB`` rows, which ``setUpTestData``'s deepcopy cannot copy (same
rationale as ``test_perk_resolution.py``).
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.added_effects import vow_added_effects_on_technique
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterVowFocusPickFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowAddedEffectFactory,
    VowFocusPickFactory,
    VowSituationalPerkFactory,
    VowStatScalingFactory,
    engage_vow_with_thread,
)
from world.covenants.focus_picks import chosen_pick_ids_by_holder
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
from world.covenants.perks.services import applicable_perks
from world.magic.constants import TechniqueFunction
from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, ManeuverEffectKey
from world.mechanics.effect_targets import effect_value
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect
from world.mechanics.models import ModifierCategory
from world.mechanics.services import vow_stat_scaling_bonus


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


class VowStatScalingOnAFocusPickTests(FocusPickFilterBase):
    """Thread level 2 shows as 2 and is stored as 20 (stored = shown x 10)."""

    def setUp(self) -> None:
        super().setUp()
        ensure_maneuver_effects()
        self.effect_target = ModifierTargetFactory(
            category=ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME),
            name="Interpose protection vow",
            scope_maneuver_effect=get_maneuver_effect(
                ManeuverEffectKey.INTERPOSE_PARTIAL_PROTECTION
            ),
        )
        VowStatScalingFactory(
            covenant_role=self.vow, modifier_target=self.effect_target, bonus_per_level=2
        )
        VowStatScalingFactory(
            covenant_role=self.vow,
            modifier_target=self.effect_target,
            bonus_per_level=3,
            focus_pick=self.pick,
        )
        self.base_value = effect_value(None, ManeuverEffectKey.INTERPOSE_PARTIAL_PROTECTION)

    def test_the_chooser_scales_by_the_base_and_the_pick(self) -> None:
        # The shown level 2 counts on a maneuver effect: 2 x 2 + 2 x 3.
        self.assertEqual(vow_stat_scaling_bonus(self.chooser, self.effect_target), 10)
        self.assertEqual(
            effect_value(self.chooser, ManeuverEffectKey.INTERPOSE_PARTIAL_PROTECTION),
            self.base_value + 10,
        )

    def test_a_holder_without_the_pick_scales_by_the_base_only(self) -> None:
        self.assertEqual(vow_stat_scaling_bonus(self.other, self.effect_target), 4)
        self.assertEqual(
            effect_value(self.other, ManeuverEffectKey.INTERPOSE_PARTIAL_PROTECTION),
            self.base_value + 4,
        )

    def test_a_pick_row_on_a_stat_target_reaches_only_the_chooser(self) -> None:
        stat_target = ModifierTargetFactory(
            category=ModifierCategoryFactory(name="stat"), name="Pick stat"
        )
        VowStatScalingFactory(
            covenant_role=self.vow,
            modifier_target=stat_target,
            bonus_per_level=3,
            focus_pick=self.pick,
        )
        # A stat target counts the stored level: 20 x 3.
        self.assertEqual(vow_stat_scaling_bonus(self.chooser, stat_target), 60)
        self.assertEqual(vow_stat_scaling_bonus(self.other, stat_target), 0)


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
