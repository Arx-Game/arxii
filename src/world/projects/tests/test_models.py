"""Tests for Project and Contribution models."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from world.projects.constants import (
    CompletionMode,
    ContributionKind,
    ContributionPrivacy,
    ProjectKind,
    ProjectStatus,
)
from world.projects.factories import ContributionFactory, ProjectFactory
from world.traits.models import CheckOutcome


class ProjectModelTests(TestCase):
    def test_project_creation_defaults(self) -> None:
        project = ProjectFactory()
        self.assertEqual(project.status, ProjectStatus.PLANNING)
        self.assertEqual(project.current_progress, 0)
        self.assertIsNone(project.outcome_tier)

    def test_single_threshold_project_requires_threshold_target(self) -> None:
        project = ProjectFactory.build(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            threshold_target=None,
            time_limit=timezone.now() + timedelta(days=7),
        )
        with self.assertRaises(ValidationError):
            project.full_clean()

    def test_tiered_period_project_allows_null_threshold_target(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            completion_mode=CompletionMode.TIERED_PERIOD,
            threshold_target=None,
            time_limit=timezone.now() + timedelta(days=7),
        )
        self.assertIsNone(project.threshold_target)


class ContributionModelTests(TestCase):
    def test_ap_contribution_populates_ap_amount(self) -> None:
        contribution = ContributionFactory(kind=ContributionKind.AP, ap_amount=3)
        self.assertEqual(contribution.ap_amount, 3)
        self.assertIsNone(contribution.money_amount)

    def test_money_contribution_populates_money_amount(self) -> None:
        contribution = ContributionFactory(
            kind=ContributionKind.MONEY, money_amount=500, ap_amount=None
        )
        self.assertEqual(contribution.money_amount, 500)
        self.assertIsNone(contribution.ap_amount)

    def test_kind_discriminator_validation(self) -> None:
        contribution = ContributionFactory.build(
            kind=ContributionKind.AP, ap_amount=None, money_amount=None
        )
        with self.assertRaises(ValidationError):
            contribution.full_clean()

    def test_default_privacy_is_private(self) -> None:
        contribution = ContributionFactory()
        self.assertEqual(contribution.privacy_setting, ContributionPrivacy.PRIVATE)


class ContributionCheckOutcomeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.success_outcome, _ = CheckOutcome.objects.get_or_create(
            name="Success", defaults={"success_level": 1}
        )

    def test_check_contribution_populates_check_outcome(self) -> None:
        contribution = ContributionFactory(
            kind=ContributionKind.CHECK,
            ap_amount=None,
            check_outcome=self.success_outcome,
        )
        self.assertEqual(contribution.check_outcome.name, "Success")

    def test_check_contribution_requires_check_outcome(self) -> None:
        contribution = ContributionFactory.build(
            kind=ContributionKind.CHECK,
            ap_amount=None,
            check_outcome=None,
        )
        with self.assertRaises(ValidationError):
            contribution.full_clean()
