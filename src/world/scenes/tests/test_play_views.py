"""Tests for the additive narrative play reader contracts."""

from unittest.mock import patch

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

    def test_paginates_beyond_one_page_with_stable_numeric_ordering(self) -> None:
        """Regression test (task-4 review): a conversation with more than 20
        distinct thread groups must not 500 (`_row_key`'s fallback needs a
        `latestVisiblePose` key, which `ThreadSummary` rows previously lacked),
        and equal-timestamp ties must order by `int(id)`, not `str(id)` (the
        pre-sort's tie-break previously compared the stringified id).

        Uses a mocked `_rows()` so the id values are exact and deterministic —
        real `Interaction` autoincrement ids depend on prior test execution
        order and cannot be relied on to straddle a digit-length boundary.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        shared_timestamp = "2026-01-01T00:00:00Z"
        # 90..112 straddles the 99 -> 100 digit-length boundary, where a STRING
        # sort ("100" < "99") disagrees with an INT sort.
        synthetic_ids = list(range(90, 113))
        rows = [
            {
                "id": pose_id,
                "timestamp": shared_timestamp,
                "thread_id": None,
                "content": f"pose {pose_id}",
                "mode": "pose",
                "place": None,
                "scene": None,
                "receiver_persona_ids": [],
                "persona": {"id": 1, "name": "Tester"},
            }
            for pose_id in synthetic_ids
        ]

        with patch("world.scenes.play_views._rows", return_value=(rows, None)):
            # The default (no-cursor) request is exactly the path that 500'd before
            # the fix: `start_index = len(results) - limit = 3 > 0`, so `_page()`
            # unconditionally calls `_cursor(page[0])`, which needs `_row_key`'s
            # fallback to resolve -- the missing `latestVisiblePose` key crashed here.
            latest_response = self.client.get("/api/play/threads/")
            self.assertEqual(latest_response.status_code, 200)
            latest_page = latest_response.json()
            self.assertIsNotNone(latest_page["before"])

            earlier_response = self.client.get(f"/api/play/threads/?before={latest_page['before']}")
            self.assertEqual(earlier_response.status_code, 200)
            earlier_page = earlier_response.json()

        latest_ids = [int(row["firstVisible"]["id"]) for row in latest_page["results"]]
        earlier_ids = [int(row["firstVisible"]["id"]) for row in earlier_page["results"]]

        # If the tie-break compared `str(id)` instead of `int(id)`, this sorted
        # order would instead be [100, 101, ..., 112, 90, 91, ..., 99] (lexical),
        # and the last-20 window would be a completely different, out-of-order set.
        self.assertEqual(latest_ids, list(range(93, 113)))
        self.assertEqual(earlier_ids, list(range(90, 110)))
