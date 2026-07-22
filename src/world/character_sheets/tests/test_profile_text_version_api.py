"""API tests for the profile-text-versions timeline endpoint (#2631)."""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.services import update_profile_text
from world.character_sheets.types import ProfileTextField
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class ProfileTextVersionEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = AccountFactory()
        roster_entry = RosterEntryFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=cls.account)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
        cls.sheet = roster_entry.character_sheet
        profile = cls.sheet.true_profile
        profile.background = "The CG original."
        profile.save(update_fields=["background"])
        update_profile_text(profile, ProfileTextField.BACKGROUND, "The rewrite.")
        cls.url = f"/api/character-sheets/{cls.sheet.pk}/profile-text-versions/"

    def setUp(self):
        self.client = APIClient()

    def test_owner_sees_timeline(self):
        self.client.force_authenticate(user=self.account)
        response = self.client.get(self.url)
        assert response.status_code == 200, response.content[:800]
        texts = [row["text"] for row in response.data]
        assert "The CG original." in texts
        assert "The rewrite." in texts

    def test_other_player_gets_empty_history(self):
        stranger = AccountFactory()
        self.client.force_authenticate(user=stranger)
        response = self.client.get(self.url)
        assert response.status_code == 200, response.content[:800]
        assert response.data == []

    def test_staff_sees_timeline(self):
        staff = AccountFactory()
        staff.is_staff = True
        staff.save()
        self.client.force_authenticate(user=staff)
        response = self.client.get(self.url)
        assert response.status_code == 200, response.content[:800]
        assert len(response.data) == 2

    def test_unauthenticated_rejected(self):
        response = self.client.get(self.url)
        assert response.status_code in (401, 403)
