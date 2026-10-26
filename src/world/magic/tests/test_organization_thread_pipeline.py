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
    def test_effective_cap_is_lower_of_grant_and_level(self):
        """The anchor cap is the org grant alone; the level cap binds in the effective cap.

        #4585: compute_anchor_cap no longer folds in a Path-stage cap. A level-1 owner
        (no class level) is held to 10 by the level cap; a level-5 owner is held to the
        grant's 30.
        """
        from world.magic.services import compute_effective_cap

        org = OrganizationFactory()
        resonance = ResonanceFactory()
        gift = GiftFactory()
        gift.resonances.add(resonance)
        OrganizationGiftGrant.objects.create(organization=org, gift=gift, anchor_cap=30)
        for class_level, effective in ((None, 10), (5, 30)):
            sheet = CharacterSheetFactory(_class_level=class_level)
            thread = Thread.objects.create(
                owner=sheet,
                resonance=resonance,
                target_kind=TargetKind.ORGANIZATION,
                target_organization=org,
            )
            self.assertEqual(compute_anchor_cap(thread), 30)
            self.assertEqual(compute_effective_cap(thread), effective)

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
