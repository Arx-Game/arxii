"""Journeys for GM-made NPCs (#4418): the GM owns what they mint and gives it a face."""

from __future__ import annotations

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile

from evennia_extensions.factories import MediaFactory
from integration_tests.harness import JourneyCase
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.roster.models import RosterEntry

GALLERY = "/api/roster/tenure-media/"
UPLOAD = "world.roster.services.gallery.CloudinaryGalleryService.upload_image"


def _fake_upload(player_data, **_kwargs):
    return MediaFactory(player_data=player_data, width=1000, height=1500, file_size_bytes=100)


class AGmMakesAnNpc(JourneyCase):
    """Ravenna is a JUNIOR GM; Sergeant Rook is the NPC she stands up."""

    def setUp(self) -> None:
        super().setUp()
        seed_default_gm_level_caps()
        self.room = self.make_room("The Barracks")
        self.ravenna = self.make_player("Ravenna", room=self.room)
        GMProfileFactory(account=self.account_of(self.ravenna), level=GMLevel.JUNIOR)

    @patch(UPLOAD, new=_fake_upload)
    def test_owner_and_portrait(self) -> None:
        result = self.web(
            self.ravenna, "mint_story_npc", name="Sergeant Rook", description="Heavyset..."
        )
        self.assertTrue(result.detail.success, result.detail.message)
        entry = RosterEntry.objects.get(pk=result.detail.data["roster_entry_id"])
        self.assertEqual(entry.creation_provenance, "gm_table")
        self.assertEqual(entry.created_by_account, self.account_of(self.ravenna))
        self.assertEqual(entry.story_npc_settings.lend_policy, "not_lent")
        self.assertFalse(entry.story_npc_settings.is_template)

        client = self.api(self.account_of(self.ravenna))
        created = client.post(
            GALLERY,
            {"roster_entry": entry.pk, "images": [SimpleUploadedFile("rook.png", b"x")]},
            format="multipart",
        )
        self.assertEqual(created.status_code, 201, created.data)
        picture = created.data[0]["id"]
        worn = client.patch(
            f"{GALLERY}{picture}/",
            {"crop": {"x": 100, "y": 50, "width": 400}, "wear": True},
            format="json",
        )
        self.assertEqual(worn.status_code, 200, worn.data)

        persona = entry.character_sheet.primary_persona
        persona.refresh_from_db()
        self.assertIn("c_crop", persona.thumbnail_url)
        self.assertIsNotNone(persona.thumbnail)
