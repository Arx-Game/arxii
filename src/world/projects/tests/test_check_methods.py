"""Tests for check-based contributions + ContributionMethod (#1574)."""

from __future__ import annotations

from django.test import TestCase

from world.action_points.factories import ActionPointPoolFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.projects.constants import ContributionKind, ProjectKind, ProjectStatus
from world.projects.factories import ProjectFactory
from world.projects.models import Contribution, ContributionMethod
from world.projects.services import (
    ContributionMethodError,
    contribute_check_to_project,
    set_contribution_story,
)
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory


class _CheckBase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory(
            kind=ProjectKind.BUILDING_CONSTRUCTION,
            status=ProjectStatus.ACTIVE,
            threshold_target=100,
        )
        self.method = ContributionMethod.objects.create(
            kind=ProjectKind.BUILDING_CONSTRUCTION,
            name="Carpentry",
            check_type=CheckTypeFactory(name="proj-carpentry"),
            ap_cost=5,
            progress_on_success=20,
        )
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.sheet.active_persona = self.persona
        self.sheet.save(update_fields=["active_persona"])
        self.actor = self.sheet.character
        self.pool = ActionPointPoolFactory(character=self.actor, current=100, maximum=200)
        self.success = CheckOutcomeFactory(name="proj-success", success_level=2)
        self.failure = CheckOutcomeFactory(name="proj-failure", success_level=-1)


class ContributeCheckTests(_CheckBase):
    def test_successful_check_spends_ap_and_advances_progress(self) -> None:
        with force_check_outcome(self.success):
            contribute_check_to_project(
                self.project, actor=self.actor, contributor_persona=self.persona, method=self.method
            )
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 95)
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_progress, 20)
        contribution = Contribution.objects.get(project=self.project)
        self.assertEqual(contribution.kind, ContributionKind.CHECK)
        self.assertEqual(contribution.contribution_method, self.method)

    def test_failed_check_spends_ap_but_does_not_advance(self) -> None:
        with force_check_outcome(self.failure):
            contribute_check_to_project(
                self.project, actor=self.actor, contributor_persona=self.persona, method=self.method
            )
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.current, 95)  # AP is spent on the attempt
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_progress, 0)

    def test_insufficient_ap_raises_and_rolls_back(self) -> None:
        self.pool.current = 2
        self.pool.save(update_fields=["current"])
        with self.assertRaises(ContributionMethodError), force_check_outcome(self.success):
            contribute_check_to_project(
                self.project, actor=self.actor, contributor_persona=self.persona, method=self.method
            )
        self.assertFalse(Contribution.objects.filter(project=self.project).exists())
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_progress, 0)

    def test_method_from_another_kind_is_rejected(self) -> None:
        wrong = ContributionMethod.objects.create(
            kind=ProjectKind.RESEARCH,
            name="Study",
            check_type=CheckTypeFactory(name="proj-study"),
            ap_cost=0,
            progress_on_success=10,
        )
        with self.assertRaises(ContributionMethodError):
            contribute_check_to_project(
                self.project, actor=self.actor, contributor_persona=self.persona, method=wrong
            )


class SetContributionStoryTests(_CheckBase):
    def test_story_attaches_to_latest_contribution(self) -> None:
        with force_check_outcome(self.success):
            contribute_check_to_project(
                self.project, actor=self.actor, contributor_persona=self.persona, method=self.method
            )
        updated = set_contribution_story(
            self.project, contributor_persona=self.persona, text="I raised the rafters."
        )
        assert updated is not None
        self.assertEqual(updated.intent_text, "I raised the rafters.")

    def test_story_without_a_contribution_returns_none(self) -> None:
        result = set_contribution_story(
            self.project, contributor_persona=self.persona, text="nothing yet"
        )
        self.assertIsNone(result)
