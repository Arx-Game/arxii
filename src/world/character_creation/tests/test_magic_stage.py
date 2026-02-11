"""
Tests for magic stage completion in character creation.

Uses the Draft* models (DraftGift, DraftTechnique, DraftMotif, DraftAnimaRitual)
which are separate from the finalized magic models.
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import (
    CharacterDraftFactory,
    DraftAnimaRitualFactory,
    DraftGiftFactory,
    DraftMotifFactory,
    DraftMotifResonanceFactory,
    DraftTechniqueFactory,
)
from world.character_creation.models import (
    CharacterDraft,
    DraftMotifResonanceAssociation,
    DraftTechnique,
)
from world.character_creation.services import ensure_draft_motif
from world.magic.factories import (
    EffectTypeFactory,
    FacetFactory,
    ResonanceModifierTypeFactory,
    TechniqueStyleFactory,
)


class MagicStageCompletionTest(TestCase):
    """Test magic stage completion logic for character creation."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()
        cls.resonance = ResonanceModifierTypeFactory()
        cls.facet = FacetFactory(name="TestFacet")

    def _create_complete_gift(self, draft):
        """Helper to create a draft gift with resonance and 1 technique."""
        gift = DraftGiftFactory(draft=draft)
        gift.resonances.add(self.resonance)
        DraftTechniqueFactory(
            gift=gift,
            style=self.style,
            effect_type=self.effect_type,
            name="Technique 0",
        )
        return gift

    def _create_complete_motif(self, draft):
        """Helper to create a draft motif with at least 1 resonance and 1 facet."""
        motif = DraftMotifFactory(draft=draft)
        motif_resonance = DraftMotifResonanceFactory(motif=motif, resonance=self.resonance)
        DraftMotifResonanceAssociation.objects.create(
            motif_resonance=motif_resonance, facet=self.facet
        )
        return motif

    def _create_complete_anima_ritual(self, draft):
        """Helper to create a complete draft anima ritual."""
        return DraftAnimaRitualFactory(draft=draft)

    def test_magic_incomplete_when_nothing_created(self):
        """Test magic is incomplete when player hasn't created any magic elements."""
        draft = CharacterDraftFactory(account=self.account)
        # No magic elements created - magic is required
        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_no_gift(self):
        """Test magic is incomplete when motif/ritual started but no gift."""
        draft = CharacterDraftFactory(account=self.account)
        # Create motif and anima ritual but no gift - started but incomplete
        self._create_complete_motif(draft)
        self._create_complete_anima_ritual(draft)

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_gift_no_resonance(self):
        """Test magic is incomplete when gift has no resonance."""
        draft = CharacterDraftFactory(account=self.account)
        # Create gift without resonances
        gift = DraftGiftFactory(draft=draft)
        DraftTechniqueFactory(
            gift=gift,
            style=self.style,
            effect_type=self.effect_type,
            name="Technique 0",
        )
        self._create_complete_motif(draft)
        self._create_complete_anima_ritual(draft)

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_no_techniques(self):
        """Test magic is incomplete when gift has no techniques."""
        draft = CharacterDraftFactory(account=self.account)
        # Create gift without techniques
        gift = DraftGiftFactory(draft=draft)
        gift.resonances.add(self.resonance)
        self._create_complete_motif(draft)
        self._create_complete_anima_ritual(draft)

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_technique_missing_name(self):
        """Test magic is incomplete when technique is missing name."""
        draft = CharacterDraftFactory(account=self.account)
        gift = DraftGiftFactory(draft=draft)
        gift.resonances.add(self.resonance)
        # Create 1 technique with empty name
        DraftTechniqueFactory(
            gift=gift,
            style=self.style,
            effect_type=self.effect_type,
            name="",
        )
        self._create_complete_motif(draft)
        self._create_complete_anima_ritual(draft)

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_no_motif(self):
        """Test magic is incomplete when motif does not exist."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        self._create_complete_anima_ritual(draft)
        # No motif created

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_motif_no_resonance(self):
        """Test magic is incomplete when motif has no resonances."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        # Create motif without resonances (and thus no facets)
        DraftMotifFactory(draft=draft)
        self._create_complete_anima_ritual(draft)

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_motif_no_facets(self):
        """Test magic is incomplete when motif has resonance but no facet assignments."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        # Create motif with resonance but NO facet
        motif = DraftMotifFactory(draft=draft)
        DraftMotifResonanceFactory(motif=motif, resonance=self.resonance)
        self._create_complete_anima_ritual(draft)

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_no_anima_ritual(self):
        """Test magic is incomplete when anima ritual does not exist."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        self._create_complete_motif(draft)
        # No anima ritual created

        self.assertFalse(draft._is_magic_complete())

    def test_magic_incomplete_anima_ritual_missing_description(self):
        """Test magic is incomplete when anima ritual has empty description."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        self._create_complete_motif(draft)
        DraftAnimaRitualFactory(draft=draft, description="")

        self.assertFalse(draft._is_magic_complete())

    def test_magic_complete(self):
        """Test magic is complete when all requirements are met."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        self._create_complete_motif(draft)
        self._create_complete_anima_ritual(draft)

        self.assertTrue(draft._is_magic_complete())

    def test_magic_complete_multiple_gifts(self):
        """Test magic is complete with multiple valid gifts."""
        draft = CharacterDraftFactory(account=self.account)
        # Create two complete gifts
        self._create_complete_gift(draft)
        self._create_complete_gift(draft)
        self._create_complete_motif(draft)
        self._create_complete_anima_ritual(draft)

        self.assertTrue(draft._is_magic_complete())

    def test_stage_completion_includes_magic(self):
        """Test that stage_completion includes magic stage."""
        draft = CharacterDraftFactory(account=self.account)
        self._create_complete_gift(draft)
        self._create_complete_motif(draft)
        self._create_complete_anima_ritual(draft)

        stage_completion = draft.get_stage_completion()
        self.assertIn(CharacterDraft.Stage.MAGIC, stage_completion)
        self.assertTrue(stage_completion[CharacterDraft.Stage.MAGIC])


class MaxTechniquesEnforcedTest(APITestCase):
    """Test that the max techniques limit (3) is enforced on creation."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()
        cls.resonance = ResonanceModifierTypeFactory()

    def setUp(self):
        self.draft = CharacterDraftFactory(account=self.user)
        self.gift = DraftGiftFactory(draft=self.draft)
        self.gift.resonances.add(self.resonance)
        # Create 3 techniques (the max)
        for i in range(3):
            DraftTechniqueFactory(
                gift=self.gift,
                style=self.style,
                effect_type=self.effect_type,
                name=f"Technique {i}",
            )

    def test_max_techniques_enforced(self):
        """POST to technique endpoint with 3 existing techniques returns 400."""
        self.client.force_authenticate(user=self.user)
        url = reverse("character_creation:draft-technique-list")
        data = {
            "gift": self.gift.id,
            "name": "Technique 4",
            "style": self.style.id,
            "effect_type": self.effect_type.id,
            "level": 1,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Should still have 3 techniques
        self.assertEqual(DraftTechnique.objects.filter(gift=self.gift).count(), 3)

    def test_can_create_up_to_max(self):
        """Ensure we can still create if under the limit."""
        # Delete one technique to be at 2
        DraftTechnique.objects.filter(gift=self.gift).first().delete()
        self.assertEqual(DraftTechnique.objects.filter(gift=self.gift).count(), 2)

        self.client.force_authenticate(user=self.user)
        url = reverse("character_creation:draft-technique-list")
        data = {
            "gift": self.gift.id,
            "name": "Replacement Technique",
            "style": self.style.id,
            "effect_type": self.effect_type.id,
            "level": 1,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DraftTechnique.objects.filter(gift=self.gift).count(), 3)


class EnsureMotifServiceTest(TestCase):
    """Test ensure_draft_motif service function."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.resonance1 = ResonanceModifierTypeFactory()
        cls.resonance2 = ResonanceModifierTypeFactory()

    def test_ensure_motif_creates_motif(self):
        """ensure_draft_motif creates a DraftMotif when none exists."""
        draft = CharacterDraftFactory(account=self.account)
        gift = DraftGiftFactory(draft=draft)
        gift.resonances.add(self.resonance1)

        motif = ensure_draft_motif(draft)
        self.assertIsNotNone(motif)
        self.assertEqual(motif.draft_id, draft.id)

    def test_ensure_motif_creates_resonances_from_gift(self):
        """ensure_draft_motif syncs resonances from the draft gift."""
        draft = CharacterDraftFactory(account=self.account)
        gift = DraftGiftFactory(draft=draft)
        gift.resonances.add(self.resonance1, self.resonance2)

        motif = ensure_draft_motif(draft)
        resonance_ids = set(motif.resonances.values_list("resonance_id", flat=True))
        self.assertIn(self.resonance1.id, resonance_ids)
        self.assertIn(self.resonance2.id, resonance_ids)

    def test_ensure_motif_idempotent(self):
        """Calling ensure_draft_motif twice doesn't duplicate records."""
        draft = CharacterDraftFactory(account=self.account)
        gift = DraftGiftFactory(draft=draft)
        gift.resonances.add(self.resonance1)

        motif1 = ensure_draft_motif(draft)
        motif2 = ensure_draft_motif(draft)
        self.assertEqual(motif1.id, motif2.id)
        self.assertEqual(motif2.resonances.count(), 1)

    def test_ensure_motif_removes_stale_gift_resonances(self):
        """Resonances removed from the gift are removed from the motif on re-sync."""
        draft = CharacterDraftFactory(account=self.account)
        gift = DraftGiftFactory(draft=draft)
        gift.resonances.add(self.resonance1, self.resonance2)

        motif = ensure_draft_motif(draft)
        self.assertEqual(motif.resonances.count(), 2)

        # Remove one resonance from the gift
        gift.resonances.remove(self.resonance2)
        motif = ensure_draft_motif(draft)
        resonance_ids = set(motif.resonances.values_list("resonance_id", flat=True))
        self.assertIn(self.resonance1.id, resonance_ids)
        self.assertNotIn(self.resonance2.id, resonance_ids)


class DraftFacetAssignmentViewSetTest(APITestCase):
    """Tests for DraftMotifResonanceAssociationViewSet (facet assignments)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.resonance = ResonanceModifierTypeFactory()
        cls.facet = FacetFactory(name="Spider")

    def setUp(self):
        self.draft = CharacterDraftFactory(account=self.user)
        self.motif = DraftMotifFactory(draft=self.draft)
        self.motif_resonance = DraftMotifResonanceFactory(
            motif=self.motif, resonance=self.resonance
        )

    def test_list_requires_auth(self):
        """Test that listing facet assignments requires authentication."""
        url = reverse("character_creation:draft-facet-assignment-list")
        response = self.client.get(url)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_list_authenticated(self):
        """Test listing facet assignments when authenticated."""
        self.client.force_authenticate(user=self.user)
        url = reverse("character_creation:draft-facet-assignment-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_facet_assignment(self):
        """Test creating a facet assignment."""
        self.client.force_authenticate(user=self.user)
        url = reverse("character_creation:draft-facet-assignment-list")
        data = {
            "motif_resonance": self.motif_resonance.id,
            "facet": self.facet.id,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DraftMotifResonanceAssociation.objects.count(), 1)

    def test_delete_facet_assignment(self):
        """Test deleting a facet assignment."""
        self.client.force_authenticate(user=self.user)
        assignment = DraftMotifResonanceAssociation.objects.create(
            motif_resonance=self.motif_resonance,
            facet=self.facet,
        )
        url = reverse("character_creation:draft-facet-assignment-detail", args=[assignment.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(DraftMotifResonanceAssociation.objects.count(), 0)

    def test_cannot_access_other_users_assignments(self):
        """Test that users cannot see other users' facet assignments."""
        other_user = AccountFactory()
        other_draft = CharacterDraftFactory(account=other_user)
        other_motif = DraftMotifFactory(draft=other_draft)
        other_resonance = DraftMotifResonanceFactory(motif=other_motif, resonance=self.resonance)
        other_assignment = DraftMotifResonanceAssociation.objects.create(
            motif_resonance=other_resonance,
            facet=self.facet,
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("character_creation:draft-facet-assignment-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should not include other user's assignment
        assignment_ids = [a["id"] for a in response.data]
        self.assertNotIn(other_assignment.id, assignment_ids)
