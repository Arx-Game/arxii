"""Tests for the secondary-vow layer split in the magic power-term providers (#2641):

- Layer 1 (``covenant_role_blend_power_term``): PRIMARY-only, zero chassis leak.
- Layer 2 (``covenant_role_specialty_power_term``): potency-scaled secondary contribution.
- Layer 4 (``vow_situational_power_term``): potency-scaled secondary POWER_BONUS firing.

Built in ``setUp`` rather than ``setUpTestData`` — factories here create Evennia
``ObjectDB`` instances (``DbHolder``, not deepcopyable), the same rationale every
neighboring power-term test class documents.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    CovenantRoleTechniqueSpecialtyFactory,
    VowSituationalPerkFactory,
)
from world.covenants.models import SecondaryVowConfig
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
from world.covenants.services import secondary_vow_config
from world.magic.constants import TechniqueFunction
from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory, ThreadFactory
from world.magic.services.power_terms import (
    PowerTermContext,
    covenant_role_blend_power_term,
    covenant_role_specialty_power_term,
    vow_situational_power_term,
)
from world.traits.factories import ensure_level_ladder


class SecondaryVowBlendChassisIsolationTests(TestCase):
    """Layer 1: a secondary vow's blend weights never contribute (#2641)."""

    def setUp(self) -> None:
        ensure_level_ladder()
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def _ctx(self, technique):
        return PowerTermContext(sheet=self.sheet, technique=technique, applicable_threads=[])

    def _engage(self, *, sword=0, shield=0, crown=0, is_secondary=False):
        role = CovenantRoleFactory(
            sword_weight=Decimal(str(sword)),
            shield_weight=Decimal(str(shield)),
            crown_weight=Decimal(str(crown)),
        )
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
            is_secondary=is_secondary,
        )
        ThreadFactory(owner=self.sheet, level=110, as_covenant_role_thread=role)
        return role

    def test_secondary_blend_weight_never_contributes(self) -> None:
        self._engage(crown=Decimal("1.0"), is_secondary=False)
        technique = TechniqueFactory(archetype_alignment="crown")
        baseline = covenant_role_blend_power_term(self._ctx(technique))
        # level_width(11) = 8 on the standard ladder, the one vow thread's rung.
        self.assertEqual(baseline, 8)

        # A secondary vow with a big crown weight too — must not add anything.
        self._engage(crown=Decimal("1.0"), is_secondary=True)
        with_secondary = covenant_role_blend_power_term(self._ctx(technique))
        self.assertEqual(with_secondary, baseline)

    def test_only_secondary_engaged_contributes_zero(self) -> None:
        self._engage(crown=Decimal("1.0"), is_secondary=True)
        technique = TechniqueFactory(archetype_alignment="crown")
        self.assertEqual(covenant_role_blend_power_term(self._ctx(technique)), 0)


class SecondaryVowSpecialtyScalingTests(TestCase):
    """Layer 2: a secondary vow's specialty contribution is potency-scaled (#2641)."""

    def setUp(self) -> None:
        ensure_level_ladder()
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def _ctx(self, technique):
        return PowerTermContext(sheet=self.sheet, technique=technique, applicable_threads=[])

    def _engage(self, role, *, is_secondary):
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
            is_secondary=is_secondary,
        )
        ThreadFactory(owner=self.sheet, level=110, as_covenant_role_thread=role)

    def test_primary_unchanged_secondary_scaled_by_default_potency(self) -> None:
        primary_role = CovenantRoleFactory()
        secondary_role = CovenantRoleFactory()
        self._engage(primary_role, is_secondary=False)
        self._engage(secondary_role, is_secondary=True)
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=primary_role, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=secondary_role, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)

        # width(11)=8. primary: 8*10/10=8.0; secondary: 8.0 * potency 0.6 = 4.8
        # total = 12.8 -> int(12.8) = 12
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 12)

    def test_secondary_alone_scaled_and_primary_alone_unscaled(self) -> None:
        role = CovenantRoleFactory()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)

        self._engage(role, is_secondary=False)
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 8)

        # Swap: same role, but now engaged only as a secondary elsewhere.
        other_sheet_role = CovenantRoleFactory()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=other_sheet_role, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        character2 = CharacterFactory()
        sheet2 = CharacterSheetFactory(character=character2)
        ThreadFactory(owner=sheet2, level=110, as_covenant_role_thread=other_sheet_role)
        CharacterCovenantRoleFactory(
            character_sheet=sheet2,
            covenant=CovenantFactory(),
            covenant_role=other_sheet_role,
            engaged=True,
            is_secondary=True,
        )
        ctx2 = PowerTermContext(sheet=sheet2, technique=technique, applicable_threads=[])
        # 8*10/10=8.0 * potency 0.6 = 4.8 -> int(4.8) = 4
        self.assertEqual(covenant_role_specialty_power_term(ctx2), 4)

    def test_custom_potency_dial_scales_secondary_contribution(self) -> None:
        secondary_role = CovenantRoleFactory()
        self._engage(secondary_role, is_secondary=True)
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=secondary_role, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)

        config = secondary_vow_config()
        config.potency_tenths = 5
        config.save()

        # 8*10/10=8.0 * potency 0.5 = 4.0 -> int(4.0) = 4
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 4)
        self.assertEqual(SecondaryVowConfig.objects.get(pk=1).potency_tenths, 5)


class SecondaryVowSituationalPowerTermTests(TestCase):
    """Layer 4: a secondary vow's fired POWER_BONUS perk is potency-scaled (#2641)."""

    def setUp(self) -> None:
        ensure_level_ladder()
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def _ctx(self, technique):
        return PowerTermContext(sheet=self.sheet, technique=technique, applicable_threads=[])

    def _engage(self, role, *, is_secondary):
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
            is_secondary=is_secondary,
        )
        ThreadFactory(owner=self.sheet, level=110, as_covenant_role_thread=role)

    def test_secondary_power_bonus_firing_scaled_by_potency(self) -> None:
        primary_role = CovenantRoleFactory()
        secondary_role = CovenantRoleFactory()
        self._engage(primary_role, is_secondary=False)
        self._engage(secondary_role, is_secondary=True)
        VowSituationalPerkFactory(
            covenant_role=primary_role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=20,
        )
        VowSituationalPerkFactory(
            covenant_role=secondary_role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=20,
        )
        technique = TechniqueFactory()

        # width(11)=8. primary: 8*20/10=16.0; secondary: 16.0 * potency 0.6 = 9.6
        # total = 25.6 -> int(25.6) = 25
        self.assertEqual(vow_situational_power_term(self._ctx(technique)), 25)

    def test_primary_only_power_bonus_is_unscaled_baseline(self) -> None:
        primary_role = CovenantRoleFactory()
        self._engage(primary_role, is_secondary=False)
        VowSituationalPerkFactory(
            covenant_role=primary_role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=20,
        )
        technique = TechniqueFactory()

        self.assertEqual(vow_situational_power_term(self._ctx(technique)), 16)
