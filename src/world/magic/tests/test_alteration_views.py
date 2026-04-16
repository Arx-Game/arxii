"""Tests for alteration API endpoints."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import (
    MIN_ALTERATION_DESCRIPTION_LENGTH,
    AlterationTier,
    PendingAlterationStatus,
)
from world.magic.factories import (
    AffinityFactory,
    MagicalAlterationTemplateFactory,
    PendingAlterationFactory,
    ResonanceFactory,
)


class PendingAlterationViewSetTests(APITestCase):
    """Test the PendingAlteration API."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        cls.character = CharacterFactory()
        cls.character.db_account = cls.account
        cls.character.save()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(name="Shadow", affinity=cls.affinity)

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.account)

    def test_list_pending_alterations(self):
        """GET returns the character's open pending alterations."""
        PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        url = reverse("magic:pending-alteration-list")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_resolve_author_from_scratch(self):
        """POST resolve action creates template and applies condition."""
        pending = PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            tier=AlterationTier.MARKED,
        )
        url = reverse("magic:pending-alteration-resolve", args=[pending.pk])
        response = self.client.post(
            url,
            {
                "name": "Voice of Many",
                "player_description": "A" * MIN_ALTERATION_DESCRIPTION_LENGTH,
                "observer_description": "B" * MIN_ALTERATION_DESCRIPTION_LENGTH,
                "weakness_magnitude": 0,
                "resonance_bonus_magnitude": 1,
                "social_reactivity_magnitude": 1,
                "is_visible_at_rest": False,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        pending.refresh_from_db()
        assert pending.status == PendingAlterationStatus.RESOLVED

    def test_library_browse(self):
        """GET library action returns tier-matched library entries."""
        pending = PendingAlterationFactory(
            character=self.sheet,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            tier=AlterationTier.MARKED,
        )
        MagicalAlterationTemplateFactory(
            tier=AlterationTier.MARKED,
            is_library_entry=True,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
        )
        MagicalAlterationTemplateFactory(
            tier=AlterationTier.TOUCHED,  # wrong tier
            is_library_entry=True,
        )
        url = reverse("magic:pending-alteration-library", args=[pending.pk])
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1  # only tier-matched entry
