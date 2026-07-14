"""Tests for the WAR_FUNDING project kind (#1890).

Mirrors the CITY_DEFENSE test structure (world/battles/tests/test_city_defense.py):
unit tests for _select_tier, _apply_quality_steps, get_war_funding_bonus, handler
idempotency, readiness accumulation, start-project gating, and a full scan-journey
test that grades at deadline and verifies bonuses flow through add_unit.
"""

from __future__ import annotations

import datetime

from django.test import TestCase
from django.utils import timezone

from world.battles.constants import UnitQuality
from world.battles.factories import BattleFactory, BattleSideFactory
from world.battles.models import (
    CovenantMilitaryReadiness,
    ReadinessThreshold,
    WarFundingDetails,
    WarFundingTierBonus,
    WarFundingTierThreshold,
)
from world.battles.services import add_unit
from world.battles.war_funding_services import (
    _apply_quality_steps,
    _select_tier,
    complete_war_funding,
    get_war_funding_bonus,
    resolve_war_funding,
    start_war_funding_project,
)
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantManagerRankFactory,
)
from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.projects.factories import ProjectFactory
from world.projects.services import (
    clear_kind_handlers,
    clear_tiered_resolvers,
    register_kind_handler,
    register_tiered_resolver,
    scan_active_projects,
)
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory


def _make_war_funding_details(
    *,
    covenant=None,
    owner_persona=None,
    progress=0,
    status=ProjectStatus.ACTIVE,
    time_limit=None,
) -> WarFundingDetails:
    """Helper: create a WarFundingDetails with thresholds."""
    project = ProjectFactory(
        kind=ProjectKind.WAR_FUNDING,
        completion_mode=CompletionMode.TIERED_PERIOD,
        status=status,
        owner_persona=owner_persona or PersonaFactory(),
        current_progress=progress,
        time_limit=time_limit or timezone.now() + datetime.timedelta(days=30),
    )
    details = WarFundingDetails.objects.create(
        project=project, covenant=covenant or CovenantFactory()
    )
    failure = CheckOutcomeFactory(success_level=-1)
    partial = CheckOutcomeFactory(success_level=0)
    success = CheckOutcomeFactory(success_level=1)
    critical = CheckOutcomeFactory(success_level=2)
    WarFundingTierThreshold.objects.create(details=details, outcome_tier=failure, min_progress=0)
    WarFundingTierThreshold.objects.create(details=details, outcome_tier=partial, min_progress=25)
    WarFundingTierThreshold.objects.create(details=details, outcome_tier=success, min_progress=50)
    WarFundingTierThreshold.objects.create(details=details, outcome_tier=critical, min_progress=100)
    return details


def _make_tier_bonus(outcome_tier, *, quality_steps=0, strength=0, morale=0, xp=0):
    return WarFundingTierBonus.objects.create(
        outcome_tier=outcome_tier,
        quality_steps=quality_steps,
        strength_bonus=strength,
        morale_bonus=morale,
        training_xp=xp,
    )


class SelectTierTests(TestCase):
    def test_highest_threshold_at_or_below_progress(self) -> None:
        details = _make_war_funding_details()
        thresholds = list(details.tier_thresholds.all())

        self.assertEqual(_select_tier(thresholds, 0).min_progress, 0)
        self.assertEqual(_select_tier(thresholds, 25).min_progress, 25)
        self.assertEqual(_select_tier(thresholds, 49).min_progress, 25)
        self.assertEqual(_select_tier(thresholds, 50).min_progress, 50)
        self.assertEqual(_select_tier(thresholds, 999).min_progress, 100)


class ApplyQualityStepsTests(TestCase):
    def test_zero_steps_no_change(self) -> None:
        self.assertEqual(_apply_quality_steps(UnitQuality.TRAINED, 0), UnitQuality.TRAINED)

    def test_one_step(self) -> None:
        self.assertEqual(_apply_quality_steps(UnitQuality.TRAINED, 1), UnitQuality.VETERAN)

    def test_two_steps(self) -> None:
        self.assertEqual(_apply_quality_steps(UnitQuality.LEVY, 2), UnitQuality.VETERAN)

    def test_three_steps_clamps_at_elite(self) -> None:
        self.assertEqual(_apply_quality_steps(UnitQuality.LEVY, 3), UnitQuality.ELITE)

    def test_clamps_at_elite(self) -> None:
        self.assertEqual(_apply_quality_steps(UnitQuality.VETERAN, 5), UnitQuality.ELITE)

    def test_militia_to_levy(self) -> None:
        self.assertEqual(_apply_quality_steps(UnitQuality.MILITIA, 1), UnitQuality.LEVY)


class HandlerIdempotencyTests(TestCase):
    def test_stores_tier_and_updates_readiness_once(self) -> None:
        covenant = CovenantFactory()
        owner = PersonaFactory()
        details = _make_war_funding_details(covenant=covenant, owner_persona=owner, progress=50)
        success_tier = details.tier_thresholds.get(min_progress=50).outcome_tier
        _make_tier_bonus(success_tier, quality_steps=1, strength=15, morale=10, xp=50)

        complete_war_funding(details.project, success_tier)

        raw = WarFundingDetails.objects.values("applied_at", "outcome_tier_id").get(
            project=details.project
        )
        first_applied = raw["applied_at"]
        first_tier = raw["outcome_tier_id"]
        self.assertIsNotNone(first_applied)
        readiness = CovenantMilitaryReadiness.objects.get(covenant=covenant)
        self.assertEqual(readiness.training_level, 50)

        # Second call should no-op.
        failure_tier = details.tier_thresholds.get(min_progress=0).outcome_tier
        complete_war_funding(details.project, failure_tier)
        raw = WarFundingDetails.objects.values("applied_at", "outcome_tier_id").get(
            project=details.project
        )
        self.assertEqual(raw["outcome_tier_id"], first_tier)
        self.assertEqual(raw["applied_at"], first_applied)
        # Readiness unchanged.
        readiness.refresh_from_db()
        self.assertEqual(readiness.training_level, 50)

    def test_failed_outcome_no_op(self) -> None:
        covenant = CovenantFactory()
        details = _make_war_funding_details(covenant=covenant, progress=0)
        failure_tier = details.tier_thresholds.get(min_progress=0).outcome_tier

        complete_war_funding(details.project, failure_tier)

        details.refresh_from_db()
        self.assertIsNone(details.applied_at)
        self.assertFalse(CovenantMilitaryReadiness.objects.filter(covenant=covenant).exists())


class ReadinessAccumulationTests(TestCase):
    def test_two_projects_accumulate_and_cross_threshold(self) -> None:
        covenant = CovenantFactory()
        owner = PersonaFactory()

        # First project: Success tier, +50 training_xp.
        details1 = _make_war_funding_details(covenant=covenant, owner_persona=owner, progress=50)
        success_tier1 = details1.tier_thresholds.get(min_progress=50).outcome_tier
        _make_tier_bonus(success_tier1, xp=50)
        complete_war_funding(details1.project, success_tier1)

        readiness = CovenantMilitaryReadiness.objects.get(covenant=covenant)
        self.assertEqual(readiness.training_level, 50)

        # Second project: Partial tier, +25 training_xp → total 75.
        details2 = _make_war_funding_details(covenant=covenant, owner_persona=owner, progress=25)
        partial_tier = details2.tier_thresholds.get(min_progress=25).outcome_tier
        _make_tier_bonus(partial_tier, xp=25)
        complete_war_funding(details2.project, partial_tier)

        readiness.refresh_from_db()
        self.assertEqual(readiness.training_level, 75)

        # Seed a ReadinessThreshold at 75 → +1 quality step.
        ReadinessThreshold.objects.create(min_training_level=75, bonus_quality_steps=1)
        bonus = get_war_funding_bonus(covenant)
        # Per-tier: partial bonus has 0 quality_steps; readiness: +1.
        self.assertEqual(bonus.quality_steps, 1)


class GetWarFundingBonusTests(TestCase):
    def test_returns_correct_combined_bonus(self) -> None:
        covenant = CovenantFactory()
        details = _make_war_funding_details(covenant=covenant, progress=100)
        critical_tier = details.tier_thresholds.get(min_progress=100).outcome_tier
        _make_tier_bonus(critical_tier, quality_steps=2, strength=30, morale=20, xp=100)
        complete_war_funding(details.project, critical_tier)

        # Seed readiness threshold at 100 → +1 quality step.
        ReadinessThreshold.objects.create(min_training_level=100, bonus_quality_steps=1)

        bonus = get_war_funding_bonus(covenant)
        self.assertEqual(bonus.quality_steps, 3)  # 2 per-tier + 1 readiness
        self.assertEqual(bonus.strength_bonus, 30)
        self.assertEqual(bonus.morale_bonus, 20)

    def test_zeros_for_no_project(self) -> None:
        covenant = CovenantFactory()
        bonus = get_war_funding_bonus(covenant)
        self.assertEqual(bonus.quality_steps, 0)
        self.assertEqual(bonus.strength_bonus, 0)
        self.assertEqual(bonus.morale_bonus, 0)

    def test_zeros_for_missing_award_row(self) -> None:
        covenant = CovenantFactory()
        details = _make_war_funding_details(covenant=covenant, progress=50)
        success_tier = details.tier_thresholds.get(min_progress=50).outcome_tier
        # No WarFundingTierBonus row created.
        complete_war_funding(details.project, success_tier)
        bonus = get_war_funding_bonus(covenant)
        self.assertEqual(bonus.quality_steps, 0)
        self.assertEqual(bonus.strength_bonus, 0)
        self.assertEqual(bonus.morale_bonus, 0)

    def test_zeros_for_missing_readiness(self) -> None:
        covenant = CovenantFactory()
        # No completed project, no readiness.
        ReadinessThreshold.objects.create(min_training_level=0, bonus_quality_steps=0)
        bonus = get_war_funding_bonus(covenant)
        self.assertEqual(bonus.quality_steps, 0)


class ScanJourneyTests(TestCase):
    def setUp(self) -> None:
        register_kind_handler(ProjectKind.WAR_FUNDING, complete_war_funding)
        register_tiered_resolver(ProjectKind.WAR_FUNDING, resolve_war_funding)

    def tearDown(self) -> None:
        clear_kind_handlers()
        clear_tiered_resolvers()

    def test_full_journey_grade_and_verify_bonus(self) -> None:
        covenant = CovenantFactory()
        owner = PersonaFactory()
        # Set time_limit in the past so scan_active_projects picks it up.
        details = _make_war_funding_details(
            covenant=covenant,
            owner_persona=owner,
            progress=50,
            time_limit=timezone.now() - datetime.timedelta(hours=1),
        )
        success_tier = details.tier_thresholds.get(min_progress=50).outcome_tier
        _make_tier_bonus(success_tier, quality_steps=1, strength=15, morale=10, xp=50)
        ReadinessThreshold.objects.create(min_training_level=50, bonus_quality_steps=1)

        transitioned = scan_active_projects()
        self.assertEqual(transitioned, 1)

        details.refresh_from_db()
        self.assertEqual(details.outcome_tier_id, success_tier.pk)
        # Re-fetch from DB — SMM cache may not reflect the handler's queryset .update().
        raw = WarFundingDetails.objects.values("applied_at").get(project=details.project)
        self.assertIsNotNone(raw["applied_at"])

        readiness = CovenantMilitaryReadiness.objects.get(covenant=covenant)
        self.assertEqual(readiness.training_level, 50)

        bonus = get_war_funding_bonus(covenant)
        self.assertEqual(bonus.quality_steps, 2)  # 1 per-tier + 1 readiness
        self.assertEqual(bonus.strength_bonus, 15)
        self.assertEqual(bonus.morale_bonus, 10)


class StartProjectTests(TestCase):
    def test_gates_on_leader_rank(self) -> None:
        covenant = CovenantFactory()
        persona = PersonaFactory()
        # No membership at all.
        with self.assertRaises(ValueError):
            start_war_funding_project(covenant=covenant, owner_persona=persona)

    def test_creates_details_and_bootstraps_readiness(self) -> None:
        covenant = CovenantFactory()
        persona = PersonaFactory()
        rank = CovenantManagerRankFactory(covenant=covenant, can_lead_rituals=True)
        CharacterCovenantRoleFactory(
            character_sheet=persona.character_sheet,
            covenant=covenant,
            rank=rank,
            engaged=True,
            left_at=None,
        )

        # Provide explicit thresholds — canonical CheckOutcome names may not exist
        # in the test DB.
        failure = CheckOutcomeFactory(success_level=-1)
        success = CheckOutcomeFactory(success_level=1)
        thresholds = [(failure, 0), (success, 50)]

        project = start_war_funding_project(
            covenant=covenant,
            owner_persona=persona,
            tier_thresholds=thresholds,
        )

        self.assertEqual(project.kind, ProjectKind.WAR_FUNDING)
        self.assertEqual(project.completion_mode, CompletionMode.TIERED_PERIOD)
        self.assertEqual(project.status, ProjectStatus.ACTIVE)
        details = WarFundingDetails.objects.get(project=project)
        self.assertEqual(details.covenant_id, covenant.pk)
        self.assertTrue(details.tier_thresholds.exists())
        self.assertTrue(CovenantMilitaryReadiness.objects.filter(covenant=covenant).exists())


class AddUnitIntegrationTests(TestCase):
    def test_bonus_applied_to_military_unit(self) -> None:
        covenant = CovenantFactory()
        battle = BattleFactory()
        side = BattleSideFactory(battle=battle, covenant=covenant)

        # Complete a WAR_FUNDING project for this covenant.
        details = _make_war_funding_details(covenant=covenant, progress=100)
        critical_tier = details.tier_thresholds.get(min_progress=100).outcome_tier
        _make_tier_bonus(critical_tier, quality_steps=1, strength=20, morale=10, xp=0)
        complete_war_funding(details.project, critical_tier)

        unit = add_unit(
            battle=battle,
            side=side,
            name="Test Cavalry",
            quality=UnitQuality.TRAINED,
            strength=100,
            morale=50,
        )

        # The MilitaryUnit should have upgraded quality and boosted stats.
        mu = unit.military_unit
        self.assertEqual(mu.quality, UnitQuality.VETERAN)  # TRAINED + 1 step
        self.assertEqual(mu.strength, 120)  # 100 + 20
        self.assertEqual(mu.morale, 60)  # 50 + 10

    def test_no_covenant_no_bonus(self) -> None:
        battle = BattleFactory()
        side = BattleSideFactory(battle=battle, covenant=None)

        unit = add_unit(
            battle=battle,
            side=side,
            name="Unaffiliated Unit",
            quality=UnitQuality.TRAINED,
            strength=100,
            morale=50,
        )

        mu = unit.military_unit
        self.assertEqual(mu.quality, UnitQuality.TRAINED)
        self.assertEqual(mu.strength, 100)
        self.assertEqual(mu.morale, 50)
