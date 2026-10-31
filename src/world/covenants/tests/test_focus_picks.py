"""Vow focus pick prices and the rules a character's choice must pass (#4759 slice 1)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from evennia.accounts.models import AccountDB

from world.covenants.constants import FocusPickLimitKind
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CharacterVowFocusPickFactory,
    CovenantFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    VowAddedEffectFactory,
    VowFocusPickConfigFactory,
    VowFocusPickFactory,
    VowFocusPickLimitFactory,
    VowFocusPickReductionLimitFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkSituationFactory,
    VowStatScalingFactory,
)
from world.covenants.focus_picks import pick_price
from world.covenants.models import CharacterVowFocusPick, VowFocusPickLimit
from world.covenants.perks.constants import Situation
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory
from world.mechanics.factories import PropertyFactory


class PickPriceTests(TestCase):
    """price = max(1, floor(value x product(frequency/10)) - sum(reduction))."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.role = CovenantRoleFactory()

    def test_value_four_with_no_limit_costs_four(self) -> None:
        pick = VowFocusPickFactory(covenant_role=self.role, value=4)
        self.assertEqual(pick_price(pick), 4)

    def test_value_four_with_a_target_limit_at_five_costs_two(self) -> None:
        pick = VowFocusPickFactory(covenant_role=self.role, value=4)
        VowFocusPickLimitFactory(pick=pick, kind=FocusPickLimitKind.TARGET, frequency_tenths=5)
        self.assertEqual(pick_price(pick), 2)

    def test_frequencies_multiply_and_floor(self) -> None:
        # 5 x 0.6 x 0.5 = 1.5, floored to 1.
        pick = VowFocusPickFactory(covenant_role=self.role, value=5)
        VowFocusPickLimitFactory(pick=pick, kind=FocusPickLimitKind.TARGET, frequency_tenths=6)
        VowFocusPickLimitFactory(pick=pick, kind=FocusPickLimitKind.TIMING, frequency_tenths=5)
        self.assertEqual(pick_price(pick), 1)

    def test_a_cost_limit_takes_its_reduction_off(self) -> None:
        pick = VowFocusPickFactory(covenant_role=self.role, value=6)
        VowFocusPickLimitFactory(pick=pick, kind=FocusPickLimitKind.SETTING, frequency_tenths=5)
        VowFocusPickReductionLimitFactory(pick=pick, kind=FocusPickLimitKind.EXPOSURE, reduction=1)
        self.assertEqual(pick_price(pick), 2)

    def test_price_never_falls_below_one(self) -> None:
        pick = VowFocusPickFactory(covenant_role=self.role, value=4)
        VowFocusPickLimitFactory(pick=pick, kind=FocusPickLimitKind.TARGET, frequency_tenths=3)
        VowFocusPickReductionLimitFactory(pick=pick, reduction=5)
        self.assertEqual(pick_price(pick), 1)


class FocusPickLimitCleanTests(TestCase):
    """A limit refuses the column its kind does not read, so no limit is ignored."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.pick = VowFocusPickFactory()

    def test_a_reduction_on_a_frequency_limit_is_refused(self) -> None:
        limit = VowFocusPickLimit(pick=self.pick, kind=FocusPickLimitKind.TARGET, reduction=1)
        with self.assertRaises(ValidationError) as caught:
            limit.full_clean()
        self.assertIn("reduction", caught.exception.message_dict)

    def test_a_frequency_on_a_cost_limit_is_refused(self) -> None:
        limit = VowFocusPickLimit(pick=self.pick, kind=FocusPickLimitKind.COST, frequency_tenths=5)
        with self.assertRaises(ValidationError) as caught:
            limit.full_clean()
        self.assertIn("frequency_tenths", caught.exception.message_dict)


class PayloadFocusPickRoleTests(TestCase):
    """A payload row may only point at a pick on its own role."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.role = CovenantRoleFactory()
        cls.other_pick = VowFocusPickFactory(covenant_role=CovenantRoleFactory())
        cls.own_pick = VowFocusPickFactory(covenant_role=cls.role)

    def test_an_added_effect_with_another_roles_pick_is_refused(self) -> None:
        effect = VowAddedEffectFactory.build(covenant_role=self.role, focus_pick=self.other_pick)
        with self.assertRaises(ValidationError) as caught:
            effect.clean()
        self.assertIn("focus_pick", caught.exception.message_dict)

    def test_a_perk_with_another_roles_pick_is_refused(self) -> None:
        perk = VowSituationalPerkFactory.build(covenant_role=self.role, focus_pick=self.other_pick)
        with self.assertRaises(ValidationError) as caught:
            perk.clean()
        self.assertIn("focus_pick", caught.exception.message_dict)

    def test_a_stat_scaling_with_another_roles_pick_is_refused(self) -> None:
        scaling = VowStatScalingFactory.build(covenant_role=self.role, focus_pick=self.other_pick)
        with self.assertRaises(ValidationError) as caught:
            scaling.clean()
        self.assertIn("focus_pick", caught.exception.message_dict)

    def test_a_pick_row_may_share_a_base_rows_scope(self) -> None:
        VowAddedEffectFactory(covenant_role=self.role)
        picked = VowAddedEffectFactory(covenant_role=self.role, focus_pick=self.own_pick)
        picked.full_clean()

    def test_a_stat_scaling_pick_row_may_share_a_base_rows_target(self) -> None:
        base = VowStatScalingFactory(covenant_role=self.role)
        picked = VowStatScalingFactory.build(
            covenant_role=self.role,
            modifier_target=base.modifier_target,
            focus_pick=self.own_pick,
        )
        base.full_clean()
        picked.full_clean()
        picked.save()
        duplicate = VowStatScalingFactory.build(
            covenant_role=self.role, modifier_target=base.modifier_target
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()


class PropertySituationTests(TestCase):
    """The condition-property situations require a property; low health takes a percent."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.perk = VowSituationalPerkFactory()
        cls.indulgence = PropertyFactory(name="indulgence-4805")

    def test_property_situation_without_a_property_is_refused(self) -> None:
        row = VowSituationalPerkSituationFactory.build(
            perk=self.perk, situation=Situation.TARGET_HAS_CONDITION_PROPERTY
        )
        with self.assertRaises(ValidationError) as caught:
            row.clean()
        self.assertIn("condition_property", caught.exception.message_dict)

    def test_property_situation_with_a_property_and_count_is_accepted(self) -> None:
        row = VowSituationalPerkSituationFactory.build(
            perk=self.perk,
            situation=Situation.ENEMIES_WITH_CONDITION_PROPERTY_NEARBY,
            condition_property=self.indulgence,
            count_threshold=2,
        )
        row.clean()
        self.assertEqual(row.params.condition_property, self.indulgence)

    def test_a_property_on_another_situation_is_refused(self) -> None:
        row = VowSituationalPerkSituationFactory.build(
            perk=self.perk,
            situation=Situation.TARGET_LOW_HEALTH,
            condition_property=self.indulgence,
            threshold_percent=25,
        )
        with self.assertRaises(ValidationError) as caught:
            row.clean()
        self.assertIn("condition_property", caught.exception.message_dict)


class CharacterFocusPickValidationTests(TestCase):
    """CharacterVowFocusPick.clean() refuses each broken rule, with the reason."""

    @classmethod
    def setUpTestData(cls) -> None:
        VowFocusPickConfigFactory(budget_per_level=4)
        cls.resonance = ResonanceFactory()
        cls.role = CovenantRoleFactory()
        cls.covenant = CovenantFactory(covenant_type=cls.role.covenant_type)
        cls.membership = CharacterCovenantRoleFactory(
            covenant=cls.covenant, covenant_role=cls.role, engaged=True
        )
        # Shown vow level 1 (stored x10).
        ThreadFactory(
            owner=cls.membership.character_sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=cls.role,
            target_trait=None,
            level=10,
        )
        cls.level_one = VowFocusPickFactory(covenant_role=cls.role, pick_level=1, value=4)
        cls.second_level_one = VowFocusPickFactory(covenant_role=cls.role, pick_level=1, value=4)
        cls.level_two = VowFocusPickFactory(covenant_role=cls.role, pick_level=2, value=4)
        cls.other_vow_pick = VowFocusPickFactory(covenant_role=CovenantRoleFactory(), pick_level=1)

    def _clean(self, pick, membership=None) -> None:
        CharacterVowFocusPick(character_role=membership or self.membership, pick=pick).full_clean()

    def test_a_level_one_pick_at_vow_level_one_is_accepted(self) -> None:
        self._clean(self.level_one)

    def test_a_level_two_pick_at_vow_level_one_is_refused(self) -> None:
        with self.assertRaisesMessage(ValidationError, "level 2 pick"):
            self._clean(self.level_two)

    def test_a_second_level_one_pick_past_the_budget_is_refused(self) -> None:
        CharacterVowFocusPickFactory(character_role=self.membership, pick=self.level_one)
        with self.assertRaisesMessage(ValidationError, "already spent 4 of the 4 points"):
            self._clean(self.second_level_one)

    def test_two_limited_picks_fit_one_budget(self) -> None:
        for pick in (self.level_one, self.second_level_one):
            VowFocusPickLimitFactory(pick=pick, kind=FocusPickLimitKind.TARGET, frequency_tenths=5)
        CharacterVowFocusPickFactory(character_role=self.membership, pick=self.level_one)
        self._clean(self.second_level_one)

    def test_a_pick_from_another_vow_is_refused(self) -> None:
        with self.assertRaisesMessage(ValidationError, "not this character's vow"):
            self._clean(self.other_vow_pick)

    def test_a_secondary_vow_gets_no_picks(self) -> None:
        secondary = CharacterCovenantRoleFactory(
            covenant=CovenantFactory(covenant_type=self.role.covenant_type),
            covenant_role=self.role,
            is_secondary=True,
        )
        with self.assertRaisesMessage(ValidationError, "secondary vow"):
            self._clean(self.level_one, membership=secondary)


class SubRoleFocusPickTests(TestCase):
    """A sub-role holder chooses from the anchor vow's catalog and the sub-role's own."""

    @classmethod
    def setUpTestData(cls) -> None:
        VowFocusPickConfigFactory(budget_per_level=8)
        cls.resonance = ResonanceFactory()
        cls.anchor = CovenantRoleFactory()
        cls.sub_role = SubroleCovenantRoleFactory(
            parent_role=cls.anchor, resonance=cls.resonance, unlock_thread_level=1
        )
        cls.anchor_pick = VowFocusPickFactory(covenant_role=cls.anchor, pick_level=1)
        cls.sub_role_pick = VowFocusPickFactory(covenant_role=cls.sub_role, pick_level=1)

    def _membership(self, role):
        membership = CharacterCovenantRoleFactory(
            covenant=CovenantFactory(covenant_type=self.anchor.covenant_type),
            covenant_role=role,
            engaged=True,
        )
        ThreadFactory(
            owner=membership.character_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=self.anchor,
            target_trait=None,
            level=10,
        )
        return membership

    def test_a_sub_role_membership_takes_the_anchor_vows_pick(self) -> None:
        membership = self._membership(self.sub_role)
        CharacterVowFocusPick(character_role=membership, pick=self.anchor_pick).full_clean()

    def test_an_anchor_holder_grown_into_the_sub_role_takes_its_pick(self) -> None:
        membership = self._membership(self.anchor)
        CharacterVowFocusPick(character_role=membership, pick=self.sub_role_pick).full_clean()


class CovenantRoleAdminFocusPickTests(TestCase):
    """The CovenantRole page lists the vow's picks with their computed prices."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser("pickstaff", "ps@example.com", "pw-123456")
        cls.role = CovenantRoleFactory(name="Pick Vow")
        VowFocusPickFactory(covenant_role=cls.role, name="Open Hand", value=4)
        limited = VowFocusPickFactory(covenant_role=cls.role, name="Held Strike", value=4)
        VowFocusPickLimitFactory(pick=limited, kind=FocusPickLimitKind.TARGET, frequency_tenths=5)

    def test_change_page_shows_each_pick_and_its_price(self) -> None:
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:arxii_covenantrole_change", args=[self.role.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Open Hand", content)
        self.assertIn("Held Strike", content)
        self.assertInHTML('<td class="field-price"><p>2</p></td>', content)
        self.assertInHTML('<td class="field-price"><p>4</p></td>', content)


class CharacterFocusPickAdminTests(TestCase):
    """Staff setting a character's pick in the admin see a refused save's reason."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountDB.objects.create_superuser("pickstaff2", "p2@example.com", "pw-123456")
        VowFocusPickConfigFactory(budget_per_level=4)
        cls.role = CovenantRoleFactory()
        cls.membership = CharacterCovenantRoleFactory(
            covenant=CovenantFactory(covenant_type=cls.role.covenant_type),
            covenant_role=cls.role,
            engaged=True,
        )
        ThreadFactory(
            owner=cls.membership.character_sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=cls.role,
            target_trait=None,
            level=10,
        )
        cls.level_one = VowFocusPickFactory(covenant_role=cls.role, pick_level=1)
        cls.level_two = VowFocusPickFactory(covenant_role=cls.role, pick_level=2)

    def _post(self, pick):
        self.client.force_login(self.staff)
        return self.client.post(
            reverse("admin:arxii_charactervowfocuspick_add"),
            {"character_role": str(self.membership.pk), "pick": str(pick.pk)},
        )

    def test_a_level_two_pick_is_refused_with_the_reason(self) -> None:
        response = self._post(self.level_two)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is a level 2 pick")
        self.assertFalse(CharacterVowFocusPick.objects.filter(pick=self.level_two).exists())

    def test_a_level_one_pick_saves(self) -> None:
        response = self._post(self.level_one)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            CharacterVowFocusPick.objects.filter(
                character_role=self.membership, pick=self.level_one
            ).exists()
        )
