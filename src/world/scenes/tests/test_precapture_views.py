"""API tests for pre-scene capture web surfaces (#3069 sub-item 4).

Covers ``SceneViewSet.truncate_precapture`` (POST /api/scenes/{id}/truncate-precapture/)
and ``PrecaptureConsentRequestViewSet`` (list mine-pending + POST .../respond/).
"""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import InteractionFactory, SceneFactory, SceneOwnerParticipationFactory
from world.scenes.models import Interaction, PrecaptureConsentRequest
from world.scenes.precapture_services import capture_prescene_interactions


def _setup_owner_with_character(account, label="Room"):
    room = ObjectDBFactory(
        db_key=f"{label}_{account.username}",
        db_typeclass_path="typeclasses.rooms.Room",
    )
    char = CharacterFactory(location=room)
    sheet = CharacterSheetFactory(character=char)
    player_data, _ = PlayerDataFactory._meta.model.objects.get_or_create(account=account)
    roster_entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    return char, sheet, room


def _backdate(interaction: Interaction, when) -> None:
    Interaction.objects.filter(pk=interaction.pk).update(timestamp=when)


class TruncatePrecaptureViewTestCase(APITestCase):
    """POST /api/scenes/{id}/truncate-precapture/."""

    def setUp(self):
        self.account = AccountFactory()
        self.char, self.sheet, self.room = _setup_owner_with_character(self.account)
        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneOwnerParticipationFactory(scene=self.scene, account=self.account)

        self.interactions = []
        for i in range(2):
            ia = InteractionFactory(
                persona=self.sheet.primary_persona,
                writer_account=self.account,
                scene=self.scene,
            )
            _backdate(ia, self.scene.date_started - timedelta(minutes=20 - i * 10))
            self.interactions.append(ia)

    def test_owner_truncates_and_gets_scene_back(self):
        self.client.force_authenticate(user=self.account)
        url = reverse("scene-truncate-precapture", kwargs={"pk": self.scene.pk})

        response = self.client.post(url, {"interaction_id": self.interactions[1].pk}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == self.scene.pk
        self.interactions[0].refresh_from_db()
        self.interactions[1].refresh_from_db()
        assert self.interactions[0].scene_id is None
        assert self.interactions[1].scene_id == self.scene.pk

    def test_non_owner_non_staff_gets_403(self):
        other_account = AccountFactory()
        self.client.force_authenticate(user=other_account)
        url = reverse("scene-truncate-precapture", kwargs={"pk": self.scene.pk})

        response = self.client.post(url, {"interaction_id": self.interactions[1].pk}, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        self.interactions[0].refresh_from_db()
        assert self.interactions[0].scene_id == self.scene.pk  # untouched

    def test_missing_interaction_id_is_400(self):
        self.client.force_authenticate(user=self.account)
        url = reverse("scene-truncate-precapture", kwargs={"pk": self.scene.pk})

        response = self.client.post(url, {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class PrecaptureConsentRequestViewSetTestCase(APITestCase):
    """List mine-pending + respond."""

    def setUp(self):
        self.owner_account = AccountFactory()
        _owner_char, _owner_sheet, self.room = _setup_owner_with_character(
            self.owner_account, "Salon"
        )
        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneOwnerParticipationFactory(scene=self.scene, account=self.owner_account)

        self.absent_account = AccountFactory()
        elsewhere = ObjectDBFactory(db_key="Elsewhere", db_typeclass_path="typeclasses.rooms.Room")
        absent_char = CharacterFactory(location=elsewhere)
        absent_sheet = CharacterSheetFactory(character=absent_char)
        player_data, _ = PlayerDataFactory._meta.model.objects.get_or_create(
            account=self.absent_account
        )
        roster_entry = RosterEntryFactory(character_sheet=absent_sheet)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)

        self.pose = InteractionFactory(
            persona=absent_sheet.primary_persona,
            writer_account=self.absent_account,
            scene=None,
        )
        _backdate(self.pose, timezone.now() - timedelta(minutes=10))

        capture_prescene_interactions(self.scene, self.room)
        self.request_row = PrecaptureConsentRequest.objects.get(
            scene=self.scene, account=self.absent_account
        )

    def test_list_returns_only_the_authenticated_accounts_pending_requests(self):
        self.client.force_authenticate(user=self.absent_account)
        response = self.client.get("/api/precapture-consent-requests/")

        assert response.status_code == status.HTTP_200_OK
        ids = [row["id"] for row in response.data]
        assert ids == [self.request_row.pk]

    def test_list_never_leaks_another_accounts_pending_requests(self):
        self.client.force_authenticate(user=self.owner_account)
        response = self.client.get("/api/precapture-consent-requests/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_preview_shows_only_the_requesters_own_content(self):
        self.client.force_authenticate(user=self.absent_account)
        response = self.client.get("/api/precapture-consent-requests/")

        candidates = response.data[0]["candidates"]
        assert len(candidates) == 1
        assert candidates[0]["id"] == self.pose.pk
        assert candidates[0]["content"] == self.pose.content

    def test_accept_attaches_and_owner_can_see_it_in_the_scene(self):
        self.client.force_authenticate(user=self.absent_account)
        url = f"/api/precapture-consent-requests/{self.request_row.pk}/respond/"

        response = self.client.post(url, {"accept": True}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["attached_count"] == 1
        self.pose.refresh_from_db()
        assert self.pose.scene_id == self.scene.pk

    def test_decline_leaves_pose_unattached(self):
        self.client.force_authenticate(user=self.absent_account)
        url = f"/api/precapture-consent-requests/{self.request_row.pk}/respond/"

        response = self.client.post(url, {"accept": False}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["attached_count"] == 0
        self.pose.refresh_from_db()
        assert self.pose.scene_id is None

    def test_cannot_respond_to_someone_elses_request(self):
        self.client.force_authenticate(user=self.owner_account)
        url = f"/api/precapture-consent-requests/{self.request_row.pk}/respond/"

        response = self.client.post(url, {"accept": True}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
