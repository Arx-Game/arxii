"""Tests for the CITY_DEFENSE project kind (#1892).

Mirrors the GANG_TURF test structure (world/societies/tests/test_gang_turf.py):
unit tests for _select_tier and get_city_defense_integrity_bonus, handler
idempotency, and a full scan-journey test that grades at deadline and verifies
the fortification integrity bonus flows through create_fortification.
"""

from __future__ import annotations

import datetime

from django.test import TestCase
from django.utils import timezone

from world.areas.factories import AreaFactory
from world.battles.city_defense_services import (
    _select_tier,
    complete_city_defense,
    get_city_defense_integrity_bonus,
    resolve_city_defense,
    start_city_defense_project,
)
from world.battles.constants import BASE_INTEGRITY, FortificationKind
from world.battles.factories import BattleFactory, BattlePlaceFactory, BattleSideFactory
from world.battles.models import (
    CityDefenseDetails,
    CityDefenseIntegrityBonus,
    CityDefenseTierThreshold,
)
from world.battles.services import create_fortification
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


class SelectTierTests(TestCase):
    def test_highest_threshold_at_or_below_progress(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.CITY_DEFENSE, completion_mode=CompletionMode.TIERED_PERIOD
        )
        area = AreaFactory()
        details = CityDefenseDetails.objects.create(project=project, area=area)
        failure = CheckOutcomeFactory(success_level=-1)
        partial = CheckOutcomeFactory(success_level=0)
        success = CheckOutcomeFactory(success_level=1)
        CityDefenseTierThreshold.objects.create(
            details=details, outcome_tier=failure, min_progress=0
        )
        CityDefenseTierThreshold.objects.create(
            details=details, outcome_tier=partial, min_progress=25
        )
        CityDefenseTierThreshold.objects.create(
            details=details, outcome_tier=success, min_progress=50
        )

        thresholds = list(details.tier_thresholds.all())
        self.assertEqual(_select_tier(thresholds, 0).outcome_tier, failure)
        self.assertEqual(_select_tier(thresholds, 25).outcome_tier, partial)
        self.assertEqual(_select_tier(thresholds, 49).outcome_tier, partial)
        self.assertEqual(_select_tier(thresholds, 50).outcome_tier, success)
        self.assertEqual(_select_tier(thresholds, 999).outcome_tier, success)


class GetCityDefenseIntegrityBonusTests(TestCase):
    def test_no_project_returns_zero(self) -> None:
        area = AreaFactory()
        self.assertEqual(get_city_defense_integrity_bonus(area), 0)

    def test_applied_with_award_returns_bonus(self) -> None:
        area = AreaFactory()
        success = CheckOutcomeFactory(success_level=1)
        project = ProjectFactory(
            kind=ProjectKind.CITY_DEFENSE,
            completion_mode=CompletionMode.TIERED_PERIOD,
            owner_persona=PersonaFactory(),
        )
        CityDefenseDetails.objects.create(
            project=project,
            area=area,
            outcome_tier=success,
            applied_at=timezone.now(),
        )
        CityDefenseIntegrityBonus.objects.create(outcome_tier=success, integrity_bonus=50)

        self.assertEqual(get_city_defense_integrity_bonus(area), 50)

    def test_applied_without_award_row_returns_zero(self) -> None:
        area = AreaFactory()
        success = CheckOutcomeFactory(success_level=1)
        project = ProjectFactory(
            kind=ProjectKind.CITY_DEFENSE,
            completion_mode=CompletionMode.TIERED_PERIOD,
            owner_persona=PersonaFactory(),
        )
        CityDefenseDetails.objects.create(
            project=project,
            area=area,
            outcome_tier=success,
            applied_at=timezone.now(),
        )
        # No CityDefenseIntegrityBonus row for this tier.
        self.assertEqual(get_city_defense_integrity_bonus(area), 0)

    def test_not_yet_applied_returns_zero(self) -> None:
        area = AreaFactory()
        project = ProjectFactory(
            kind=ProjectKind.CITY_DEFENSE,
            completion_mode=CompletionMode.TIERED_PERIOD,
            owner_persona=PersonaFactory(),
        )
        CityDefenseDetails.objects.create(project=project, area=area)
        # applied_at is None — not graded yet.
        self.assertEqual(get_city_defense_integrity_bonus(area), 0)

    def test_most_recent_applied_wins(self) -> None:
        area = AreaFactory()
        success = CheckOutcomeFactory(success_level=1)
        critical = CheckOutcomeFactory(success_level=2)

        project1 = ProjectFactory(
            kind=ProjectKind.CITY_DEFENSE,
            completion_mode=CompletionMode.TIERED_PERIOD,
            owner_persona=PersonaFactory(),
        )
        CityDefenseDetails.objects.create(
            project=project1,
            area=area,
            outcome_tier=success,
            applied_at=timezone.now() - datetime.timedelta(hours=1),
        )

        project2 = ProjectFactory(
            kind=ProjectKind.CITY_DEFENSE,
            completion_mode=CompletionMode.TIERED_PERIOD,
            owner_persona=PersonaFactory(),
        )
        CityDefenseDetails.objects.create(
            project=project2,
            area=area,
            outcome_tier=critical,
            applied_at=timezone.now(),
        )
        CityDefenseIntegrityBonus.objects.create(outcome_tier=success, integrity_bonus=50)
        CityDefenseIntegrityBonus.objects.create(outcome_tier=critical, integrity_bonus=100)

        # The most recently applied project wins.
        self.assertEqual(get_city_defense_integrity_bonus(area), 100)


class CompleteCityDefenseTests(TestCase):
    def test_stores_tier_and_sets_applied_at(self) -> None:
        area = AreaFactory()
        project = ProjectFactory(
            kind=ProjectKind.CITY_DEFENSE,
            completion_mode=CompletionMode.TIERED_PERIOD,
            owner_persona=PersonaFactory(),
        )
        details = CityDefenseDetails.objects.create(project=project, area=area)
        success = CheckOutcomeFactory(success_level=1)

        complete_city_defense(project, success)

        # The handler sets outcome_tier via instance mutation (visible on the
        # cached SharedMemoryModel), but applied_at via queryset .update()
        # (bypasses the cache). Read applied_at directly from the DB to verify.
        self.assertEqual(details.outcome_tier, success)
        raw = CityDefenseDetails.objects.values("applied_at", "outcome_tier_id").get(
            project=project
        )
        self.assertIsNotNone(raw["applied_at"])
        self.assertEqual(raw["outcome_tier_id"], success.pk)

    def test_idempotent_second_call_no_op(self) -> None:
        area = AreaFactory()
        project = ProjectFactory(
            kind=ProjectKind.CITY_DEFENSE,
            completion_mode=CompletionMode.TIERED_PERIOD,
            owner_persona=PersonaFactory(),
        )
        CityDefenseDetails.objects.create(project=project, area=area)
        success = CheckOutcomeFactory(success_level=1)
        failure = CheckOutcomeFactory(success_level=-1)

        complete_city_defense(project, success)
        raw = CityDefenseDetails.objects.values("applied_at", "outcome_tier_id").get(
            project=project
        )
        first_applied = raw["applied_at"]
        first_tier = raw["outcome_tier_id"]
        self.assertIsNotNone(first_applied)

        # Second call with a different tier should not overwrite.
        complete_city_defense(project, failure)
        raw = CityDefenseDetails.objects.values("applied_at", "outcome_tier_id").get(
            project=project
        )
        self.assertEqual(raw["outcome_tier_id"], first_tier)
        self.assertEqual(raw["applied_at"], first_applied)


class ResolveCityDefenseTests(TestCase):
    def setUp(self) -> None:
        register_kind_handler(ProjectKind.CITY_DEFENSE, complete_city_defense)

    def tearDown(self) -> None:
        clear_kind_handlers()
        clear_tiered_resolvers()

    def test_grades_by_progress_and_resolves(self) -> None:
        area = AreaFactory()
        project = ProjectFactory(
            kind=ProjectKind.CITY_DEFENSE,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.RESOLVING,
            owner_persona=PersonaFactory(),
            current_progress=50,
        )
        details = CityDefenseDetails.objects.create(project=project, area=area)
        failure = CheckOutcomeFactory(success_level=-1)
        success = CheckOutcomeFactory(success_level=1)
        CityDefenseTierThreshold.objects.create(
            details=details, outcome_tier=failure, min_progress=0
        )
        CityDefenseTierThreshold.objects.create(
            details=details, outcome_tier=success, min_progress=50
        )

        resolve_city_defense(project)

        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        self.assertEqual(project.outcome_tier, success)
        raw = CityDefenseDetails.objects.values("applied_at", "outcome_tier_id").get(
            project=project
        )
        self.assertEqual(raw["outcome_tier_id"], success.pk)
        self.assertIsNotNone(raw["applied_at"])


class StartCityDefenseProjectTests(TestCase):
    def test_creates_project_details_and_thresholds(self) -> None:
        area = AreaFactory()
        persona = PersonaFactory()
        failure = CheckOutcomeFactory(success_level=-1)
        success = CheckOutcomeFactory(success_level=1)
        thresholds = [(failure, 0), (success, 50)]

        project = start_city_defense_project(
            area=area, owner_persona=persona, tier_thresholds=thresholds, period_days=14
        )

        self.assertEqual(project.kind, ProjectKind.CITY_DEFENSE)
        self.assertEqual(project.completion_mode, CompletionMode.TIERED_PERIOD)
        self.assertEqual(project.owner_persona, persona)
        self.assertIsNone(project.threshold_target)
        self.assertEqual(project.city_defense_details.area, area)
        self.assertEqual(project.city_defense_details.tier_thresholds.count(), 2)
        self.assertAlmostEqual(
            (project.time_limit - project.started_at).total_seconds(), 14 * 86400, delta=5
        )


class ScanJourneyTests(TestCase):
    """Full journey: scan grades at deadline, then create_fortification applies bonus."""

    def setUp(self) -> None:
        register_kind_handler(ProjectKind.CITY_DEFENSE, complete_city_defense)
        register_tiered_resolver(ProjectKind.CITY_DEFENSE, resolve_city_defense)

    def tearDown(self) -> None:
        clear_kind_handlers()
        clear_tiered_resolvers()

    def test_scan_grades_and_fortification_gets_bonus(self) -> None:
        area = AreaFactory()
        persona = PersonaFactory()
        failure = CheckOutcomeFactory(success_level=-1)
        success = CheckOutcomeFactory(success_level=1)
        thresholds = [(failure, 0), (success, 50)]

        project = start_city_defense_project(
            area=area, owner_persona=persona, tier_thresholds=thresholds, period_days=30
        )
        project.current_progress = 60  # Success tier
        project.time_limit = timezone.now() - datetime.timedelta(seconds=1)
        project.save(update_fields=["current_progress", "time_limit"])

        CityDefenseIntegrityBonus.objects.create(outcome_tier=success, integrity_bonus=40)

        scan_active_projects()

        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        self.assertEqual(project.outcome_tier, success)

        # Now create a battle in that area and verify the fortification bonus.
        battle = BattleFactory(region=area)
        defender = BattleSideFactory(battle=battle)
        place = BattlePlaceFactory(battle=battle)
        fort = create_fortification(
            place=place, defending_side=defender, kind=FortificationKind.WALL
        )

        expected = BASE_INTEGRITY[FortificationKind.WALL] + 40
        self.assertEqual(fort.max_integrity, expected)
        self.assertEqual(fort.integrity, expected)

    def test_no_bonus_without_battle_region(self) -> None:
        """A battle with no region gets no city-defense bonus (existing behavior)."""
        battle = BattleFactory(region=None)
        defender = BattleSideFactory(battle=battle)
        place = BattlePlaceFactory(battle=battle)
        fort = create_fortification(
            place=place, defending_side=defender, kind=FortificationKind.WALL
        )

        expected = BASE_INTEGRITY[FortificationKind.WALL]
        self.assertEqual(fort.max_integrity, expected)

    def test_explicit_max_integrity_not_boosted(self) -> None:
        """When max_integrity is explicitly passed (blueprint staging), no bonus applied."""
        area = AreaFactory()
        success = CheckOutcomeFactory(success_level=1)
        project = ProjectFactory(
            kind=ProjectKind.CITY_DEFENSE,
            completion_mode=CompletionMode.TIERED_PERIOD,
            owner_persona=PersonaFactory(),
        )
        CityDefenseDetails.objects.create(
            project=project, area=area, outcome_tier=success, applied_at=timezone.now()
        )
        CityDefenseIntegrityBonus.objects.create(outcome_tier=success, integrity_bonus=40)

        battle = BattleFactory(region=area)
        defender = BattleSideFactory(battle=battle)
        place = BattlePlaceFactory(battle=battle)
        fort = create_fortification(
            place=place, defending_side=defender, kind=FortificationKind.WALL, max_integrity=150
        )

        # Explicit value is not modified.
        self.assertEqual(fort.max_integrity, 150)
