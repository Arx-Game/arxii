"""Tests for the projects framework service functions."""

from django.test import TestCase

from world.projects.constants import (
    ContributionKind,
    ProjectKind,
    ProjectStatus,
)
from world.projects.factories import ProjectFactory
from world.projects.models import Contribution
from world.projects.services import (
    ProjectNotActiveError,
    add_contribution,
    clear_kind_handlers,
    get_kind_handler,
    register_kind_handler,
    resolve_project,
)
from world.scenes.factories import PersonaFactory
from world.traits.models import CheckOutcome


class AddContributionTests(TestCase):
    def test_ap_contribution_advances_progress(self) -> None:
        project = ProjectFactory(status=ProjectStatus.ACTIVE, current_progress=0)
        contributor = PersonaFactory()
        add_contribution(
            project=project,
            contributor_persona=contributor,
            kind=ContributionKind.AP,
            ap_amount=5,
            intent_text="putting my back into it",
        )
        project.refresh_from_db()
        self.assertEqual(project.current_progress, 5)
        self.assertEqual(Contribution.objects.filter(project=project).count(), 1)

    def test_money_contribution_advances_progress_by_100s(self) -> None:
        project = ProjectFactory(status=ProjectStatus.ACTIVE, current_progress=0)
        contributor = PersonaFactory()
        add_contribution(
            project=project,
            contributor_persona=contributor,
            kind=ContributionKind.MONEY,
            money_amount=500,
            ap_amount=None,
        )
        project.refresh_from_db()
        self.assertEqual(project.current_progress, 5)

    def test_inactive_project_rejects_contribution(self) -> None:
        project = ProjectFactory(status=ProjectStatus.PLANNING, current_progress=0)
        contributor = PersonaFactory()
        with self.assertRaises(ProjectNotActiveError):
            add_contribution(
                project=project,
                contributor_persona=contributor,
                kind=ContributionKind.AP,
                ap_amount=5,
            )


class KindHandlerRegistryTests(TestCase):
    def setUp(self) -> None:
        clear_kind_handlers()

    def test_register_and_lookup_handler(self) -> None:
        def fake_handler(project, outcome_tier):
            return None

        register_kind_handler(ProjectKind.TEST_KIND, fake_handler)
        self.assertIs(get_kind_handler(ProjectKind.TEST_KIND), fake_handler)

    def test_missing_handler_raises(self) -> None:
        with self.assertRaises(LookupError):
            get_kind_handler("NONEXISTENT_KIND")


class ResolveProjectTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.success_outcome, _ = CheckOutcome.objects.get_or_create(
            name="Success", defaults={"success_level": 1}
        )
        cls.failed_outcome, _ = CheckOutcome.objects.get_or_create(
            name="Failed", defaults={"success_level": -1}
        )

    def setUp(self) -> None:
        clear_kind_handlers()
        self.handler_calls = []

        def test_handler(project, outcome_tier):
            self.handler_calls.append((project.pk, outcome_tier))

        register_kind_handler(ProjectKind.TEST_KIND, test_handler)

    def test_resolve_calls_handler_and_completes(self) -> None:
        project = ProjectFactory(kind=ProjectKind.TEST_KIND, status=ProjectStatus.RESOLVING)
        resolve_project(project, outcome_tier=self.success_outcome)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        self.assertEqual(project.outcome_tier_id, self.success_outcome.pk)
        self.assertEqual(len(self.handler_calls), 1)

    def test_resolve_failed_outcome_sets_failed_status(self) -> None:
        project = ProjectFactory(kind=ProjectKind.TEST_KIND, status=ProjectStatus.RESOLVING)
        resolve_project(project, outcome_tier=self.failed_outcome)
        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.FAILED)

    def test_resolve_non_resolving_project_raises(self) -> None:
        project = ProjectFactory(kind=ProjectKind.TEST_KIND, status=ProjectStatus.ACTIVE)
        with self.assertRaises(ValueError):
            resolve_project(project, outcome_tier=self.success_outcome)
