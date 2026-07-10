"""Tests for the PROPAGANDA project kind (#1621): launch → fund → renown fires once."""

from __future__ import annotations

from django.test import TestCase

from world.currency.models import CharacterPurse
from world.projects.constants import CompletionMode, ProjectKind, ProjectStatus
from world.projects.services import donate_to_project
from world.scenes.factories import PersonaFactory
from world.societies.constants import RenownMagnitude
from world.societies.models import PropagandaCampaignTier, PropagandaDetails
from world.societies.propaganda import (
    InactiveCampaignTierError,
    launch_propaganda_campaign,
    resolve_propaganda_project,
)


def _tier(**overrides) -> PropagandaCampaignTier:
    defaults = {
        "name": "Test Criers",
        "threshold_coppers": 1_000,
        "magnitude": RenownMagnitude.MODERATE,
        "display_order": 0,
        "is_active": True,
    }
    defaults.update(overrides)
    return PropagandaCampaignTier.objects.create(**defaults)


class LaunchPropagandaCampaignTests(TestCase):
    def setUp(self) -> None:
        self.sponsor = PersonaFactory()
        self.tier = _tier()

    def test_launch_creates_active_project_with_copied_config(self) -> None:
        project = launch_propaganda_campaign(
            owner_persona=self.sponsor, tier=self.tier, campaign_name="Sing My Praises"
        )
        self.assertEqual(project.kind, ProjectKind.PROPAGANDA)
        self.assertEqual(project.status, ProjectStatus.ACTIVE)
        self.assertEqual(project.completion_mode, CompletionMode.SINGLE_THRESHOLD)
        self.assertEqual(project.threshold_target, 10)  # 1_000 // 100
        details = PropagandaDetails.objects.get(project=project)
        self.assertEqual(details.campaign_name, "Sing My Praises")
        self.assertEqual(details.magnitude, RenownMagnitude.MODERATE)
        self.assertEqual(details.source_tier, self.tier)
        self.assertFalse(details.renown_fired)

    def test_tier_edits_never_mutate_live_campaigns(self) -> None:
        project = launch_propaganda_campaign(
            owner_persona=self.sponsor, tier=self.tier, campaign_name="Frozen Config"
        )
        self.tier.magnitude = RenownMagnitude.VERY_HIGH
        self.tier.save(update_fields=["magnitude"])
        details = PropagandaDetails.objects.get(project=project)
        self.assertEqual(details.magnitude, RenownMagnitude.MODERATE)

    def test_inactive_tier_rejected(self) -> None:
        self.tier.is_active = False
        self.tier.save(update_fields=["is_active"])
        with self.assertRaises(InactiveCampaignTierError):
            launch_propaganda_campaign(
                owner_persona=self.sponsor, tier=self.tier, campaign_name="Nope"
            )


class PropagandaCompletionTests(TestCase):
    """Funding to threshold instantly completes and fires the sponsor's renown."""

    def setUp(self) -> None:
        # Other suite modules reset the module-level kind-handler registry;
        # re-register like test_ransom_project.py does (same #1500 seam).
        from world.projects.services import (
            register_instant_completion_kind,
            register_kind_handler,
        )

        register_kind_handler(ProjectKind.PROPAGANDA, resolve_propaganda_project)
        register_instant_completion_kind(ProjectKind.PROPAGANDA)
        self.sponsor = PersonaFactory()
        self.donor = PersonaFactory()
        CharacterPurse.objects.create(character_sheet=self.donor.character_sheet, balance=50_000)
        self.tier = _tier()
        self.project = launch_propaganda_campaign(
            owner_persona=self.sponsor, tier=self.tier, campaign_name="The Grand Claim"
        )

    def test_funding_to_threshold_completes_and_fires_renown(self) -> None:
        before = self.sponsor.fame_points
        donate_to_project(self.project, donor_persona=self.donor, amount=1_000)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.COMPLETED)
        details = PropagandaDetails.objects.get(project=self.project)
        self.assertTrue(details.renown_fired)
        self.sponsor.refresh_from_db()
        self.assertGreater(self.sponsor.fame_points, before)

    def test_partial_funding_neither_completes_nor_fires(self) -> None:
        donate_to_project(self.project, donor_persona=self.donor, amount=300)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.ACTIVE)
        self.assertFalse(PropagandaDetails.objects.get(project=self.project).renown_fired)

    def test_handler_is_idempotent(self) -> None:
        donate_to_project(self.project, donor_persona=self.donor, amount=1_000)
        self.sponsor.refresh_from_db()
        after_first = self.sponsor.fame_points
        self.project.refresh_from_db()
        resolve_propaganda_project(self.project, None)
        self.sponsor.refresh_from_db()
        self.assertEqual(self.sponsor.fame_points, after_first)

    def test_underfunded_deadline_resolution_awards_nothing(self) -> None:
        donate_to_project(self.project, donor_persona=self.donor, amount=300)
        before = self.sponsor.fame_points
        self.project.refresh_from_db()
        resolve_propaganda_project(self.project, None)
        self.sponsor.refresh_from_db()
        self.assertEqual(self.sponsor.fame_points, before)
        self.assertFalse(PropagandaDetails.objects.get(project=self.project).renown_fired)


class PropagandaSeedTests(TestCase):
    def test_seed_idempotent_and_upserting(self) -> None:
        from world.seeds.propaganda import seed_propaganda_content

        seed_propaganda_content()
        seed_propaganda_content()
        self.assertEqual(PropagandaCampaignTier.objects.count(), 3)
        street = PropagandaCampaignTier.objects.get(name="Street Criers")
        street.threshold_coppers = 1
        street.save(update_fields=["threshold_coppers"])
        seed_propaganda_content()
        street.refresh_from_db()
        self.assertEqual(street.threshold_coppers, 5_000)
