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


class SecondaryVowBlendChassisIsolationTests(TestCase):
    """Layer 1: a secondary vow's blend weights never contribute (#2641)."""

    def setUp(self) -> None:
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
        return role

    def test_secondary_blend_weight_never_contributes(self) -> None:
        ThreadFactory(owner=self.sheet, level=10)
        self._engage(crown=Decimal("1.0"), is_secondary=False)
        technique = TechniqueFactory(archetype_alignment="crown")
        baseline = covenant_role_blend_power_term(self._ctx(technique))
        self.assertEqual(baseline, 10)

        # A secondary vow with a big crown weight too — must not add anything.
        self._engage(crown=Decimal("1.0"), is_secondary=True)
        with_secondary = covenant_role_blend_power_term(self._ctx(technique))
        self.assertEqual(with_secondary, baseline)

    def test_only_secondary_engaged_contributes_zero(self) -> None:
        ThreadFactory(owner=self.sheet, level=10)
        self._engage(crown=Decimal("1.0"), is_secondary=True)
        technique = TechniqueFactory(archetype_alignment="crown")
        self.assertEqual(covenant_role_blend_power_term(self._ctx(technique)), 0)


class SecondaryVowSpecialtyScalingTests(TestCase):
    """Layer 2: a secondary vow's specialty contribution is potency-scaled (#2641)."""

    def setUp(self) -> None:
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

    def test_primary_unchanged_secondary_scaled_by_default_potency(self) -> None:
        ThreadFactory(owner=self.sheet, level=10)  # total_threads = 10
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

        # primary: 10*10/10=10.0; secondary: 10*10/10=10.0 * potency 0.6 = 6.0
        # total = 16.0 -> int(16.0) = 16
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 16)

    def test_secondary_alone_scaled_and_primary_alone_unscaled(self) -> None:
        ThreadFactory(owner=self.sheet, level=10)
        role = CovenantRoleFactory()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)

        self._engage(role, is_secondary=False)
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 10)

        # Swap: same role, but now engaged only as a secondary elsewhere.
        other_sheet_role = CovenantRoleFactory()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=other_sheet_role, function=TechniqueFunction.WEAKEN, multiplier_tenths=10
        )
        character2 = CharacterFactory()
        sheet2 = CharacterSheetFactory(character=character2)
        ThreadFactory(owner=sheet2, level=10)
        CharacterCovenantRoleFactory(
            character_sheet=sheet2,
            covenant=CovenantFactory(),
            covenant_role=other_sheet_role,
            engaged=True,
            is_secondary=True,
        )
        ctx2 = PowerTermContext(sheet=sheet2, technique=technique, applicable_threads=[])
        # 10*10/10=10.0 * potency 0.6 = 6.0 -> int(6.0) = 6
        self.assertEqual(covenant_role_specialty_power_term(ctx2), 6)

    def test_custom_potency_dial_scales_secondary_contribution(self) -> None:
        ThreadFactory(owner=self.sheet, level=10)
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

        # 10*10/10=10.0 * potency 0.5 = 5.0 -> int(5.0) = 5
        self.assertEqual(covenant_role_specialty_power_term(self._ctx(technique)), 5)
        self.assertEqual(SecondaryVowConfig.objects.get(pk=1).potency_tenths, 5)


class SecondaryVowSituationalPowerTermTests(TestCase):
    """Layer 4: a secondary vow's fired POWER_BONUS perk is potency-scaled (#2641)."""

    def setUp(self) -> None:
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

    def test_secondary_power_bonus_firing_scaled_by_potency(self) -> None:
        ThreadFactory(owner=self.sheet, level=10)  # total_threads = 10
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

        # primary: 10*20/10=20.0; secondary: 10*20/10=20.0 * potency 0.6 = 12.0
        # total = 32.0 -> int(32.0) = 32
        self.assertEqual(vow_situational_power_term(self._ctx(technique)), 32)

    def test_primary_only_power_bonus_is_unscaled_baseline(self) -> None:
        ThreadFactory(owner=self.sheet, level=10)
        primary_role = CovenantRoleFactory()
        self._engage(primary_role, is_secondary=False)
        VowSituationalPerkFactory(
            covenant_role=primary_role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.POWER_BONUS,
            magnitude_tenths=20,
        )
        technique = TechniqueFactory()

        self.assertEqual(vow_situational_power_term(self._ctx(technique)), 20)
