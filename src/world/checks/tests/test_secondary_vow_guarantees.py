"""Tests for the secondary-vow layer split in the checks-app Layer 4 seams (#2641):

- CHECK_BONUS magnitude (``_situational_perk_check_bonus``): potency-scaled when
  the firing is sourced from a SECONDARY membership.
- Outcome guarantees (``_apply_outcome_guarantees``): a secondary-sourced TIER_FLOOR
  binds one tier weaker (``floor_success_level - 1``); BOTCH_IMMUNITY stays at full
  strength (deliberately unweakened — no numeric field to soften).

Modeled directly on ``test_situational_perk_check_bonus.py`` / ``test_outcome_guarantees.py``
(same ``TestCase``-not-``setUpTestData`` rationale — factories create Evennia ``ObjectDB``
instances, ``DbHolder``, not deepcopyable).
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import _situational_perk_check_bonus, perform_check
from world.checks.test_helpers import force_check_outcome
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
from world.covenants.perks.context import SituationContext
from world.magic.factories import ThreadFactory
from world.traits.factories import (
    CheckOutcomeFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart


class SecondaryVowCheckBonusScalingTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.check_type = CheckTypeFactory(name="Secondary Vow Check")

    def _engage(self, role, *, is_secondary):
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
            is_secondary=is_secondary,
        )

    def test_secondary_check_bonus_scaled_primary_unscaled(self) -> None:
        ThreadFactory(owner=self.sheet, level=10)  # total_threads = 10
        primary_role = CovenantRoleFactory()
        secondary_role = CovenantRoleFactory()
        self._engage(primary_role, is_secondary=False)
        self._engage(secondary_role, is_secondary=True)
        VowSituationalPerkFactory(
            covenant_role=primary_role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=20,
            check_type=None,
        )
        VowSituationalPerkFactory(
            covenant_role=secondary_role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=20,
            check_type=None,
        )
        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)

        # primary: 10*20/10=20.0; secondary: 10*20/10=20.0 * potency 0.6 = 12.0
        # total = 32.0 -> int(32.0) = 32
        total = _situational_perk_check_bonus(self.character, self.check_type, ctx)
        self.assertEqual(total, 32)


class SecondaryVowOutcomeGuaranteeWeakeningTests(TestCase):
    """Not ``setUpTestData`` — see module docstring."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.check_type = CheckTypeFactory(name="Secondary Guarantee Check")
        ResultChart.clear_cache()

    def _engage_secondary_perk_role(self):
        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
            is_secondary=True,
        )
        return role

    def _chart(self, *levels: int):
        chart = ResultChartFactory(rank_difference=0)
        outcomes = {}
        lo = 1
        for level in levels:
            outcome = CheckOutcomeFactory(name=f"L{level}", success_level=level)
            ResultChartOutcomeFactory(chart=chart, outcome=outcome, min_roll=lo, max_roll=lo + 9)
            outcomes[level] = outcome
            lo += 10
        return chart, outcomes

    def test_secondary_tier_floor_binds_one_tier_weaker(self) -> None:
        _chart, outcomes = self._chart(-2, -1, 1, 2)
        role = self._engage_secondary_perk_role()
        VowSituationalPerkFactory(
            covenant_role=role,
            effect_kind=PerkEffectKind.TIER_FLOOR,
            floor_success_level=2,
            beneficiary=PerkBeneficiary.SELF,
        )

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with force_check_outcome(outcomes[-1]):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        # Authored floor is 2; a secondary-sourced firing binds at floor - 1 = 1.
        self.assertEqual(result.outcome.success_level, 1)

    def test_secondary_botch_immunity_unweakened(self) -> None:
        """BOTCH_IMMUNITY has no numeric field to soften — a secondary-sourced
        firing downgrades a botch exactly like a primary's (deliberate judgment
        call, #2641)."""
        _chart, outcomes = self._chart(-2, -1, 1)
        role = self._engage_secondary_perk_role()
        VowSituationalPerkFactory(
            covenant_role=role,
            effect_kind=PerkEffectKind.BOTCH_IMMUNITY,
            beneficiary=PerkBeneficiary.SELF,
        )

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with force_check_outcome(outcomes[-2]):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome.success_level, -1)
