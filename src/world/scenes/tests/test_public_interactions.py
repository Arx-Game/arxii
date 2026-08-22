"""Anonymous public-scene interaction reads for the landing-page excerpt (#3305)."""

from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    InteractionReceiverFactory,
    PlaceFactory,
    SceneFactory,
)


class PublicInteractionListTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        def build_account():
            account = AccountFactory()
            character = CharacterFactory()
            roster_entry = RosterEntryFactory(character_sheet__character=character)
            player_data = PlayerDataFactory(account=account)
            RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
            return account, roster_entry.character_sheet.primary_persona

        cls.writer_account, cls.writer_persona = build_account()
        cls.receiver_account, cls.receiver_persona = build_account()

        cls.scene_public = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        # Normal room-heard pose (DEFAULT visibility, no place, no receivers).
        cls.public_pose = InteractionFactory(
            persona=cls.writer_persona,
            mode=InteractionMode.POSE,
            scene=cls.scene_public,
        )
        # Whisper -- directed, never room-heard.
        cls.whisper = InteractionFactory(
            persona=cls.writer_persona,
            mode=InteractionMode.WHISPER,
            scene=cls.scene_public,
        )
        InteractionReceiverFactory(interaction=cls.whisper, persona=cls.receiver_persona)
        # Directed (place-scoped table talk) -- has a receiver, never room-heard.
        cls.place = PlaceFactory()
        cls.directed = InteractionFactory(
            persona=cls.writer_persona,
            mode=InteractionMode.SAY,
            scene=cls.scene_public,
            place=cls.place,
        )
        InteractionReceiverFactory(interaction=cls.directed, persona=cls.receiver_persona)

        cls.scene_private = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)
        cls.private_pose = InteractionFactory(
            persona=cls.writer_persona,
            mode=InteractionMode.POSE,
            scene=cls.scene_private,
        )

    def test_anonymous_list_returns_only_public_room_heard(self) -> None:
        client = APIClient()
        url = reverse("interaction-list")
        resp = client.get(url, {"scene": self.scene_public.pk})
        self.assertEqual(resp.status_code, 200)
        ids = [row["id"] for row in resp.json()["results"]]
        self.assertIn(self.public_pose.pk, ids)
        self.assertNotIn(self.whisper.pk, ids)
        self.assertNotIn(self.directed.pk, ids)

    def test_anonymous_list_excludes_private_scene(self) -> None:
        client = APIClient()
        url = reverse("interaction-list")
        resp = client.get(url, {"scene": self.scene_private.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"], [])

    def test_anonymous_other_actions_rejected(self) -> None:
        client = APIClient()
        detail = reverse("interaction-detail", kwargs={"pk": self.public_pose.pk})
        self.assertIn(client.get(detail).status_code, (401, 403))
        self.assertIn(client.delete(detail).status_code, (401, 403))

    def test_anonymous_mark_private_rejected(self) -> None:
        client = APIClient()
        url = reverse("interaction-mark-private", kwargs={"pk": self.public_pose.pk})
        self.assertIn(client.post(url).status_code, (401, 403))

    def test_anonymous_submit_pose_rejected(self) -> None:
        client = APIClient()
        url = reverse("interaction-submit-pose")
        self.assertIn(
            client.post(url, {"persona_id": self.writer_persona.pk, "content": "hi"}).status_code,
            (401, 403),
        )

    def test_anonymous_page_size_capped(self) -> None:
        for _ in range(6):
            InteractionFactory(
                persona=self.writer_persona,
                mode=InteractionMode.POSE,
                scene=self.scene_public,
            )
        client = APIClient()
        url = reverse("interaction-list")
        resp = client.get(url, {"scene": self.scene_public.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertLessEqual(len(resp.json()["results"]), 5)
