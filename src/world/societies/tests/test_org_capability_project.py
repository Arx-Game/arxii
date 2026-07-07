"""Tests for ORGANIZATION_CAPABILITY project resolver."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.magic.factories import GiftFactory
from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.projects.models import Project
from world.societies.factories import OrganizationFactory
from world.societies.models import OrganizationGiftGrant
from world.societies.org_capability import (
    OrganizationCapabilityProjectDetails,
    resolve_organization_capability,
)


class OrganizationCapabilityResolverTests(TestCase):
    def _make_project(self, org, gift, anchor_cap=30):
        from world.scenes.factories import PersonaFactory

        project = Project.objects.create(
            kind=ProjectKind.ORGANIZATION_CAPABILITY,
            completion_mode=CompletionMode.SINGLE_THRESHOLD,
            status=ProjectStatus.RESOLVING,
            owner_persona=PersonaFactory(),
            started_at=timezone.now(),
            time_limit=timezone.now() + timedelta(days=7),
            threshold_target=100,
            current_progress=100,
        )
        OrganizationCapabilityProjectDetails.objects.create(
            project=project,
            gift=gift,
            anchor_cap=anchor_cap,
            organization=org,
        )
        return project

    def test_resolver_creates_gift_grant(self):
        """resolve_organization_capability creates an OrganizationGiftGrant."""
        org = OrganizationFactory()
        gift = GiftFactory()
        project = self._make_project(org, gift, anchor_cap=30)

        resolve_organization_capability(project, outcome_tier=None)

        grant = OrganizationGiftGrant.objects.get(organization=org, gift=gift)
        self.assertEqual(grant.anchor_cap, 30)
        self.assertEqual(grant.project, project)

    def test_resolver_is_idempotent(self):
        """Re-resolving the same project does not create a duplicate grant."""
        org = OrganizationFactory()
        gift = GiftFactory()
        project = self._make_project(org, gift)

        resolve_organization_capability(project, outcome_tier=None)
        resolve_organization_capability(project, outcome_tier=None)

        self.assertEqual(
            OrganizationGiftGrant.objects.filter(organization=org, gift=gift).count(),
            1,
        )

    def test_unique_constraint_one_grant_per_org_gift(self):
        """Two grants for the same (org, gift) are forbidden."""
        from django.db.utils import IntegrityError

        org = OrganizationFactory()
        gift = GiftFactory()
        OrganizationGiftGrant.objects.create(organization=org, gift=gift, anchor_cap=20)
        with self.assertRaises(IntegrityError):
            OrganizationGiftGrant.objects.create(organization=org, gift=gift, anchor_cap=30)
