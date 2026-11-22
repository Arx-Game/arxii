"""Service tests for apply_anima_ritual_outcome (Scope 6 Phase 8, retargeted in #5280).

The anima ritual is never done alone, so the roll and its gates belong to the partner
ritual (``check_partner_ritual``, ``resolve_ritual_request``); these tests apply a rolled
outcome row and check what it did to anima and Soulfray. SoulfrayConfig
and ConditionTemplate rows are created in setUp because they are singletons
queried with .first() / .get(name=...).

The per-character ritual is now a Ritual(execution_kind=SCENE_ACTION) +
RitualCheckConfig. Tests create the full pair via factories and attach
the Ritual to the character's account via author_account.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    SoulfrayTemplateFactory,
)
from world.magic.constants import RitualExecutionKind
from world.magic.exceptions import RitualAlreadyPerformedThisScene
from world.magic.factories import (
    CharacterAnimaFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    SoulfrayConfigFactory,
)
from world.magic.models.anima import AnimaRitualPerformance
from world.magic.models.soulfray import AnimaRitualBudgetAward
from world.magic.services.anima import apply_anima_ritual_outcome
from world.scenes.factories import SceneFactory
from world.traits.factories import CheckOutcomeFactory
from world.traits.models import CheckOutcome


def _outcome(success_level: int) -> CheckOutcome:
    """A real CheckOutcome row at ``success_level``."""
    return CheckOutcomeFactory(
        name=f"Outcome_sl_{success_level}_{id(object())}",
        success_level=success_level,
    )


def _perform(sheet, ritual, outcome, scene):
    """Apply a rolled ``outcome`` to ``sheet``'s ritual with a partner, as an accepted request
    does after the roll (the roll itself is ``resolve_ritual_request``'s, covered by the
    journeys)."""
    return apply_anima_ritual_outcome(
        ritual=ritual,
        outcome=outcome,
        scene=scene,
        character_sheet=sheet,
        partner_sheet=CharacterSheetFactory(),
    )


def _make_ritual_for_sheet(sheet):
    """Create a SCENE_ACTION Ritual + sidecar for the given character sheet.

    Sets character.db_account if not already set, then creates the ritual
    with author_account pointing to that account.
    """
    character = sheet.character
    if character.db_account is None:
        account = AccountFactory()
        character.db_account = account
        character.save(update_fields=["db_account"])
    ritual = RitualFactory(
        execution_kind=RitualExecutionKind.SCENE_ACTION,
        service_function_path="",
        flow=None,
        author_account=character.db_account,
    )
    RitualCheckConfigFactory(ritual=ritual)
    return ritual


class CritNoSoulfrayTests(TestCase):
    """Crit with no active Soulfray: anima goes to max, no severity change."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = _make_ritual_for_sheet(self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet,
            current=3,
            maximum=10,
        )
        self.config = SoulfrayConfigFactory(
            ritual_severity_cost_per_point=1,
        )
        self.soulfray_template = SoulfrayTemplateFactory()
        self.scene = SceneFactory(is_active=True)

    def test_crit_no_soulfray_anima_goes_to_max(self) -> None:
        outcome = _outcome(2)
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=10)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 10)
        self.assertEqual(result.severity_reduced, 0)
        self.assertEqual(result.anima_recovered, 7)  # 10 - 3
        self.assertFalse(result.soulfray_resolved)
        self.assertIsNone(result.soulfray_stage_after)


class CritWithSoulfrayTests(TestCase):
    """Crit with active Soulfray: severity paid down, anima goes to max."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = _make_ritual_for_sheet(self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet,
            current=5,
            maximum=10,
        )
        self.soulfray_template = SoulfrayTemplateFactory()
        self.soulfray_inst = ConditionInstanceFactory(
            target=self.sheet.character,
            condition=self.soulfray_template,
            severity=2,
        )
        self.config = SoulfrayConfigFactory(
            ritual_severity_cost_per_point=2,  # 2 budget per severity point
        )
        self.scene = SceneFactory(is_active=True)

    def test_crit_with_soulfray_severity_paid_down_anima_force_refilled(self) -> None:
        outcome = _outcome(2)
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=10)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        # Crit budget=10, cost_per_point=2: can reduce 5 severity points, but only 2 exist
        # After 2 reductions: budget = 10 - 4 = 6 remaining
        # Crit always fills anima to max regardless
        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 10)
        self.assertEqual(result.severity_reduced, 2)
        self.assertTrue(result.soulfray_resolved)


class SuccessWithSoulfrayTests(TestCase):
    """Success outcome with Soulfray: partial severity reduction + partial anima."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = _make_ritual_for_sheet(self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet,
            current=2,
            maximum=10,
        )
        self.soulfray_template = SoulfrayTemplateFactory()
        self.soulfray_inst = ConditionInstanceFactory(
            target=self.sheet.character,
            condition=self.soulfray_template,
            severity=5,  # 5 severity points
        )
        self.config = SoulfrayConfigFactory(
            ritual_severity_cost_per_point=2,  # 2 budget per severity point
        )
        self.scene = SceneFactory(is_active=True)

    def test_success_with_soulfray_severity_reduced_partial_anima_refill(self) -> None:
        outcome = _outcome(1)
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=6)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        # Success budget=6, cost_per_point=2: can reduce 3 severity points (cost=6)
        # Budget exhausted after 3 reductions → 0 left for anima
        self.assertEqual(result.severity_reduced, 3)
        self.anima.refresh_from_db()
        # budget=0 after severity reduction, so anima stays at 2
        self.assertEqual(self.anima.current, 2)
        self.assertEqual(result.anima_recovered, 0)
        self.assertFalse(result.soulfray_resolved)


class PartialWithHighSoulfrayTests(TestCase):
    """Partial outcome with high severity Soulfray: small severity reduction, leftover anima.

    Spec §4.11 budget guard: loop runs while budget >= cost_per_point, so partial
    budget=3 with cost=2 yields exactly 1 reduction (2 spent) and 1 leftover for anima.
    """

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = _make_ritual_for_sheet(self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet,
            current=1,
            maximum=10,
        )
        self.soulfray_template = SoulfrayTemplateFactory()
        self.soulfray_inst = ConditionInstanceFactory(
            target=self.sheet.character,
            condition=self.soulfray_template,
            severity=10,
        )
        self.config = SoulfrayConfigFactory(
            ritual_severity_cost_per_point=2,
        )
        self.scene = SceneFactory(is_active=True)

    def test_partial_high_soulfray_small_severity_reduction_leftover_anima(self) -> None:
        outcome = _outcome(0)
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=3)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        # Partial budget=3, cost_per_point=2 (guard: budget >= cost_per_point):
        #   iteration 1: budget(3) >= 2 → reduce, budget=1
        #   iteration 2: budget(1) NOT >= 2 → exit
        # 1 reduction, 1 budget remaining → refills 1 anima
        self.assertEqual(result.severity_reduced, 1)
        self.anima.refresh_from_db()
        # 1 budget leftover → anima goes from 1 to 2
        self.assertEqual(self.anima.current, 2)
        self.assertEqual(result.anima_recovered, 1)
        self.assertFalse(result.soulfray_resolved)
        # Partial Success is a success at its own tier (maintainer ruling 2026-11-22).
        self.assertTrue(result.performance.was_successful)


class FailureNoSoulfrayTests(TestCase):
    """Failure outcome with no Soulfray: a failed roll gives no anima."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = _make_ritual_for_sheet(self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet,
            current=0,
            maximum=10,
        )
        self.config = SoulfrayConfigFactory(
            ritual_severity_cost_per_point=1,
        )
        self.soulfray_template = SoulfrayTemplateFactory()
        self.scene = SceneFactory(is_active=True)

    def test_failure_no_soulfray_gives_no_anima(self) -> None:
        outcome = _outcome(-1)
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=1)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, 0)  # the Failure row's budget of 1 is not paid
        self.assertEqual(result.anima_recovered, 0)
        self.assertEqual(result.severity_reduced, 0)
        self.assertFalse(result.performance.was_successful)


class ChosenPatronShareTests(TestCase):
    """A Chosen's patron adds anima by the ritual's result, and the result says how much (#4349)."""

    def setUp(self) -> None:
        from world.worship.constants import FavorAwardKind
        from world.worship.factories import (
            FavorOutcomeAwardFactory,
            WorshippedBeingFactory,
            make_chosen,
        )

        self.sheet = CharacterSheetFactory()
        self.ritual = _make_ritual_for_sheet(self.sheet)
        self.anima = CharacterAnimaFactory(character=self.sheet, current=0, maximum=20)
        SoulfrayConfigFactory(ritual_severity_cost_per_point=1)
        SoulfrayTemplateFactory()
        self.scene = SceneFactory(is_active=True)
        self.being = WorshippedBeingFactory(name="The Tide")
        make_chosen(self.sheet, self.being, favor=12)
        self.award = lambda outcome, amount: FavorOutcomeAwardFactory(
            kind=FavorAwardKind.CHOSEN_ANIMA, outcome_tier=outcome, amount=amount
        )

    def test_a_good_ritual_shows_what_the_patron_added(self) -> None:
        outcome = _outcome(1)
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=3)
        self.award(outcome, 5)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        self.assertEqual(result.anima_recovered, 8)
        self.assertEqual((result.patron_bonus, result.patron_name), (5, "The Tide"))

    def test_a_failure_gets_nothing_from_the_patron_and_no_anima(self) -> None:
        outcome = _outcome(-1)
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=2)
        self.award(outcome, 5)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        self.assertEqual((result.anima_recovered, result.patron_bonus), (0, 0))


class GateTests(TestCase):
    """Gate conditions that raise before check is rolled."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = _make_ritual_for_sheet(self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet,
            current=5,
            maximum=10,
        )
        self.config = SoulfrayConfigFactory(
            ritual_severity_cost_per_point=1,
        )
        self.soulfray_template = SoulfrayTemplateFactory()
        self.scene = SceneFactory(is_active=True)

    def test_second_ritual_same_scene_raises(self) -> None:
        outcome = _outcome(1)
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=6)
        # First call succeeds
        _perform(self.sheet, self.ritual, outcome, self.scene)
        # Second call raises
        with self.assertRaises(RitualAlreadyPerformedThisScene):
            _perform(self.sheet, self.ritual, outcome, self.scene)


class PerformanceRowTests(TestCase):
    """Performance row is persisted with accurate fields."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = _make_ritual_for_sheet(self.sheet)
        self.anima = CharacterAnimaFactory(
            character=self.sheet,
            current=3,
            maximum=10,
        )
        self.config = SoulfrayConfigFactory(
            ritual_severity_cost_per_point=1,
        )
        self.soulfray_template = SoulfrayTemplateFactory()
        self.scene = SceneFactory(is_active=True)

    def test_performance_row_persisted_with_accurate_fields(self) -> None:
        outcome = _outcome(1)
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=6)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        perf = AnimaRitualPerformance.objects.get(pk=result.performance.pk)
        self.assertEqual(perf.ritual, self.ritual)
        self.assertEqual(perf.scene, self.scene)
        self.assertTrue(perf.was_successful)
        # success budget=6, no soulfray, so anima goes from 3 to 9
        self.assertEqual(perf.anima_recovered, 6)
        self.assertEqual(perf.severity_reduced, 0)
        self.assertIsNotNone(perf.outcome)


class AnimaRitualBudgetGuardTests(TestCase):
    """Spec §4.11: the outcome applier's loop guard prevents overspend.

    The loop guard 'budget >= cost_per_point' ensures that when cost > 1
    the loop does not run when the remaining budget cannot pay for a full
    severity reduction. Before the fix the guard was 'budget > 0', which
    allowed one extra (unpaid) reduction when budget < cost_per_point.
    """

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.ritual = _make_ritual_for_sheet(self.sheet)
        self.soulfray_template = SoulfrayTemplateFactory()
        self.scene = SceneFactory(is_active=True)

    def test_cost_one_budget_three_three_reductions(self) -> None:
        """cost=1, budget=3, severity=10 → 3 severity reductions, 0 leftover for anima.

        Unchanged behavior at cost=1 (current default).
        """
        CharacterAnimaFactory(character=self.sheet, current=0, maximum=10)
        ConditionInstanceFactory(
            target=self.sheet.character,
            condition=self.soulfray_template,
            severity=10,
        )
        SoulfrayConfigFactory(ritual_severity_cost_per_point=1)
        outcome = _outcome(1)  # success → budget=3
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=3)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        # cost=1: 3 reductions consume budget exactly; 0 leftover → no anima refill
        self.assertEqual(result.severity_reduced, 3)
        self.assertEqual(result.anima_recovered, 0)

    def test_cost_two_budget_three_one_reduction_one_leftover(self) -> None:
        """cost=2, budget=3 → 1 reduction (2 spent), 1 leftover refills anima.

        BEFORE the fix: loop ran while budget > 0, so:
          iter 1: budget=3 (>0), decrement → budget=1, severity reduced
          iter 2: budget=1 (>0), decrement → budget=-1, severity reduced  (overspend!)
        AFTER the fix: loop runs while budget >= cost (=2), so:
          iter 1: budget=3 (>=2), decrement → budget=1, severity reduced
          iter 2: budget=1 (NOT >=2), exit. 1 leftover refills anima.
        """
        CharacterAnimaFactory(character=self.sheet, current=0, maximum=10)
        ConditionInstanceFactory(
            target=self.sheet.character,
            condition=self.soulfray_template,
            severity=10,
        )
        SoulfrayConfigFactory(ritual_severity_cost_per_point=2)
        outcome = _outcome(1)  # success → budget=3
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=3)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        # cost=2, budget=3: only 1 reduction (2 spent), 1 leftover → anima refill of 1
        self.assertEqual(result.severity_reduced, 1)
        self.assertEqual(result.anima_recovered, 1)

    def test_no_soulfray_full_budget_to_anima(self) -> None:
        """cost=2, no soulfray instance → 0 reductions, full budget for anima.

        Regression guard for the no-soulfray short-circuit path; the loop
        is gated by 'if soulfray_inst is not None:' and never enters.
        """
        CharacterAnimaFactory(character=self.sheet, current=0, maximum=10)
        # No ConditionInstance created for this character
        SoulfrayConfigFactory(ritual_severity_cost_per_point=2)
        outcome = _outcome(1)  # success → budget=3
        AnimaRitualBudgetAward.objects.create(outcome_tier=outcome, budget=3)

        result = _perform(self.sheet, self.ritual, outcome, self.scene)

        # No soulfray → 0 reductions; full budget=3 refills anima
        self.assertEqual(result.severity_reduced, 0)
        self.assertEqual(result.anima_recovered, 3)
