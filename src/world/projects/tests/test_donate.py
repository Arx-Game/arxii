"""Tests for donate_to_project — money contribution from a character's purse (#1574)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.currency.models import CharacterPurse
from world.projects.constants import ContributionKind, ProjectStatus
from world.projects.factories import ProjectFactory
from world.projects.models import Contribution
from world.projects.services import ProjectNotActiveError, donate_to_project
from world.scenes.factories import PersonaFactory


class DonateToProjectTests(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory(status=ProjectStatus.ACTIVE, threshold_target=100)
        self.donor = PersonaFactory()
        self.purse = CharacterPurse.objects.create(
            character_sheet=self.donor.character_sheet, balance=10_000
        )

    def test_debits_purse_records_contribution_and_advances_progress(self) -> None:
        donate_to_project(self.project, donor_persona=self.donor, amount=5_000)

        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 5_000)  # 10_000 - 5_000

        contribution = Contribution.objects.get(project=self.project)
        self.assertEqual(contribution.kind, ContributionKind.MONEY)
        self.assertEqual(contribution.money_amount, 5_000)
        self.assertEqual(contribution.contributor_persona, self.donor)

        self.project.refresh_from_db()
        self.assertEqual(self.project.current_progress, 50)  # 5_000 // 100

    def test_insufficient_funds_raises_and_rolls_back(self) -> None:
        with self.assertRaises(ValidationError):
            donate_to_project(self.project, donor_persona=self.donor, amount=999_999)
        # Atomic: neither the spend nor the contribution landed.
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 10_000)
        self.assertFalse(Contribution.objects.filter(project=self.project).exists())

    def test_donating_to_an_inactive_project_raises_and_rolls_back(self) -> None:
        planning = ProjectFactory(status=ProjectStatus.PLANNING, threshold_target=100)
        with self.assertRaises(ProjectNotActiveError):
            donate_to_project(planning, donor_persona=self.donor, amount=100)
        # The status pre-check fires before any debit.
        self.purse.refresh_from_db()
        self.assertEqual(self.purse.balance, 10_000)


class DonateToProjectActionTests(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory(status=ProjectStatus.ACTIVE, threshold_target=100)
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        # Present as this persona so active_persona_for_sheet resolves it.
        self.sheet.active_persona = self.persona
        self.sheet.save(update_fields=["active_persona"])
        CharacterPurse.objects.create(character_sheet=self.sheet, balance=10_000)
        self.actor = self.sheet.character

    def test_action_donates_and_advances_progress(self) -> None:
        from actions.definitions.projects import DonateToProjectAction

        result = DonateToProjectAction().execute(
            self.actor, project_id=self.project.pk, amount=5_000
        )
        self.assertTrue(result.success, result.message)
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_progress, 50)

    def test_action_unknown_project_fails_gracefully(self) -> None:
        from actions.definitions.projects import DonateToProjectAction

        result = DonateToProjectAction().execute(self.actor, project_id=999_999, amount=100)
        self.assertFalse(result.success)
        self.assertIn("No such project", result.message)
