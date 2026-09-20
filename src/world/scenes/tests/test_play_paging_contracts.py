"""Focused regression coverage for bounded narrative-play cursors."""

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.models import Interaction


class PlayKeysetPagingContractTests(APITestCase):
    def test_cursor_page_is_bounded_and_filter_bound(self):
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        [InteractionFactory(scene=scene) for _ in range(101)]

        first = self.client.get("/api/play/poses/?from=2000-01-01")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.json()["results"]), 100)
        self.assertTrue(first.json()["after"])

        second = self.client.get(
            "/api/play/poses/",
            {"from": "2000-01-01", "after": first.json()["after"]},
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(second.json()["results"]), 1)
        self.assertNotEqual(first.json()["results"][-1]["id"], second.json()["results"][0]["id"])

        changed_filter = self.client.get(
            "/api/play/poses/",
            {"from": "2000-01-01", "kind": "room", "after": first.json()["after"]},
        )
        self.assertEqual(changed_filter.status_code, 400)
        self.assertEqual(changed_filter.json()["code"], "invalid_cursor")
        self.assertIn("reload", changed_filter.json()["detail"].lower())

    def test_bad_dates_are_typed_client_errors(self):
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        response = self.client.get("/api/play/poses/?from=not-a-date")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_date")
        self.assertEqual(response.json()["field"], "from")


class PlayContextCursorContractTests(APITestCase):
    def test_context_cursor_rejects_tamper_and_filter_mismatch(self):
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        rows = [InteractionFactory(scene=scene) for _ in range(60)]
        params = {
            "id": rows[30].pk,
            "timestamp": rows[30].timestamp.isoformat(),
            "from": "2000-01-01",
        }
        response = self.client.get("/api/play/context/", params)
        self.assertEqual(response.status_code, 200)
        cursor = response.json()["before"]
        self.assertTrue(cursor)

        tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
        invalid = self.client.get("/api/play/context/", {**params, "before": tampered})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["code"], "invalid_cursor")

        mismatched = self.client.get(
            "/api/play/context/", {**params, "from": "2020-01-01", "before": cursor}
        )
        self.assertEqual(mismatched.status_code, 400)
        self.assertEqual(mismatched.json()["code"], "invalid_cursor")

    def test_context_cursor_rejects_deleted_boundary_as_stale(self):
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        rows = [InteractionFactory(scene=scene) for _ in range(60)]
        params = {
            "id": rows[30].pk,
            "timestamp": rows[30].timestamp.isoformat(),
            "from": "2000-01-01",
        }
        response = self.client.get("/api/play/context/", params)
        cursor = response.json()["before"]
        from django.core import signing

        boundary_id = signing.loads(cursor, salt="narrative-play-cursor-v2")["key"][1]
        Interaction.objects.filter(pk=boundary_id).delete()
        stale = self.client.get("/api/play/context/", {**params, "before": cursor})
        self.assertEqual(stale.status_code, 400)
        self.assertEqual(stale.json()["code"], "invalid_cursor")
