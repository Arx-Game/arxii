"""Tests for the additive narrative play reader contracts."""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.models import InteractionReadReceipt


class PlayReaderContractTests(APITestCase):
    def test_reader_endpoints_require_authentication(self):
        for path in (
            "/api/play/conversations/",
            "/api/play/poses/",
            "/api/play/context/?id=1",
            "/api/play/search/?q=pose",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, path)

    def test_search_rejects_short_queries_before_database_access(self):
        self.client.force_authenticate(user=AccountFactory())
        response = self.client.get("/api/play/search/?q=x")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("between 2 and 200", response.json()["detail"])

    def test_context_missing_reference_has_non_leaking_response(self):
        self.client.force_authenticate(user=AccountFactory())
        response = self.client.get("/api/play/context/?id=999999")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.json()["detail"], "This pose is no longer available.")


class PlayReadViewTests(APITestCase):
    def test_marks_poses_read(self) -> None:
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        interaction = InteractionFactory()
        response = self.client.post(
            "/api/play/read/",
            {"poses": [{"id": interaction.pk, "timestamp": interaction.timestamp.isoformat()}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["marked"], 1)
        self.assertTrue(
            InteractionReadReceipt.objects.filter(account=account, interaction=interaction).exists()
        )

    def test_rejects_more_than_100_poses(self) -> None:
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        poses = [{"id": i, "timestamp": "2026-01-01T00:00:00Z"} for i in range(101)]
        response = self.client.post("/api/play/read/", {"poses": poses}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_requires_authentication(self) -> None:
        response = self.client.post("/api/play/read/", {"poses": []}, format="json")
        self.assertEqual(response.status_code, 403)


class PlayThreadsViewTests(APITestCase):
    def test_groups_by_thread_and_paginates(self) -> None:
        from world.scenes.models import InteractionThread

        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        thread = InteractionThread.objects.create(
            holder_kind="scene", holder_id=scene.pk, scene_id=scene.pk
        )
        InteractionFactory(scene=scene, thread=thread, content="root pose")
        InteractionFactory(scene=scene, thread=thread, content="a reply")
        InteractionFactory(scene=scene, content="unthreaded standalone")

        response = self.client.get(f"/api/play/threads/?conversation=scene:{scene.pk}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        thread_ids = {row["id"] for row in data["results"]}
        self.assertIn(str(thread.pk), thread_ids)
        threaded_row = next(r for r in data["results"] if r["id"] == str(thread.pk))
        self.assertEqual(threaded_row["visiblePoseCount"], 2)

    def test_threads_respect_visibility(self) -> None:
        from world.scenes.constants import InteractionVisibility

        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        InteractionFactory(scene=scene, visibility=InteractionVisibility.VERY_PRIVATE)
        response = self.client.get(f"/api/play/threads/?conversation=scene:{scene.pk}")
        self.assertEqual(response.json()["results"], [])
