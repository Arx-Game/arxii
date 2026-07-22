"""Tests for the Sphinx of Black Quartz — vow-suitability oracle (#2640).

``judge_vow`` re-runs the kit∩demand join ``covenant_role_specialty_power_term``
already uses, but as a report; ``audit_vow_coverage`` runs the same join across the
whole catalog. Both are pure reads — nothing here writes.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import SphinxTier
from world.covenants.factories import (
    CovenantRoleFactory,
    CovenantRoleTechniqueSpecialtyFactory,
    SubroleCovenantRoleFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkSituationFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, Situation
from world.covenants.sphinx import audit_vow_coverage, judge_vow
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterTechniqueFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)


class JudgeVowUnauthoredRoleTests(TestCase):
    """An unauthored vow makes no demands and cannot reject (#2640 v1 rule)."""

    def test_unauthored_role_takes_with_no_demands(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()

        verdict = judge_vow(sheet, role)

        self.assertEqual(verdict.tier, SphinxTier.TAKES)
        self.assertEqual(verdict.demands, [])
        self.assertEqual(verdict.shopping_list, [])
        self.assertEqual(verdict.role_name, role.name)


class JudgeVowFullCoverageTests(TestCase):
    """Every specialty demand covered -> TAKES, naming the qualifying technique."""

    def test_full_coverage_takes_and_names_technique(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.WEAKEN)

        technique = TechniqueFactory(name="Sundering Blow")
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        CharacterTechniqueFactory(character=sheet, technique=technique)

        verdict = judge_vow(sheet, role)

        self.assertEqual(verdict.tier, SphinxTier.TAKES)
        self.assertEqual(len(verdict.demands), 1)
        demand = verdict.demands[0]
        self.assertEqual(demand.function, TechniqueFunction.WEAKEN)
        self.assertEqual(demand.source, "specialty")
        self.assertTrue(demand.covered)
        self.assertIn("Sundering Blow", demand.qualifying_technique_names)
        self.assertEqual(verdict.shopping_list, [])


class JudgeVowPartialCoverageTests(TestCase):
    """One covered, one not -> DORMANT, naming the uncovered demand."""

    def test_partial_coverage_is_dormant(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.WEAKEN)
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.CHARM)

        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        CharacterTechniqueFactory(character=sheet, technique=technique)

        verdict = judge_vow(sheet, role)

        self.assertEqual(verdict.tier, SphinxTier.DORMANT)
        by_function = {demand.function: demand for demand in verdict.demands}
        self.assertTrue(by_function[TechniqueFunction.WEAKEN].covered)
        self.assertFalse(by_function[TechniqueFunction.CHARM].covered)
        self.assertEqual(by_function[TechniqueFunction.CHARM].qualifying_technique_names, [])


class JudgeVowNoCoverageTests(TestCase):
    """Zero demands covered -> NOT_YET, with a shopping list."""

    def test_no_coverage_is_not_yet_with_shopping_list(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.BARRIER
        )

        # A learnable technique the character doesn't yet know, carrying the demanded tag.
        learnable = TechniqueFactory(name="Ward of Black Quartz")
        TechniqueFunctionTagFactory(technique=learnable, function=TechniqueFunction.BARRIER)

        verdict = judge_vow(sheet, role)

        self.assertEqual(verdict.tier, SphinxTier.NOT_YET)
        self.assertEqual(len(verdict.demands), 1)
        self.assertFalse(verdict.demands[0].covered)
        shopping_names = [item.technique_name for item in verdict.shopping_list]
        self.assertIn("Ward of Black Quartz", shopping_names)
        for item in verdict.shopping_list:
            self.assertEqual(item.function, TechniqueFunction.BARRIER)


class JudgeVowSituationDemandTests(TestCase):
    """A SELF-beneficiary perk's in-mapping situation demands a creator function."""

    def test_situation_demand_covered_via_creator_function(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        perk = VowSituationalPerkFactory(
            covenant_role=role, name="Sway the Room", beneficiary=PerkBeneficiary.SELF
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.TARGET_DISTRACTED)

        # CHARM is in TARGET_DISTRACTED's creator set.
        technique = TechniqueFactory(name="Beguiling Word")
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.CHARM)
        CharacterTechniqueFactory(character=sheet, technique=technique)

        verdict = judge_vow(sheet, role)

        self.assertEqual(verdict.tier, SphinxTier.TAKES)
        self.assertEqual(len(verdict.demands), 1)
        demand = verdict.demands[0]
        self.assertEqual(demand.function, Situation.TARGET_DISTRACTED)
        self.assertEqual(demand.source, "Sway the Room")
        self.assertTrue(demand.covered)
        self.assertIn("Beguiling Word", demand.qualifying_technique_names)

    def test_situation_absent_from_mapping_demands_nothing(self) -> None:
        """A positional/encounter situation (not in SITUATION_CREATOR_FUNCTIONS) is inert."""
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        perk = VowSituationalPerkFactory(
            covenant_role=role, name="Battle Instinct", beneficiary=PerkBeneficiary.SELF
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.AT_RANGE)

        verdict = judge_vow(sheet, role)

        self.assertEqual(verdict.tier, SphinxTier.TAKES)
        self.assertEqual(verdict.demands, [])

    def test_non_self_beneficiary_perk_is_not_judged(self) -> None:
        """COVENANT_ALLIES/WHOLE_GROUP perks describe what OTHERS get, not this holder's kit."""
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            name="Rally the Line",
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
        )
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.TARGET_DISTRACTED)

        verdict = judge_vow(sheet, role)

        self.assertEqual(verdict.tier, SphinxTier.TAKES)
        self.assertEqual(verdict.demands, [])


class JudgeVowSubRoleTests(TestCase):
    """Sub-role judgment ADDs the parent's specialty rows (mirrors the power term)."""

    def test_sub_role_includes_parent_specialty_rows(self) -> None:
        sheet = CharacterSheetFactory()
        parent = CovenantRoleFactory()
        sub_role = SubroleCovenantRoleFactory(parent_role=parent)
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=parent, function=TechniqueFunction.WEAKEN
        )

        technique = TechniqueFactory(name="Sundering Blow")
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        CharacterTechniqueFactory(character=sheet, technique=technique)

        verdict = judge_vow(sheet, sub_role)

        self.assertEqual(verdict.tier, SphinxTier.TAKES)
        self.assertEqual(len(verdict.demands), 1)
        self.assertEqual(verdict.demands[0].source, "specialty")
        self.assertTrue(verdict.demands[0].covered)


class AuditVowCoverageTests(TestCase):
    """The staff catalog-wide coverage audit: specialty demands only."""

    def test_full_pool_covers_role_fully(self) -> None:
        role = CovenantRoleFactory(name="Vanguard")
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.WEAKEN)

        tradition = TraditionFactory(name="The Sundering Path")
        grant = TraditionGiftGrantFactory(tradition=tradition)
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        grant.signature_techniques.set([technique])

        rows = audit_vow_coverage()

        matching = [
            row
            for row in rows
            if row.role_name == "Vanguard" and row.tradition_name == "The Sundering Path"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].coverage, "full")
        self.assertEqual(matching[0].missing_functions, [])

    def test_missing_function_reported_as_none_coverage(self) -> None:
        role = CovenantRoleFactory(name="Herald")
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.CHARM)

        tradition = TraditionFactory(name="The Quiet Order")
        grant = TraditionGiftGrantFactory(tradition=tradition)
        # Pool carries an unrelated function only.
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.BARRIER)
        grant.signature_techniques.set([technique])

        rows = audit_vow_coverage()

        matching = [
            row
            for row in rows
            if row.role_name == "Herald" and row.tradition_name == "The Quiet Order"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].coverage, "none")
        self.assertEqual(matching[0].missing_functions, [TechniqueFunction.CHARM])

    def test_partial_pool_reports_partial_coverage(self) -> None:
        role = CovenantRoleFactory(name="Sentinel")
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.WEAKEN)
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.CHARM)

        tradition = TraditionFactory(name="The Half-Answered Way")
        grant = TraditionGiftGrantFactory(tradition=tradition)
        technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=technique, function=TechniqueFunction.WEAKEN)
        grant.signature_techniques.set([technique])

        rows = audit_vow_coverage()

        matching = [
            row
            for row in rows
            if row.role_name == "Sentinel" and row.tradition_name == "The Half-Answered Way"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].coverage, "partial")
        self.assertEqual(matching[0].missing_functions, [TechniqueFunction.CHARM])

    def test_unauthored_role_is_full_coverage(self) -> None:
        CovenantRoleFactory(name="Blank Vow")
        TraditionFactory(name="Any Tradition")

        rows = audit_vow_coverage()

        matching = [
            row
            for row in rows
            if row.role_name == "Blank Vow" and row.tradition_name == "Any Tradition"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].coverage, "full")

    def test_sub_role_excluded_from_audit(self) -> None:
        parent = CovenantRoleFactory(name="Parent Vow")
        SubroleCovenantRoleFactory(parent_role=parent, name="Child Vow")
        TraditionFactory(name="Some Tradition")

        rows = audit_vow_coverage()

        self.assertFalse(any(row.role_name == "Child Vow" for row in rows))
