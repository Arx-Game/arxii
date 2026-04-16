"""Tests for alteration API endpoints."""

from django.urls import reverse
from evennia.utils.test_resources import BaseEvenniaTest
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
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


class PendingAlterationViewSetTests(BaseEvenniaTest):
    """Test the PendingAlteration API."""

    @classmethod
    def setUpTestData(cls):
        cls.affinity = AffinityFactory(name="Abyssal")
        cls.resonance = ResonanceFactory(name="Shadow", affinity=cls.affinity)

    def setUp(self):
        super().setUp()
        # Create account and sheet per-test so the db_account save is visible
        # within the test's transaction, avoiding SharedMemoryModel stale-cache issues.
        self.account = AccountFactory()
        self.sheet = CharacterSheetFactory()
        character = self.sheet.character
        character.db_account = self.account
        character.save()
        # Refresh to clear identity-map cache so the ORM filter sees db_account.
        character.refresh_from_db()
        self.client = APIClient()
        self.client.force_login(self.account)

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
