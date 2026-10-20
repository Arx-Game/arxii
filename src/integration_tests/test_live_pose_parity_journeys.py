"""Journey for a live pose in an open scene (#4508): what arrives live is what the feed shows."""

from __future__ import annotations

from typing import Any
import uuid

from rest_framework import status

from integration_tests.harness import JourneyCase
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory

SUBMIT_POSE = "/api/interactions/submit-pose/"
ENDORSE = "/api/magic/pose-endorsements/"


class ALivePoseIsEndorsedInAnOpenScene(JourneyCase):
    """Ysmay poses in a scene Hobb is reading; Hobb endorses it."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.watch(self.ysmay, self.hobb)
        self.scene = SceneFactory(room=self.room, name="Supper at the Lantern")
        for player in (self.ysmay, self.hobb):
            SceneParticipationFactory(scene=self.scene, account=self.account_of(player))
        self.resonance = ResonanceFactory(name="Hearth-warm")
        CharacterResonanceFactory(character_sheet=self.ysmay.sheet_data, resonance=self.resonance)
        self.ysmay_web = self.api(self.account_of(self.ysmay))
        self.hobb_web = self.api(self.account_of(self.hobb))

    def _frames(self, character, name: str) -> list[dict[str, Any]]:
        """The payload of each ``name`` frame the game sent ``character``'s browser."""
        return [
            kwargs[name][1] for _args, kwargs in self.mailbox(character).calls if name in kwargs
        ]

    def _changed_ids(self, character) -> list[int]:
        return [frame["interaction_id"] for frame in self._frames(character, "interaction_changed")]

    def test_a_live_pose_can_be_endorsed_and_the_room_sees_it(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            posed = self.ysmay_web.post(
                SUBMIT_POSE,
                {
                    "persona_id": self.ysmay.sheet_data.primary_persona.pk,
                    "scene_id": self.scene.pk,
                    "content": "raises a cup to the room.",
                    "client_request_id": str(uuid.uuid4()),
                },
                format="json",
            )
        self.assertEqual(posed.status_code, status.HTTP_201_CREATED, posed.data)
        pose_id = posed.json()["id"]

        # The live frame Hobb got carries what his own feed read shows for that pose.
        live = self._frames(self.hobb, "interaction")
        self.assertEqual(len(live), 1, live)
        feed = self.hobb_web.get(f"/api/interactions/?scene={self.scene.pk}")
        self.assertEqual(feed.status_code, status.HTTP_200_OK, feed.content)
        data = feed.json()
        row = next(
            r for r in (data["results"] if isinstance(data, dict) else data) if r["id"] == pose_id
        )
        self.assertEqual([r["id"] for r in live[0]["endorsable_resonances"]], [self.resonance.pk])
        self.assertEqual(live[0]["endorsable_resonances"], row["endorsable_resonances"])
        self.assertEqual(self._changed_ids(self.ysmay), [])

        # Hobb endorses it; both browsers are told the pose changed.
        with self.captureOnCommitCallbacks(execute=True):
            endorsed = self.hobb_web.post(
                ENDORSE, {"interaction": pose_id, "resonance": self.resonance.pk}, format="json"
            )
        self.assertEqual(endorsed.status_code, status.HTTP_201_CREATED, endorsed.content)
        for character in (self.ysmay, self.hobb):
            self.assertEqual(self._changed_ids(character), [pose_id], character.key)
            self.assertEqual(
                self._frames(character, "interaction_changed")[0]["scene_id"], self.scene.pk
            )

        # Hobb's refetch of the pose shows his own endorsement.
        refetched = self.hobb_web.get(f"/api/interactions/{pose_id}/")
        self.assertEqual(refetched.status_code, status.HTTP_200_OK, refetched.content)
        mine = refetched.json()["my_pose_endorsement"]
        self.assertEqual(mine["id"], endorsed.json()["id"])
        self.assertEqual(mine["resonance_id"], self.resonance.pk)

        # He takes it back; both browsers are told again.
        with self.captureOnCommitCallbacks(execute=True):
            retracted = self.hobb_web.delete(f"{ENDORSE}{endorsed.json()['id']}/")
        self.assertEqual(retracted.status_code, status.HTTP_204_NO_CONTENT)
        for character in (self.ysmay, self.hobb):
            self.assertEqual(self._changed_ids(character), [pose_id, pose_id], character.key)
        again = self.hobb_web.get(f"/api/interactions/{pose_id}/")
        self.assertIsNone(again.json()["my_pose_endorsement"])

    def _ysmay_poses(self) -> int:
        """Ysmay poses in the scene; the id of her pose."""
        with self.captureOnCommitCallbacks(execute=True):
            posed = self.ysmay_web.post(
                SUBMIT_POSE,
                {
                    "persona_id": self.ysmay.sheet_data.primary_persona.pk,
                    "scene_id": self.scene.pk,
                    "content": "raises a cup to the room.",
                    "client_request_id": str(uuid.uuid4()),
                },
                format="json",
            )
        self.assertEqual(posed.status_code, status.HTTP_201_CREATED, posed.data)
        return posed.json()["id"]

    def test_ysmay_cannot_endorse_her_own_pose(self) -> None:
        pose_id = self._ysmay_poses()

        with self.captureOnCommitCallbacks(execute=True):
            refused = self.ysmay_web.post(
                ENDORSE, {"interaction": pose_id, "resonance": self.resonance.pk}, format="json"
            )

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertIn("own pose", str(refused.json()))
        for character in (self.ysmay, self.hobb):
            self.assertEqual(self._changed_ids(character), [], character.key)
        refetched = self.hobb_web.get(f"/api/interactions/{pose_id}/")
        self.assertEqual(refetched.json()["pose_endorsers"], [])

    def test_the_first_kudos_on_a_pose_tells_both_players_once(self) -> None:
        pose_id = self._ysmay_poses()
        self.assertEqual(self._changed_ids(self.hobb), [])

        with self.captureOnCommitCallbacks(execute=True):
            kudos = self.hobb_web.post(
                "/api/reaction-windows/react-to-interaction/",
                {
                    "persona_id": self.hobb.sheet_data.primary_persona.pk,
                    "interaction_id": pose_id,
                    "kind": "kudos",
                    "choice": "kudos",
                },
                format="json",
            )

        self.assertEqual(kudos.status_code, status.HTTP_201_CREATED, kudos.content)
        for character in (self.ysmay, self.hobb):
            self.assertEqual(self._changed_ids(character), [pose_id], character.key)
        refetched = self.hobb_web.get(f"/api/interactions/{pose_id}/")
        self.assertEqual(refetched.status_code, status.HTTP_200_OK, refetched.content)
        # Ysmay's first pose is her entrance, so its entrance window is there too.
        windows = {w["kind"]: w for w in refetched.json()["reaction_windows"]}
        self.assertEqual(sorted(windows), ["entrance", "kudos"])
        self.assertEqual(windows["kudos"]["my_reaction"], "kudos")
        self.assertEqual(windows["kudos"]["counts"], {"kudos": 1})
