"""Tests for the additive narrative play reader contracts."""

import base64
import json
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

    def test_context_includes_surrounding_cursors(self) -> None:
        """The +-25 pose window must be genuinely bounded, not just present.

        With only a handful of interactions, the whole set fits inside the
        +-25 window and `before`/`after` are always `None` regardless of
        whether the boundary math is right -- `assertIn` alone would pass
        for a broken view that hardcodes `{"before": None, "after": None}`
        (reviewer finding on 2028a0af7). Use enough rows that the target has
        genuine earlier AND later poses beyond the window, then decode each
        cursor the same way `_page()` does (base64 + json, see its own
        boundary-parsing code) and assert it names the EXACT boundary row's
        (timestamp, id) pair -- not merely a non-null string.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        interactions = [InteractionFactory(scene=scene) for _ in range(60)]
        target = interactions[30]

        response = self.client.get(
            "/api/play/context/",
            {"id": target.pk, "timestamp": target.timestamp.isoformat()},
        )
        data = response.json()
        self.assertIsNotNone(data["before"])
        self.assertIsNotNone(data["after"])

        def _decode(token: str) -> list:
            padded = token + "=" * (-len(token) % 4)
            return json.loads(base64.urlsafe_b64decode(padded).decode())

        # Window is rows[5:56] (start = max(0, 30-25) = 5, end = 30+26 = 56,
        # of 60 rows): `before` must decode to row 5's boundary, `after` to
        # row 55's. Fetch the served (DRF-rendered) timestamps from
        # `/api/play/poses/` rather than reformatting `.isoformat()` by hand,
        # since that rendering is exactly what `_cursor()` encodes.
        poses_by_id = {
            row["id"]: row["timestamp"]
            for row in self.client.get("/api/play/poses/").json()["results"]
        }
        expected_before_row = interactions[5]
        expected_after_row = interactions[55]
        self.assertEqual(
            _decode(data["before"]),
            [poses_by_id[expected_before_row.pk], expected_before_row.pk],
        )
        self.assertEqual(
            _decode(data["after"]),
            [poses_by_id[expected_after_row.pk], expected_after_row.pk],
        )


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

    def test_multi_pose_thread_cursor_matches_its_sort_key(self) -> None:
        """Regression test (task-4 re-review): the cursor-boundary key must be
        computed from the SAME field the view sorts and pages by.

        `PlayThreadsView` sorts groups by `firstVisible` (root creation time,
        per spec: "Roots are ordered by creation time, oldest to newest"). A
        genuine multi-pose `InteractionThread` can have a `latestVisible`
        (newest reply) far removed from its `firstVisible` (root) -- an old
        thread with a very recent reply. If `_row_key`'s fallback resolved to
        `latestVisible` instead of `firstVisible`, the cursor-boundary key for
        that thread would disagree with its actual sort position, and
        `_page()`'s linear `key > boundary` / `key >= boundary` search --
        which assumes `results` is monotonic in the SAME field it searches --
        would misplace the boundary, re-including rows a caller already saw.

        Layout (26 groups, page size 20): 6 single-pose "legacy" groups at
        minutes 01-06, then thread "A" whose root lands at minute 07 (so it
        sorts 7th) but whose reply lands 9 days later, then 19 more legacy
        groups at minutes 08-26. Requesting everything strictly `after`
        legacy pose 9 (minute 09, sort position 9th) must return legacy 10
        onward only -- never "A", legacy 8, or legacy 9 again, which is
        exactly what leaks back in if the cursor key uses the reply's
        timestamp instead of the root's.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)

        def _row(pose_id: int, timestamp: str, thread_id: str | None) -> dict:
            return {
                "id": pose_id,
                "timestamp": timestamp,
                "thread_id": thread_id,
                "content": f"pose {pose_id}",
                "mode": "pose",
                "place": None,
                "scene": None,
                "receiver_persona_ids": [],
                "persona": {"id": 1, "name": "Tester"},
            }

        rows = [_row(i, f"2026-01-01T00:{i:02d}:00Z", None) for i in range(1, 7)]
        rows.append(_row(1000, "2026-01-01T00:07:00Z", "A"))  # thread A's root
        rows.append(_row(2000, "2026-01-10T00:00:00Z", "A"))  # thread A's reply, 9 days later
        rows.extend(_row(i, f"2026-01-01T00:{i:02d}:00Z", None) for i in range(8, 27))

        # Build the "after" cursor for legacy pose 9 the same way `_cursor()` does,
        # without importing that private helper: base64(json([timestamp, id])).
        after_value = json.dumps(["2026-01-01T00:09:00Z", 9], separators=(",", ":"))
        after_token = base64.urlsafe_b64encode(after_value.encode()).decode().rstrip("=")

        with patch("world.scenes.play_views._rows", return_value=(rows, None)):
            response = self.client.get(f"/api/play/threads/?after={after_token}")

        self.assertEqual(response.status_code, 200)
        result_ids = [row["id"] for row in response.json()["results"]]
        # Thread "A" (root at minute 07) and legacy 8/9 all sort BEFORE the
        # minute-09 boundary and must never reappear once we've paged past it.
        self.assertNotIn("A", result_ids)
        self.assertNotIn("legacy:8", result_ids)
        self.assertNotIn("legacy:9", result_ids)
        self.assertEqual(result_ids[0], "legacy:10")


class PlaySearchMaskingTests(APITestCase):
    """Proves search matches rendered (comprehension-masked) text, never raw content."""

    def test_zero_fluency_viewer_gets_no_hit_on_garbled_term(self) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )
        from world.scenes.constants import InteractionMode
        from world.scenes.factories import SceneFactory
        from world.species.factories import LanguageFactory
        from world.traits.factories import CharacterTraitValueFactory
        from world.traits.models import Trait, TraitCategory, TraitType

        trait = Trait.objects.create(
            name="TestSearchKhatic", trait_type=TraitType.LANGUAGE, category=TraitCategory.GENERAL
        )
        language = LanguageFactory(name="TestSearchKhatic", trait=trait)
        scene = SceneFactory()

        writer_account = AccountFactory()
        writer_sheet = CharacterSheetFactory(character=CharacterFactory())
        RosterTenureFactory(
            player_data=PlayerDataFactory(account=writer_account),
            roster_entry=RosterEntryFactory(character_sheet=writer_sheet),
        )
        CharacterTraitValueFactory(character=writer_sheet, trait=trait, value=100)
        content = "the caravan leaves at dawn through the salt gate"
        interaction = InteractionFactory(
            persona=writer_sheet.primary_persona,
            scene=scene,
            mode=InteractionMode.SAY,
            language=language,
            content=content,
        )

        zero_account = AccountFactory()
        zero_sheet = CharacterSheetFactory(character=CharacterFactory())
        RosterTenureFactory(
            player_data=PlayerDataFactory(account=zero_account),
            roster_entry=RosterEntryFactory(character_sheet=zero_sheet),
        )
        # C1: the zero-fluency viewer needs a pose IN this scene to count as a
        # participant at all (test_language_interactions.py's own pattern) —
        # without one they always garble regardless of fluency, which still
        # proves the point but let's be precise and give them scene presence.
        InteractionFactory(
            persona=zero_sheet.primary_persona, scene=scene, mode=InteractionMode.POSE
        )

        self.client.force_authenticate(user=zero_account)
        # This task (Task 5) requires every search request to carry a bound;
        # bound by this scene's conversation, which does not narrow the
        # candidate set below the writer's interaction (it stays IN scope) —
        # so the masking proof below is unaffected by the bound requirement.
        response = self.client.get(f"/api/play/search/?q=caravan&conversation=scene:{scene.pk}")
        self.assertEqual(response.status_code, 200)
        hit_ids = {r["pose"]["id"] for r in response.json()["results"]}
        self.assertNotIn(str(interaction.pk), hit_ids)

        # Sanity: the SAME query against the raw DB column would have matched —
        # proves this is a real masking test, not a query the raw column
        # wouldn't have hit anyway.
        self.assertIn("caravan", content)

    def test_search_requires_a_bound(self) -> None:
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        response = self.client.get("/api/play/search/?q=pose")
        self.assertEqual(response.status_code, 400)
        self.assertIn("bound", response.json()["detail"])

    def test_search_with_a_date_bound_succeeds(self) -> None:
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        response = self.client.get("/api/play/search/?q=pose&from=2020-01-01")
        self.assertEqual(response.status_code, 200)

    def test_search_with_only_an_until_bound_succeeds(self) -> None:
        """`_queryset()` accepts `until` as an alias for `to` (play_views.py:99);
        the bound gate must recognize it too, or a caller bounding solely by
        `until` gets spuriously 400'd even though `_queryset()` would have
        honored it as a real bound (reviewer finding on b159b889b)."""
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        response = self.client.get("/api/play/search/?q=pose&until=2030-01-01")
        self.assertEqual(response.status_code, 200)
