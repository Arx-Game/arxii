"""Integration tests for the cron-driven Project lifecycle."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.projects.constants import (
    CompletionMode,
    ProjectKind,
    ProjectStatus,
)
from world.projects.factories import ProjectFactory
from world.projects.services import (
    clear_kind_handlers,
    register_kind_handler,
    scan_active_projects,
)


class SingleThresholdLifecycleTests(TestCase):
    def setUp(self) -> None:
        clear_kind_handlers()
        register_kind_handler(ProjectKind.TEST_KIND, lambda _project, _tier: None)

    def test_threshold_hit_schedules_resolution(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            status=ProjectStatus.ACTIVE,
            current_progress=100,
            threshold_target=100,
            time_limit=timezone.now() + timedelta(days=7),
        )
        scan_active_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.RESOLVING)

    def test_time_limit_passed_schedules_resolution(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            status=ProjectStatus.ACTIVE,
            current_progress=50,
            threshold_target=100,
            time_limit=timezone.now() - timedelta(hours=1),
        )
        scan_active_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.RESOLVING)

    def test_under_threshold_within_time_stays_active(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            status=ProjectStatus.ACTIVE,
            current_progress=50,
            threshold_target=100,
            time_limit=timezone.now() + timedelta(days=7),
        )
        scan_active_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.ACTIVE)


class TieredPeriodLifecycleTests(TestCase):
    def setUp(self) -> None:
        clear_kind_handlers()
        register_kind_handler(ProjectKind.TEST_KIND, lambda _project, _tier: None)

    def test_tiered_period_only_resolves_at_deadline(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.ACTIVE,
            current_progress=9999,
            threshold_target=None,
            time_limit=timezone.now() + timedelta(days=7),
        )
        scan_active_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.ACTIVE)

    def test_tiered_period_resolves_at_deadline(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.TIERED_PERIOD,
            status=ProjectStatus.ACTIVE,
            current_progress=50,
            threshold_target=None,
            time_limit=timezone.now() - timedelta(hours=1),
        )
        scan_active_projects()
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.RESOLVING)
