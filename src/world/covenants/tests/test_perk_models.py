"""Tests for the situational-perk authoring models (#2536, Task 1).

``VowSituationalPerk`` / ``VowSituationalPerkSituation`` /
``VowSituationalPerkRung`` — the vocabulary + schema slice of Layer 4 of the
vow-power model. No evaluator/resolution logic exists yet (Tasks 2-3); these
tests cover model shape only: uniqueness, sub-role validity, rung clean(),
and natural-key round-trips (extended in ``core_management/tests/test_content_export.py``).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.battles.constants import BattleActionKind
from world.checks.factories import CheckTypeFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkRungFactory,
    VowSituationalPerkSituationFactory,
)
from world.covenants.models import (
    VowSituationalPerk,
    VowSituationalPerkRung,
    VowSituationalPerkSituation,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
from world.missions.factories import MissionCategoryFactory, MissionTemplateFactory


class VowSituationalPerkModelTests(TestCase):
    def test_str_uses_role_name_and_perk_name(self) -> None:
        perk = VowSituationalPerkFactory(covenant_role__name="Vanguard", name="Scout's Instinct")
        self.assertEqual(str(perk), "Vanguard: Scout's Instinct")

    def test_default_magnitude_tenths_is_ten(self) -> None:
        perk = VowSituationalPerkFactory()
        self.assertEqual(perk.magnitude_tenths, 10)

    def test_unique_name_per_role(self) -> None:
        """The same perk name cannot be attached twice to the same role."""
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        VowSituationalPerkFactory(covenant_role=role, name="Scout's Instinct")

        with self.assertRaises(IntegrityError), transaction.atomic():
            VowSituationalPerk.objects.create(
                covenant_role=role,
                name="Scout's Instinct",
                beneficiary=PerkBeneficiary.SELF,
                effect_kind=PerkEffectKind.POWER_BONUS,
                announce_template="{holder} shines!",
            )

    def test_same_name_allowed_on_different_roles(self) -> None:
        """Uniqueness is scoped per-role, not global."""
        first = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        second = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        VowSituationalPerkFactory(covenant_role=first, name="Scout's Instinct")
        VowSituationalPerkFactory(covenant_role=second, name="Scout's Instinct")

        self.assertEqual(VowSituationalPerk.objects.filter(name="Scout's Instinct").count(), 2)

    def test_cascade_deletes_with_covenant_role(self) -> None:
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        VowSituationalPerkFactory(covenant_role=role)

        role.delete()

        self.assertEqual(VowSituationalPerk.objects.count(), 0)

    def test_valid_on_primary_role(self) -> None:
        """A perk row on a primary role's full_clean() passes."""
        role = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE, sword_weight=1, crown_weight=0
        )
        role.full_clean()  # sanity: primary role itself is valid

        perk = VowSituationalPerkFactory(covenant_role=role)
        perk.full_clean()

    def test_valid_on_sub_role(self) -> None:
        """A perk row on a valid sub-role full_clean()s cleanly.

        Sub-role: parent+resonance set, unlock_thread_level>0, zero blend
        weights (``CovenantRoleFactory`` defaults ``crown_weight=1``, zeroed
        here via ``SubroleCovenantRoleFactory``). Proves perk rows ADD on top
        of the anchor role rather than being restricted to primary roles.
        """
        parent = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        sub_role = SubroleCovenantRoleFactory(parent_role=parent, unlock_thread_level=3)
        sub_role.full_clean()  # sanity: the sub-role itself is valid

        perk = VowSituationalPerkFactory(covenant_role=sub_role)
        perk.full_clean()

    def test_check_type_null_means_any_check(self) -> None:
        perk = VowSituationalPerkFactory(effect_kind=PerkEffectKind.CHECK_BONUS)
        self.assertIsNone(perk.check_type)

    def test_check_type_scopes_check_bonus_perk(self) -> None:
        check_type = CheckTypeFactory(name="Perception")
        perk = VowSituationalPerkFactory(
            effect_kind=PerkEffectKind.CHECK_BONUS, check_type=check_type
        )
        self.assertEqual(perk.check_type, check_type)

    def test_check_type_set_null_on_delete(self) -> None:
        check_type = CheckTypeFactory(name="Perception")
        perk = VowSituationalPerkFactory(
            effect_kind=PerkEffectKind.CHECK_BONUS, check_type=check_type
        )
        perk_pk = perk.pk

        check_type.delete()

        # Collector-driven SET_NULL is a bulk UPDATE that bypasses per-instance
        # .save(), so the idmapper identity map never sees it — even a fresh
        # refresh_from_db() would return the same stale cached instance.
        # flush_instance_cache() forces the next .get() to hit the DB.
        VowSituationalPerk.flush_instance_cache()
        reloaded = VowSituationalPerk.objects.get(pk=perk_pk)
        self.assertIsNone(reloaded.check_type)

    def test_check_type_rejected_on_non_check_bonus_perk(self) -> None:
        """#2536 Task 5 content-authoring guard: check_type is only meaningful
        on a CHECK_BONUS perk — clean() rejects it on any other effect_kind."""
        check_type = CheckTypeFactory(name="Perception")
        perk = VowSituationalPerkFactory.build(
            effect_kind=PerkEffectKind.POWER_BONUS, check_type=check_type
        )
        with self.assertRaises(ValidationError) as ctx:
            perk.full_clean()
        self.assertIn("check_type", ctx.exception.message_dict)

    def test_check_type_allowed_on_check_bonus_perk_clean(self) -> None:
        """Sanity: the guard does not block the legitimate CHECK_BONUS+check_type
        pairing — full_clean() passes cleanly."""
        check_type = CheckTypeFactory(name="Perception")
        perk = VowSituationalPerkFactory(
            effect_kind=PerkEffectKind.CHECK_BONUS, check_type=check_type
        )
        perk.full_clean()

    def test_no_negative_magnitude(self) -> None:
        """PositiveIntegerField structurally forbids negative magnitudes."""
        perk = VowSituationalPerkFactory.build(magnitude_tenths=-5)
        with self.assertRaises(ValidationError):
            perk.full_clean()

    def test_tier_floor_requires_floor_success_level(self) -> None:
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        perk = VowSituationalPerkFactory.build(
            covenant_role=role,
            effect_kind=PerkEffectKind.TIER_FLOOR,
            floor_success_level=None,
        )
        with self.assertRaises(ValidationError):
            perk.full_clean()

    def test_floor_success_level_rejected_off_tier_floor(self) -> None:
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        perk = VowSituationalPerkFactory.build(
            covenant_role=role,
            effect_kind=PerkEffectKind.BOTCH_IMMUNITY,
            floor_success_level=1,
        )
        with self.assertRaises(ValidationError):
            perk.full_clean()

    def test_tier_floor_with_floor_is_valid(self) -> None:
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        perk = VowSituationalPerkFactory.build(
            covenant_role=role,
            effect_kind=PerkEffectKind.TIER_FLOOR,
            floor_success_level=1,
        )
        perk.full_clean()  # must not raise

    def test_mission_category_null_means_any_mission(self) -> None:
        perk = VowSituationalPerkFactory(effect_kind=PerkEffectKind.CHECK_BONUS)
        self.assertIsNone(perk.mission_category)
        self.assertIsNone(perk.mission_template)

    def test_mission_category_rejected_on_non_check_bonus_perk(self) -> None:
        """#2536 slice 3 content-authoring guard: mission_category/mission_template
        are only meaningful on a CHECK_BONUS perk — clean() rejects either on any
        other effect_kind."""
        category = MissionCategoryFactory()
        perk = VowSituationalPerkFactory.build(
            effect_kind=PerkEffectKind.POWER_BONUS, mission_category=category
        )
        with self.assertRaises(ValidationError) as ctx:
            perk.full_clean()
        self.assertIn("mission_category", ctx.exception.message_dict)

    def test_mission_template_rejected_on_non_check_bonus_perk(self) -> None:
        template = MissionTemplateFactory()
        perk = VowSituationalPerkFactory.build(
            effect_kind=PerkEffectKind.TIER_FLOOR,
            floor_success_level=1,
            mission_template=template,
        )
        with self.assertRaises(ValidationError) as ctx:
            perk.full_clean()
        self.assertIn("mission_template", ctx.exception.message_dict)

    def test_mission_category_allowed_on_check_bonus_perk_clean(self) -> None:
        """Sanity: the guard does not block the legitimate CHECK_BONUS+mission
        scope pairing — full_clean() passes cleanly."""
        category = MissionCategoryFactory()
        perk = VowSituationalPerkFactory(
            effect_kind=PerkEffectKind.CHECK_BONUS, mission_category=category
        )
        perk.full_clean()

    def test_battle_action_kind_rejected_on_tier_floor_perk(self) -> None:
        """#2536 slice 3 content-authoring guard: battle_action_kind is only
        meaningful on CHECK_BONUS/POWER_BONUS perks — clean() rejects it on
        TIER_FLOOR (and BOTCH_IMMUNITY)."""
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        perk = VowSituationalPerkFactory.build(
            covenant_role=role,
            effect_kind=PerkEffectKind.TIER_FLOOR,
            floor_success_level=1,
            battle_action_kind=BattleActionKind.ROUT,
        )
        with self.assertRaises(ValidationError) as ctx:
            perk.full_clean()
        self.assertIn("battle_action_kind", ctx.exception.message_dict)

    def test_battle_action_kind_allowed_on_power_bonus_perk_clean(self) -> None:
        """Spec §4: Battle scopes both kinds — battle_action_kind is valid on
        POWER_BONUS perks (not just CHECK_BONUS)."""
        perk = VowSituationalPerkFactory(
            effect_kind=PerkEffectKind.POWER_BONUS,
            battle_action_kind=BattleActionKind.ROUT,
        )
        perk.full_clean()

    def test_battle_action_kind_allowed_on_check_bonus_perk_clean(self) -> None:
        perk = VowSituationalPerkFactory(
            effect_kind=PerkEffectKind.CHECK_BONUS,
            battle_action_kind=BattleActionKind.ROUT,
        )
        perk.full_clean()


class VowSituationalPerkSituationModelTests(TestCase):
    def test_str_uses_perk_name_and_situation_display(self) -> None:
        perk = VowSituationalPerkFactory(name="Scout's Instinct")
        situation = VowSituationalPerkSituationFactory(perk=perk, situation=Situation.AT_RANGE)
        self.assertEqual(str(situation), "Scout's Instinct: At Range")

    def test_unique_situation_per_perk(self) -> None:
        perk = VowSituationalPerkFactory()
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.AT_RANGE)

        with self.assertRaises(IntegrityError), transaction.atomic():
            VowSituationalPerkSituation.objects.create(perk=perk, situation=Situation.AT_RANGE)

    def test_multiple_situations_and_composed(self) -> None:
        """A perk may carry several situations — resolution ANDs them (Task 3)."""
        perk = VowSituationalPerkFactory()
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.AT_RANGE)
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.TARGET_DISTRACTED)

        self.assertEqual(perk.situations.count(), 2)
        situations = set(perk.situations.values_list("situation", flat=True))
        self.assertEqual(situations, {Situation.AT_RANGE, Situation.TARGET_DISTRACTED})

    def test_cascade_deletes_with_perk(self) -> None:
        perk = VowSituationalPerkFactory()
        VowSituationalPerkSituationFactory(perk=perk)

        perk.delete()

        self.assertEqual(VowSituationalPerkSituation.objects.count(), 0)


class VowSituationalPerkRungModelTests(TestCase):
    def test_str_uses_perk_name_rung_number_and_situation_display(self) -> None:
        perk = VowSituationalPerkFactory(name="Last Bulwark")
        rung = VowSituationalPerkRungFactory(
            perk=perk, rung_number=1, extra_situation=Situation.ALLY_LOW_HEALTH
        )
        self.assertEqual(str(rung), "Last Bulwark rung 1: Ally Low Health")

    def test_unique_rung_number_per_perk(self) -> None:
        perk = VowSituationalPerkFactory()
        VowSituationalPerkRungFactory(perk=perk, rung_number=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            VowSituationalPerkRung.objects.create(
                perk=perk,
                rung_number=1,
                extra_situation=Situation.ALLY_LOW_HEALTH,
                magnitude_tenths=20,
            )

    def test_same_rung_number_allowed_on_different_perks(self) -> None:
        first = VowSituationalPerkFactory()
        second = VowSituationalPerkFactory()
        VowSituationalPerkRungFactory(perk=first, rung_number=1)
        VowSituationalPerkRungFactory(perk=second, rung_number=1)

        self.assertEqual(VowSituationalPerkRung.objects.filter(rung_number=1).count(), 2)

    def test_clean_rejects_rung_number_zero(self) -> None:
        rung = VowSituationalPerkRungFactory.build(perk=VowSituationalPerkFactory(), rung_number=0)
        with self.assertRaises(ValidationError):
            rung.clean()

    def test_clean_accepts_rung_number_one(self) -> None:
        rung = VowSituationalPerkRungFactory.build(perk=VowSituationalPerkFactory(), rung_number=1)
        rung.clean()  # does not raise

    def test_clean_does_not_enforce_contiguity(self) -> None:
        """Rung numbers may skip — resolution walks whatever rungs exist (spec)."""
        perk = VowSituationalPerkFactory()
        VowSituationalPerkRungFactory(perk=perk, rung_number=1)
        rung_three = VowSituationalPerkRungFactory(perk=perk, rung_number=3)
        rung_three.full_clean()  # does not raise despite the gap at rung 2

    def test_cascade_deletes_with_perk(self) -> None:
        perk = VowSituationalPerkFactory()
        VowSituationalPerkRungFactory(perk=perk)

        perk.delete()

        self.assertEqual(VowSituationalPerkRung.objects.count(), 0)
