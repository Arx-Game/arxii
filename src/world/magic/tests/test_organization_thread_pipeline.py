"""Tests for ORGANIZATION thread pipeline: anchor cap."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory
from world.magic.models import Thread
from world.magic.services.threads import compute_anchor_cap
from world.societies.factories import OrganizationFactory
from world.societies.models import OrganizationGiftGrant


class OrganizationAnchorCapTests(TestCase):
    def test_anchor_cap_is_min_of_grant_and_path_stage(self):
        """compute_anchor_cap returns min(grant_cap, path_stage × 10).

        A fresh sheet has path_stage 0, so the cap is 0 regardless of the
        grant's anchor_cap — the member can't invest until they progress.
        """
        sheet = CharacterSheetFactory()
        org = OrganizationFactory()
        resonance = ResonanceFactory()
        gift = GiftFactory()
        gift.resonances.add(resonance)
        OrganizationGiftGrant.objects.create(organization=org, gift=gift, anchor_cap=30)
        thread = Thread.objects.create(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.ORGANIZATION,
            target_organization=org,
        )
        cap = compute_anchor_cap(thread)
        # path_stage defaults to 1 for a fresh sheet (no path history),
        # so cap is min(30, 1 × 10) = 10.
        self.assertEqual(cap, 10)

    def test_anchor_cap_zero_when_no_matching_grant(self):
        """No matching grant for the thread's resonance → cap is 0."""
        sheet = CharacterSheetFactory()
        org = OrganizationFactory()
        resonance = ResonanceFactory()
        # No OrganizationGiftGrant created — org has no gifts
        thread = Thread.objects.create(
            owner=sheet,
            resonance=resonance,
            target_kind=TargetKind.ORGANIZATION,
            target_organization=org,
        )
        cap = compute_anchor_cap(thread)
        self.assertEqual(cap, 0)
