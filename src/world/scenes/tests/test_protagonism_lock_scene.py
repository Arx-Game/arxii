"""Gate 10.5 — protagonism-locked accounts cannot initiate scenes."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from world.magic.factories import ResonanceFactory, with_corruption_at_stage
from world.roster.factories import RosterTenureFactory


class ProtagonismLockSceneInitiationTests(APITestCase):
    """Subsumed accounts cannot create scenes (gate 10.5)."""

    def _make_subsumed_account(self):
        """Return an AccountDB linked to a character at corruption stage 5."""
        tenure = RosterTenureFactory()
        sheet = tenure.roster_entry.character_sheet
        resonance = ResonanceFactory()
        with_corruption_at_stage(sheet, resonance, stage=5)
        sheet.__dict__.pop("is_protagonism_locked", None)
        return tenure.player_data.account

    def test_subsumed_account_gets_403_on_scene_create(self) -> None:
        account = self._make_subsumed_account()
        self.client.force_authenticate(user=account)

        url = reverse("scene-list")
        response = self.client.post(url, {"name": "Locked scene"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("locked", response.data.get("detail", "").lower())

    def test_normal_account_can_create_scene(self) -> None:
        """Sanity check: non-locked accounts can create scenes normally."""
        tenure = RosterTenureFactory()
        account = tenure.player_data.account
        self.client.force_authenticate(user=account)

        url = reverse("scene-list")
        response = self.client.post(url, {"name": "Normal scene"}, format="json")

        # 201 Created is the success path
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
