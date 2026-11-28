"""Journey for a masked endorser's badge (#5290, the #4889 rule that no payload links a mask
to the real character).

Ysmay wears her Owl Mask and endorses Hobb's entrance pose, both as a pose endorsement and as
a scene-entry endorsement, through the web client's routes. Hobb reads his scene feed:

- the endorser badge on each endorsement shows the Owl Mask, never "Ysmay" or her real portrait;
- once Ysmay takes the mask off, the badges Hobb already received keep showing the mask,
  because the badge shows the face she wore when she endorsed.

The pose endorsement names no resonance of its own, so it waits for Hobb to accept it (#5327):
the waiting pick names the mask too, and the badge is listed once he accepts.

Expected values come from the issue: the badge is the face worn at the moment of endorsing.
"""

from __future__ import annotations

import json
from typing import Any
import uuid

from django.test import tag
from rest_framework import status

from integration_tests.harness import JourneyCase
from world.character_sheets.group_writer import SheetWriteError, remove_persona
from world.conditions.thumbnail_services import BUILTIN_FACE_PLACEHOLDER_URL
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.roster.factories import MediaFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Persona

SUBMIT_POSE = "/api/interactions/submit-pose/"
POSE_ENDORSEMENTS = "/api/magic/pose-endorsements/"
ENTRY_ENDORSEMENTS = "/api/magic/scene-entry-endorsements/"


class AMaskedEndorsersBadge(JourneyCase):
    """Ysmay endorses Hobb's entrance pose from behind an Owl Mask."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.scene = SceneFactory(room=self.room, name="Supper at the Lantern")
        for player in (self.ysmay, self.hobb):
            SceneParticipationFactory(scene=self.scene, account=self.account_of(player))
        self.resonance = ResonanceFactory(name="Hearth-warm")
        CharacterResonanceFactory(character_sheet=self.hobb.sheet_data, resonance=self.resonance)
        self.face = MediaFactory()
        real = self.ysmay.sheet_data.primary_persona
        real.thumbnail = self.face
        real.save(update_fields=["thumbnail"])
        self.ysmay_web = self.api(self.account_of(self.ysmay))
        self.hobb_web = self.api(self.account_of(self.hobb))

        posed = self.hobb_web.post(
            SUBMIT_POSE,
            {
                "persona_id": self.hobb.sheet_data.primary_persona.pk,
                "scene_id": self.scene.pk,
                "content": "walks in and shakes the rain from his coat.",
                "client_request_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(posed.status_code, status.HTTP_201_CREATED, posed.data)
        self.pose_id = posed.json()["id"]

        told = self.telnet(self.ysmay, "persona mask Owl Mask")
        self.assertIn("You don a mask: 'Owl Mask'", told)
        endorsed = self.ysmay_web.post(
            POSE_ENDORSEMENTS,
            {"interaction": self.pose_id, "resonance": self.resonance.pk},
            format="json",
        )
        self.assertEqual(endorsed.status_code, status.HTTP_201_CREATED, endorsed.content)
        self.pick_id = endorsed.json()["id"]
        entry = self.ysmay_web.post(
            ENTRY_ENDORSEMENTS,
            {
                "endorsee_sheet": self.hobb.sheet_data.pk,
                "scene": self.scene.pk,
                "resonance": self.resonance.pk,
            },
            format="json",
        )
        self.assertEqual(entry.status_code, status.HTTP_201_CREATED, entry.content)

    def hobbs_pose(self) -> dict[str, Any]:
        """Hobb's entrance pose as his own scene feed shows it."""
        feed = self.hobb_web.get(f"/api/interactions/?scene={self.scene.pk}")
        self.assertEqual(feed.status_code, status.HTTP_200_OK, feed.content)
        data = feed.json()
        rows = data["results"] if isinstance(data, dict) else data
        return next(row for row in rows if row["id"] == self.pose_id)

    def hobb_accepts(self) -> None:
        """Hobb accepts the resonance the masked witness proposed, so it counts."""
        accepted = self.hobb_web.post(f"{POSE_ENDORSEMENTS}{self.pick_id}/accept/")
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.content)

    def assert_badges_show_the_mask(self, row: dict[str, Any]) -> None:
        for kind in ("pose_endorsers", "entry_endorsers"):
            (badge,) = row[kind]
            self.assertEqual(badge["persona_name"], "Owl Mask", (kind, badge))
            # A bare mask shows the placeholder portrait, never the real face.
            self.assertEqual(badge["thumbnail_url"], BUILTIN_FACE_PLACEHOLDER_URL, (kind, badge))
        self.assertNotIn("Ysmay", json.dumps(row, default=str))
        self.assertNotIn(self.face.cloudinary_url, json.dumps(row, default=str))

    def test_the_waiting_pick_names_the_mask_and_the_badge_waits_for_the_accept(self) -> None:
        row = self.hobbs_pose()

        self.assertEqual(row["pose_endorsers"], [])
        (pick,) = row["pending_picks"]
        self.assertEqual((pick["endorser_name"], pick["can_answer"]), ("Owl Mask", True))
        self.assertNotIn("Ysmay", json.dumps(row["pending_picks"], default=str))

    @tag("regression")
    def test_regression_the_badge_shows_the_mask_not_the_real_self(self) -> None:
        """Regression for #5290. Hobb's badges name the Owl Mask, not Ysmay's real face."""
        self.hobb_accepts()
        self.assert_badges_show_the_mask(self.hobbs_pose())

    @tag("regression")
    def test_regression_the_badge_keeps_the_mask_after_she_unmasks(self) -> None:
        """Regression for #5290. Taking the mask off does not rewrite the badges she gave."""
        self.hobb_accepts()
        told = self.telnet(self.ysmay, "persona Ysmay")
        self.assertEqual(
            self.ysmay.sheet_data.active_persona_id, self.ysmay.sheet_data.primary_persona.pk, told
        )

        self.assert_badges_show_the_mask(self.hobbs_pose())

    @tag("regression")
    def test_regression_a_mask_with_endorsements_cannot_be_deleted(self) -> None:
        """Regression for #5290. Deleting the mask would turn its badges back into her real face."""
        mask = Persona.objects.get(character_sheet=self.ysmay.sheet_data, name="Owl Mask")
        self.hobb_accepts()

        with self.assertRaises(SheetWriteError):
            remove_persona(mask)

        self.assert_badges_show_the_mask(self.hobbs_pose())
