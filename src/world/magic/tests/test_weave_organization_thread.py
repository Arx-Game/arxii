"""Tests for weaving an ORGANIZATION-anchored thread."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import WeavingUnlockMissing
from world.magic.factories import GiftFactory, ResonanceFactory
from world.magic.models import (
    CharacterTechnique,
    CharacterThreadWeavingUnlock,
    Thread,
    ThreadWeavingUnlock,
)
from world.magic.services.threads import weave_thread
from world.societies.factories import OrganizationFactory
from world.societies.models import OrganizationGiftGrant, OrganizationMembership


class WeaveOrganizationThreadTests(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.org = OrganizationFactory()
        self.resonance = ResonanceFactory()
        self.gift = GiftFactory()
        self.gift.resonances.add(self.resonance)
        # Grant the org the gift
        OrganizationGiftGrant.objects.create(organization=self.org, gift=self.gift, anchor_cap=30)
        # Grant the character the ORGANIZATION weaving unlock
        unlock = ThreadWeavingUnlock.objects.create(
            target_kind=TargetKind.ORGANIZATION, xp_cost=100
        )
        CharacterThreadWeavingUnlock.objects.create(
            character=self.sheet, unlock=unlock, xp_spent=100
        )

    def test_weave_rejects_without_membership(self):
        """Weaving without active membership raises WeavingUnlockMissing."""
        with self.assertRaises(WeavingUnlockMissing):
            weave_thread(
                character_sheet=self.sheet,
                target_kind=TargetKind.ORGANIZATION,
                target=self.org,
                resonance=self.resonance,
            )

    def test_weave_rejects_without_unlock(self):
        """Weaving without the ORGANIZATION unlock raises WeavingUnlockMissing."""
        # Create membership
        persona = self.sheet.primary_persona
        OrganizationMembership.objects.create(organization=self.org, persona=persona)
        # Remove the unlock
        CharacterThreadWeavingUnlock.objects.filter(character=self.sheet).delete()
        self.sheet.character.weaving_unlocks.invalidate()
        with self.assertRaises(WeavingUnlockMissing):
            weave_thread(
                character_sheet=self.sheet,
                target_kind=TargetKind.ORGANIZATION,
                target=self.org,
                resonance=self.resonance,
            )

    def test_weave_succeeds_with_membership_and_unlock(self):
        """Weaving with active membership + unlock creates a thread + techniques."""
        persona = self.sheet.primary_persona
        OrganizationMembership.objects.create(organization=self.org, persona=persona)
        thread = weave_thread(
            character_sheet=self.sheet,
            target_kind=TargetKind.ORGANIZATION,
            target=self.org,
            resonance=self.resonance,
        )
        self.assertEqual(thread.target_kind, TargetKind.ORGANIZATION)
        self.assertEqual(thread.target_organization, self.org)
        # Thread should exist
        self.assertTrue(
            Thread.objects.filter(
                owner=self.sheet,
                target_kind=TargetKind.ORGANIZATION,
                target_organization=self.org,
            ).exists()
        )

    def test_weave_mints_techniques_for_matching_resonance(self):
        """Weaving mints CharacterTechnique rows for matching-resonance gifts."""
        from world.magic.factories import TechniqueFactory

        technique = TechniqueFactory(gift=self.gift, level=1)
        persona = self.sheet.primary_persona
        OrganizationMembership.objects.create(organization=self.org, persona=persona)
        weave_thread(
            character_sheet=self.sheet,
            target_kind=TargetKind.ORGANIZATION,
            target=self.org,
            resonance=self.resonance,
        )
        self.assertTrue(
            CharacterTechnique.objects.filter(character=self.sheet, technique=technique).exists()
        )
