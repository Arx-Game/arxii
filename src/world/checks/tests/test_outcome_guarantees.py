"""Tests for TIER_FLOOR + BOTCH_IMMUNITY outcome guarantees in ``perform_check`` (#2536 slice 2).

``perform_check`` (and the test-rig forced-outcome path,
``_build_forced_check_result``) fire ``TIER_FLOOR``/``BOTCH_IMMUNITY``
situational perks — via ``_apply_outcome_guarantees`` — AFTER the outcome is
determined (rolled or forced) and raise it to the effective floor when it
landed below one. Both guarantees are absolute (no thread-level scaling, no
thread-level gate — ungated ruling, 2026-07-20) and announce ONLY when they
actually altered the outcome. ``situation_ctx=None`` (every pre-slice-2 call
site) stays byte-identical — no query, no perk lookup, no alteration.

Modeled directly on ``test_situational_perk_check_bonus.py`` (same
``TestCase``-not-``setUpTestData`` rationale — factories create Evennia
``ObjectDB`` instances, ``DbHolder``, not deepcopyable — and the same
``_engage_role`` helper).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
    VowSituationalPerkSituationFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind, Situation
from world.covenants.perks.context import SituationContext
from world.traits.factories import (
    CheckOutcomeFactory,
    CheckRankFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart


class OutcomeGuaranteeTests(TestCase):
    """Not ``setUpTestData`` — factories create Evennia ``ObjectDB`` instances
    (``DbHolder``, not deepcopyable), same rationale as the perk resolution /
    power-term / CHECK_BONUS suites."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.check_type = CheckTypeFactory(name="Guarantee Check")
        ResultChart.clear_cache()

    def _engage_role(self, *, sheet=None, engaged=True, covenant=None, role=None):
        role = role or CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=sheet or self.sheet,
            covenant=covenant or CovenantFactory(),
            covenant_role=role,
            engaged=engaged,
        )
        return role

    def _chart(self, *levels: int):
        """One rank-0 chart with one outcome per success_level, roll bands stacked."""
        chart = ResultChartFactory(rank_difference=0)
        outcomes = {}
        lo = 1
        for level in levels:
            outcome = CheckOutcomeFactory(name=f"L{level}", success_level=level)
            ResultChartOutcomeFactory(chart=chart, outcome=outcome, min_roll=lo, max_roll=lo + 9)
            outcomes[level] = outcome
            lo += 10
        return chart, outcomes

    def _guarantee_perk(self, *, effect_kind, floor=None, beneficiary=PerkBeneficiary.SELF):
        role = self._engage_role()
        return VowSituationalPerkFactory(
            covenant_role=role,
            effect_kind=effect_kind,
            floor_success_level=floor,
            beneficiary=beneficiary,
        )

    def test_situation_ctx_none_leaves_forced_botch_untouched(self) -> None:
        _chart, outcomes = self._chart(-2, -1, 1)
        self._guarantee_perk(effect_kind=PerkEffectKind.BOTCH_IMMUNITY)

        with force_check_outcome(outcomes[-2]):
            result = perform_check(self.character, self.check_type, situation_ctx=None)

        self.assertEqual(result.outcome, outcomes[-2])

    def test_botch_immunity_downgrades_botch_to_least_bad_non_botch(self) -> None:
        _chart, outcomes = self._chart(-2, -1, 1)
        self._guarantee_perk(effect_kind=PerkEffectKind.BOTCH_IMMUNITY)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with force_check_outcome(outcomes[-2]):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome.success_level, -1)

    def test_botch_immunity_ignores_plain_failure(self) -> None:
        _chart, outcomes = self._chart(-2, -1, 1)
        self._guarantee_perk(effect_kind=PerkEffectKind.BOTCH_IMMUNITY)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with (
            patch("world.covenants.perks.services.announce_fired_perks") as mock_announce,
            force_check_outcome(outcomes[-1]),
        ):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome, outcomes[-1])
        mock_announce.assert_not_called()

    def test_botch_immunity_needs_no_threads(self) -> None:
        """UNGATED ruling (2026-07-20): no ThreadFactory anywhere — the
        guarantee still binds."""
        _chart, outcomes = self._chart(-2, -1, 1)
        self._guarantee_perk(effect_kind=PerkEffectKind.BOTCH_IMMUNITY)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with force_check_outcome(outcomes[-2]):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome.success_level, -1)

    def test_tier_floor_lifts_below_floor_outcome(self) -> None:
        _chart, outcomes = self._chart(-2, -1, 1, 2)
        self._guarantee_perk(effect_kind=PerkEffectKind.TIER_FLOOR, floor=1)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with force_check_outcome(outcomes[-1]):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome.success_level, 1)

    def test_tier_floor_does_not_bind_at_or_above_floor(self) -> None:
        _chart, outcomes = self._chart(-2, -1, 1, 2)
        self._guarantee_perk(effect_kind=PerkEffectKind.TIER_FLOOR, floor=1)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with force_check_outcome(outcomes[2]):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome, outcomes[2])

    def test_highest_floor_wins(self) -> None:
        _chart, outcomes = self._chart(-2, -1, 0, 1)
        self._guarantee_perk(effect_kind=PerkEffectKind.TIER_FLOOR, floor=0)
        self._guarantee_perk(effect_kind=PerkEffectKind.TIER_FLOOR, floor=1)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with force_check_outcome(outcomes[-2]):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome.success_level, 1)

    def test_unmet_situation_gates_guarantee(self) -> None:
        _chart, outcomes = self._chart(-2, -1, 1)
        perk = self._guarantee_perk(effect_kind=PerkEffectKind.BOTCH_IMMUNITY)
        VowSituationalPerkSituationFactory(perk=perk, situation=Situation.TARGET_DISTRACTED)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with force_check_outcome(outcomes[-2]):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome, outcomes[-2])

    def test_chart_without_qualifying_outcome_falls_back_to_global(self) -> None:
        _chart, outcomes = self._chart(-2, -1)
        global_outcome = CheckOutcomeFactory(name="GlobalOnly", success_level=1)
        self._guarantee_perk(effect_kind=PerkEffectKind.TIER_FLOOR, floor=1)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with force_check_outcome(outcomes[-2]):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome, global_outcome)
        self.assertEqual(result.outcome.success_level, 1)

    def test_announced_exactly_once_and_only_on_alteration(self) -> None:
        from evennia import create_object

        room = create_object(
            "typeclasses.rooms.Room", key="OutcomeGuaranteeAnnounceRoom", nohome=True
        )
        self.character.location = room
        self.character.save()

        _chart, outcomes = self._chart(-2, -1, 1)
        perk = self._guarantee_perk(effect_kind=PerkEffectKind.BOTCH_IMMUNITY)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with (
            patch("world.covenants.perks.services.announce_fired_perks") as mock_announce,
            force_check_outcome(outcomes[-2]),
        ):
            perform_check(self.character, self.check_type, situation_ctx=ctx)

        assert mock_announce.call_count == 1
        (fired_arg,), kwargs = mock_announce.call_args
        assert len(fired_arg) == 1
        assert fired_arg[0].perk == perk
        assert kwargs["subject"] == self.sheet
        assert kwargs["location"] == room

        mock_announce.reset_mock()
        with force_check_outcome(outcomes[1]):
            perform_check(self.character, self.check_type, situation_ctx=ctx)

        mock_announce.assert_not_called()

    def test_rolled_path_applies_guarantees(self) -> None:
        CheckRankFactory(rank=0, min_points=0)
        _chart, outcomes = self._chart(-2, -1, 1)
        self._guarantee_perk(effect_kind=PerkEffectKind.BOTCH_IMMUNITY)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with patch("world.checks.services.random.randint", return_value=1):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome, outcomes[-1])
