"""The Gallery API (#4151), walked the way a player and their visitors use it."""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from evennia_extensions.factories import MediaFactory
from evennia_extensions.models import Media
from world.character_sheets.factories import MoodOptionFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterTenureFactory,
    TenureMediaFactory,
)
from world.roster.models import TenureMedia

URL = "/api/roster/tenure-media/"
UPLOAD = "world.roster.services.gallery.CloudinaryGalleryService.upload_image"
DELETE = "world.roster.services.gallery.CloudinaryGalleryService.delete_media"


def _fake_upload(player_data, **_kwargs) -> Media:
    return MediaFactory(player_data=player_data, width=1000, height=1500, file_size_bytes=100)


def _results(response) -> list[dict]:
    return response.data.get("results", response.data)


class GalleryJourneyTests(TestCase):
    """The owner builds a gallery; a stranger, a friend and nobody read it."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        self.entry = self.tenure.roster_entry
        self.owner = self.tenure.player_data.account
        self.mood = MoodOptionFactory(name="Furious")
        self.client = APIClient()

    def _as(self, account) -> APIClient:
        self.client.force_authenticate(user=account)
        return self.client

    def _list(self, account) -> list[dict]:
        response = self._as(account).get(URL, {"roster_entry": self.entry.pk})
        assert response.status_code == 200, response.data
        return _results(response)

    @patch(DELETE, side_effect=lambda media: media.delete())
    @patch(UPLOAD, side_effect=_fake_upload)
    def test_owner_builds_the_gallery(self, upload, delete_media) -> None:
        client = self._as(self.owner)
        files = [SimpleUploadedFile(f"{n}.png", b"x") for n in "abc"]
        created = client.post(
            URL, {"roster_entry": self.entry.pk, "images": files}, format="multipart"
        )
        assert created.status_code == 201, created.data
        assert upload.call_count == 3
        a, b, c = (row["id"] for row in created.data)

        cropped = client.patch(
            f"{URL}{a}/",
            {
                "title": "Cold, after",
                "caption": "The ledger, read aloud.",
                "mood": self.mood.pk,
                "crop": {"x": 100, "y": 50, "width": 400},
                "wear": True,
            },
            format="json",
        )
        assert cropped.status_code == 200, cropped.data
        assert cropped.data["is_look"]
        assert cropped.data["is_worn"]
        assert cropped.data["mood"] == "Furious"
        assert "c_crop,x_100,y_50,w_400,h_500" in cropped.data["look_url"]

        assert (
            client.post(
                f"{URL}reorder/", {"roster_entry": self.entry.pk, "ids": [c, a, b]}, format="json"
            ).status_code
            == 204
        )
        assert [row["id"] for row in self._list(self.owner)] == [c, a, b]

        deleted = client.delete(f"{URL}{b}/")
        assert deleted.data == {"outcome": "deleted"}
        delete_media.assert_called_once()
        assert [row["id"] for row in self._list(self.owner)] == [c, a]

        usage = client.get(f"{URL}usage/")
        assert usage.data == {
            "used_bytes": 200,
            "quota_bytes": self.tenure.player_data.media_quota_bytes,
        }

    def test_a_stranger_reads_but_cannot_change_it(self) -> None:
        link = TenureMediaFactory(tenure=self.tenure, media__is_nsfw=True)
        stranger = PlayerDataFactory().account
        rows = self._list(stranger)
        assert [row["id"] for row in rows] == [link.pk]
        # The veil is the client's: the flag travels, the picture is not withheld.
        assert rows[0]["is_nsfw"] is True
        assert rows[0]["can_delete"] is False
        assert (
            self._as(stranger).patch(f"{URL}{link.pk}/", {"title": "x"}, format="json").status_code
            == 403
        )
        assert self._as(stranger).delete(f"{URL}{link.pk}/").status_code == 403

    def test_nobody_without_an_account_sees_any_art(self) -> None:
        TenureMediaFactory(tenure=self.tenure)
        self.client.force_authenticate(user=None)
        assert self.client.get(URL, {"roster_entry": self.entry.pk}).status_code in (401, 403)

    def test_whose_gallery_must_be_named(self) -> None:
        assert self._as(self.owner).get(URL).status_code == 400

    def test_reorder_with_another_characters_picture_is_refused(self) -> None:
        own = TenureMediaFactory(tenure=self.tenure)
        foreign = TenureMediaFactory()
        response = self._as(self.owner).post(
            f"{URL}reorder/",
            {"roster_entry": self.entry.pk, "ids": [own.pk, foreign.pk]},
            format="json",
        )
        assert response.status_code == 400

    def test_an_nsfw_picture_cannot_be_cropped_into_a_look(self) -> None:
        link = TenureMediaFactory(tenure=self.tenure, media__is_nsfw=True)
        response = self._as(self.owner).patch(
            f"{URL}{link.pk}/", {"crop": {"x": 0, "y": 0, "width": 200}}, format="json"
        )
        assert response.status_code == 400
        assert response.data["detail"] == "An NSFW picture can't be a look."


class CharacterArtApiTests(TestCase):
    """Staff art on a roster character: the player hides it, never deletes it."""

    def setUp(self) -> None:
        self.tenure = RosterTenureFactory()
        self.entry = self.tenure.roster_entry
        self.player = self.tenure.player_data.account
        self.staff = PlayerDataFactory(account__is_staff=True).account
        self.client = APIClient()

    @patch(UPLOAD, side_effect=_fake_upload)
    def test_staff_add_art_that_outlives_the_player(self, upload) -> None:
        self.client.force_authenticate(user=self.staff)
        created = self.client.post(
            URL,
            {"roster_entry": self.entry.pk, "images": [SimpleUploadedFile("art.png", b"x")]},
            format="multipart",
        )
        assert created.status_code == 201, created.data
        upload.assert_called_once()
        art_id = created.data[0]["id"]
        assert created.data[0]["is_character_art"]

        self.client.force_authenticate(user=self.player)
        row = next(
            r
            for r in _results(self.client.get(URL, {"roster_entry": self.entry.pk}))
            if r["id"] == art_id
        )
        assert row["can_delete"] is False
        assert self.client.delete(f"{URL}{art_id}/").status_code == 403

        hidden = self.client.post(f"{URL}{art_id}/hide/")
        assert hidden.status_code == 200
        assert hidden.data["is_hidden"]

        stranger = PlayerDataFactory().account
        self.client.force_authenticate(user=stranger)
        assert _results(self.client.get(URL, {"roster_entry": self.entry.pk})) == []

        self.tenure.end_date = timezone.now()
        self.tenure.save()
        RosterTenureFactory(roster_entry=self.entry, player_number=2)
        self.entry.invalidate_tenure_cache()
        ids = [r["id"] for r in _results(self.client.get(URL, {"roster_entry": self.entry.pk}))]
        assert ids == [art_id]
        assert TenureMedia.objects.filter(pk=art_id).exists()

    def test_a_player_cannot_hide_their_own_upload(self) -> None:
        own = TenureMediaFactory(tenure=self.tenure)
        self.client.force_authenticate(user=self.player)
        assert self.client.post(f"{URL}{own.pk}/hide/").status_code == 400


class MoodOptionsApiTests(TestCase):
    """The mood picker reads the active moods."""

    def test_active_moods_are_listed(self) -> None:
        MoodOptionFactory(name="Amused")
        MoodOptionFactory(name="Retired", is_active=False)
        client = APIClient()
        client.force_authenticate(user=PlayerDataFactory().account)
        response = client.get("/api/character-sheets/mood-options/")
        names = [row["name"] for row in _results(response)]
        assert "Amused" in names
        assert "Retired" not in names


class RosterPortraitTests(TestCase):
    """The public roster shows a portrait only to an account (#3904 item 0)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenure = RosterTenureFactory()
        cls.entry = cls.tenure.roster_entry
        cls.entry.profile_picture = TenureMediaFactory(
            tenure=cls.tenure, crop_x=0, crop_y=0, crop_width=200
        )
        cls.entry.save()

    def test_signed_out_visitors_get_no_portrait(self) -> None:
        response = APIClient().get(f"/api/roster/entries/{self.entry.pk}/")
        assert response.status_code == 200
        assert response.data["profile_picture_url"] is None
        assert "media" not in response.data["tenures"][0]

    def test_an_account_gets_the_worn_looks_crop(self) -> None:
        client = APIClient()
        client.force_authenticate(user=PlayerDataFactory().account)
        response = client.get(f"/api/roster/entries/{self.entry.pk}/")
        assert "c_crop,x_0,y_0,w_200,h_250" in response.data["profile_picture_url"]
