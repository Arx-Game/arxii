"""Journey for a live pose in an open scene (#4508, #5327): what arrives live is what the feed
shows, including the marks a pose carries and the picks waiting for its poser."""

from __future__ import annotations

from typing import Any
import uuid

from rest_framework import status

from integration_tests.harness import JourneyCase
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.narrative.models import NarrativeMessageDelivery
from world.scenes.factories import SceneFactory, SceneParticipationFactory

SUBMIT_POSE = "/api/interactions/submit-pose/"
ENDORSE = "/api/magic/pose-endorsements/"
PROPOSED = (
    "Hobb proposed Hearth-warm on your pose #1. "
    "Use endorse accept Hobb #1 or endorse decline Hobb #1."
)


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

    def notices(self, character) -> str:
        """Every private line the game sent ``character``'s player, from the delivery rows."""
        return "\n".join(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=character.sheet_data
            ).values_list("message__body", flat=True)
        )

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
        # A new pose carries no mark and no waiting pick, on the frame and on the feed alike.
        for field in ("act_marks", "pending_picks"):
            self.assertEqual((live[0][field], row[field]), ([], []), field)
        self.assertEqual(self._changed_ids(self.ysmay), [])

        # Hobb endorses it. The pose named no resonance, so his pick waits for Ysmay to accept
        # it; both browsers are told the pose changed, and Ysmay is told what was proposed.
        with self.captureOnCommitCallbacks(execute=True):
            endorsed = self.hobb_web.post(
                ENDORSE, {"interaction": pose_id, "resonance": self.resonance.pk}, format="json"
            )
        self.assertEqual(endorsed.status_code, status.HTTP_201_CREATED, endorsed.content)
        self.assertTrue(endorsed.json()["awaiting_acceptance"])
        for character in (self.ysmay, self.hobb):
            self.assertEqual(self._changed_ids(character), [pose_id], character.key)
            self.assertEqual(
                self._frames(character, "interaction_changed")[0]["scene_id"], self.scene.pk
            )
        self.assertIn(PROPOSED, self.notices(self.ysmay))

        # Hobb's refetch of the pose shows his own pick, waiting; the room does not count it.
        refetched = self.hobb_web.get(f"/api/interactions/{pose_id}/")
        self.assertEqual(refetched.status_code, status.HTTP_200_OK, refetched.content)
        mine = refetched.json()["my_pose_endorsement"]
        self.assertEqual(mine["id"], endorsed.json()["id"])
        self.assertEqual(mine["resonance_id"], self.resonance.pk)
        self.assertTrue(mine["awaiting_acceptance"])
        self.assertEqual(refetched.json()["pose_endorsers"], [])
        self.assertEqual(
            refetched.json()["pending_picks"],
            [
                {
                    "endorsement_id": endorsed.json()["id"],
                    "resonance_id": self.resonance.pk,
                    "resonance_name": "Hearth-warm",
                    "endorser_name": "Hobb",
                    "mine": True,
                    "can_answer": False,
                }
            ],
        )
        # Ysmay, whose pose it is, reads the same pick as hers to answer.
        hers = self.ysmay_web.get(f"/api/interactions/{pose_id}/").json()
        (pick,) = hers["pending_picks"]
        self.assertEqual((pick["mine"], pick["can_answer"]), (False, True))
        self.assertEqual(hers["pose_endorsers"], [])

        # She accepts it; both browsers are told again, and now the pick counts.
        with self.captureOnCommitCallbacks(execute=True):
            accepted = self.ysmay_web.post(f"{ENDORSE}{endorsed.json()['id']}/accept/")
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.content)
        for character in (self.ysmay, self.hobb):
            self.assertEqual(self._changed_ids(character), [pose_id, pose_id], character.key)
        after = self.hobb_web.get(f"/api/interactions/{pose_id}/").json()
        self.assertEqual(after["pending_picks"], [])
        self.assertEqual([e["resonance_id"] for e in after["pose_endorsers"]], [self.resonance.pk])
        self.assertFalse(after["my_pose_endorsement"]["awaiting_acceptance"])

        # He takes it back; both browsers are told again.
        with self.captureOnCommitCallbacks(execute=True):
            retracted = self.hobb_web.delete(f"{ENDORSE}{endorsed.json()['id']}/")
        self.assertEqual(retracted.status_code, status.HTTP_204_NO_CONTENT)
        for character in (self.ysmay, self.hobb):
            self.assertEqual(self._changed_ids(character), [pose_id] * 3, character.key)
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
