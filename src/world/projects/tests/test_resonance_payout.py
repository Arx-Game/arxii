"""Tests for the PROJECT_CONTRIBUTION resonance payout hook (#2038).

Covers the approved spec's 7 acceptance criteria: an opted-in ProjectKind (via
ProjectKindResonanceAward) grants resonance on every contribution, a project with
no opt-in row (or amount=0) is unaffected, an opted-in project missing
project.resonance logs a warning and does not raise, and repeat contributions
from the same contributor to the same project each grant independently
(uncapped, per Tehom's ruling).
"""

from django.test import TestCase

from world.magic.constants import GainSource
from world.magic.factories import ResonanceFactory
from world.magic.models import ResonanceGrant
from world.projects.constants import ContributionKind, ProjectKind, ProjectStatus
from world.projects.factories import ProjectFactory
from world.projects.models import ProjectKindResonanceAward
from world.projects.services import add_contribution
from world.scenes.factories import PersonaFactory


class ProjectContributionResonancePayoutTests(TestCase):
    def test_opted_in_kind_with_resonance_grants_on_contribution(self) -> None:
        """Criterion 1: opted-in kind + resonance set grants the award amount."""
        resonance = ResonanceFactory()
        project = ProjectFactory(
            kind=ProjectKind.ORGANIZATION_CAPABILITY,
            status=ProjectStatus.ACTIVE,
            resonance=resonance,
        )
        ProjectKindResonanceAward.objects.create(
            kind=ProjectKind.ORGANIZATION_CAPABILITY, resonance_award_amount=5
        )
        contributor = PersonaFactory()

        add_contribution(
            project=project,
            contributor_persona=contributor,
            kind=ContributionKind.AP,
            ap_amount=3,
        )

        grants = ResonanceGrant.objects.filter(
            source=GainSource.PROJECT_CONTRIBUTION, source_project=project
        )
        self.assertEqual(grants.count(), 1)
        grant = grants.first()
        self.assertEqual(grant.amount, 5)
        self.assertEqual(grant.character_sheet_id, contributor.character_sheet_id)
        self.assertEqual(grant.resonance_id, resonance.pk)

    def test_kind_with_no_award_row_grants_nothing(self) -> None:
        """Criterion 2: no ProjectKindResonanceAward row -> no grant, no error."""
        resonance = ResonanceFactory()
        project = ProjectFactory(
            kind=ProjectKind.TEST_KIND,
            status=ProjectStatus.ACTIVE,
            resonance=resonance,
        )
        contributor = PersonaFactory()

        add_contribution(
            project=project,
            contributor_persona=contributor,
            kind=ContributionKind.AP,
            ap_amount=3,
        )

        self.assertEqual(
            ResonanceGrant.objects.filter(source=GainSource.PROJECT_CONTRIBUTION).count(), 0
        )

    def test_award_amount_zero_grants_nothing(self) -> None:
        """Criterion 2 (amount=0 branch): a zero-amount row behaves as opted-out."""
        resonance = ResonanceFactory()
        project = ProjectFactory(
            kind=ProjectKind.ORGANIZATION_CAPABILITY,
            status=ProjectStatus.ACTIVE,
            resonance=resonance,
        )
        ProjectKindResonanceAward.objects.create(
            kind=ProjectKind.ORGANIZATION_CAPABILITY, resonance_award_amount=0
        )
        contributor = PersonaFactory()

        add_contribution(
            project=project,
            contributor_persona=contributor,
            kind=ContributionKind.AP,
            ap_amount=3,
        )

        self.assertEqual(
            ResonanceGrant.objects.filter(source=GainSource.PROJECT_CONTRIBUTION).count(), 0
        )

    def test_opted_in_kind_without_project_resonance_logs_and_skips(self) -> None:
        """Criterion 3: resonance unset -> logged skip, contribution proceeds unaffected."""
        project = ProjectFactory(
            kind=ProjectKind.ORGANIZATION_CAPABILITY,
            status=ProjectStatus.ACTIVE,
            resonance=None,
        )
        ProjectKindResonanceAward.objects.create(
            kind=ProjectKind.ORGANIZATION_CAPABILITY, resonance_award_amount=5
        )
        contributor = PersonaFactory()

        with self.assertLogs("world.projects.services", level="WARNING") as logs:
            contribution = add_contribution(
                project=project,
                contributor_persona=contributor,
                kind=ContributionKind.AP,
                ap_amount=3,
            )

        self.assertTrue(any("resonance" in message.lower() for message in logs.output))
        project.refresh_from_db()
        self.assertEqual(project.current_progress, 3)
        self.assertIsNotNone(contribution.pk)
        self.assertEqual(
            ResonanceGrant.objects.filter(source=GainSource.PROJECT_CONTRIBUTION).count(), 0
        )

    def test_seed_row_exists_for_organization_capability(self) -> None:
        """Criterion 4: seed content — the ensure_* seeder creates the default row."""
        from world.projects.seeds import ensure_project_kind_resonance_awards

        ensure_project_kind_resonance_awards()

        award = ProjectKindResonanceAward.objects.get(kind=ProjectKind.ORGANIZATION_CAPABILITY)
        self.assertEqual(award.resonance_award_amount, 5)

        # Idempotent: calling again does not duplicate or reset a staff edit.
        award.resonance_award_amount = 9
        award.save(update_fields=["resonance_award_amount"])
        ensure_project_kind_resonance_awards()
        award.refresh_from_db()
        self.assertEqual(award.resonance_award_amount, 9)
        self.assertEqual(
            ProjectKindResonanceAward.objects.filter(
                kind=ProjectKind.ORGANIZATION_CAPABILITY
            ).count(),
            1,
        )

    def test_repeat_contributions_each_grant_independently_uncapped(self) -> None:
        """Criterion 7: repeat contributions from the same contributor each pay out."""
        resonance = ResonanceFactory()
        project = ProjectFactory(
            kind=ProjectKind.ORGANIZATION_CAPABILITY,
            status=ProjectStatus.ACTIVE,
            resonance=resonance,
        )
        ProjectKindResonanceAward.objects.create(
            kind=ProjectKind.ORGANIZATION_CAPABILITY, resonance_award_amount=5
        )
        contributor = PersonaFactory()

        for _ in range(3):
            add_contribution(
                project=project,
                contributor_persona=contributor,
                kind=ContributionKind.AP,
                ap_amount=1,
            )

        grants = ResonanceGrant.objects.filter(
            source=GainSource.PROJECT_CONTRIBUTION, source_project=project
        )
        self.assertEqual(grants.count(), 3)
        self.assertEqual(sum(g.amount for g in grants), 15)
