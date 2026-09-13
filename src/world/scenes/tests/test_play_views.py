"""Tests for the additive narrative play reader contracts."""

import base64
from datetime import timedelta
import json
from unittest.mock import patch

from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from evennia_extensions.factories import AccountFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import (
    InteractionFactory,
    PersonaFactory,
    PlaceFactory,
    SceneFactory,
)
from world.scenes.interaction_services import create_interaction
from world.scenes.models import Interaction, InteractionReadReceipt, InteractionThread
from world.scenes.play_views import _queryset
from world.scenes.thread_services import ReplyTarget


def _root_threads(count):
    """Mint *count* real root threads, returning their ids as strings.

    The mocked-``_rows`` pagination tests below need opaque, deterministic group
    keys. They used bare strings like ``"t1"``, but since #3787 the view resolves
    each thread to its exchange in the database (a row's thread is what it ANSWERS,
    so a nested reply has to collapse onto its root), and a made-up key is not a
    thread id. These are real rows, so the keys are real - while the POSE ids those
    tests actually assert on stay synthetic and exact, which is the whole reason
    they mock ``_rows`` in the first place.
    """
    scene = SceneFactory()
    ids = []
    for _ in range(count):
        thread = InteractionThread.objects.create(
            holder_kind=InteractionThread.HolderKind.SCENE,
            holder_id=scene.pk,
            scene_id=scene.pk,
        )
        ids.append(str(thread.pk))
    return ids


def _reply_to(scene, account, target, content):
    """Write a real reply to *target* through the production writer.

    Tests that build an exchange by hand-setting ``thread=`` model a state
    ``assign_interaction_thread`` cannot produce any more: since #3787 a thread
    holds the ANSWERS to a row and the answered row is its anchor, never a member.
    Going through ``create_interaction`` is what keeps these tests honest.

    ``PersonaFactory()`` has no roster tenure, so ``_get_account_for_persona``
    returns ``None`` and the reply is refused; patching it to a real account is the
    established pattern (see ``test_threading.py``).
    """
    with patch(
        "world.scenes.interaction_services._get_account_for_persona",
        return_value=account.pk,
    ):
        return create_interaction(
            persona=PersonaFactory(),
            content=content,
            mode=InteractionMode.POSE,
            scene=scene,
            reply_to=ReplyTarget(interaction_id=target.pk, timestamp=target.timestamp),
        )


def _reply_exchange(scene, account, target_content, reply_content):
    """An answered pose plus one real reply to it. Returns ``(target, reply)``."""
    target = InteractionFactory(scene=scene, content=target_content)
    return target, _reply_to(scene, account, target, reply_content)


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


class PlayPosesPaginationTests(APITestCase):
    def test_before_cursor_near_start_excludes_boundary_and_later_rows(self) -> None:
        """`_page()`'s ``before`` branch must stop at the boundary, not overshoot it.

        With 60 total rows and a `before` cursor targeting row index 5 (so only
        5 rows exist strictly before the boundary, far fewer than the view's
        page limit of 100), the old slice `results[start_index:start_index+limit]`
        computed `start_index = max(0, end_index-limit) = max(0, 5-100) = 0` and
        then sliced `[0:100]`, returning all 60 rows -- including the boundary
        row itself and everything after it, which a "before" request must never
        include. The fixed slice must return exactly rows 0-4.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        interactions = [InteractionFactory(scene=scene) for _ in range(60)]
        boundary = interactions[5]

        poses_by_id = {
            row["id"]: row["timestamp"]
            for row in self.client.get("/api/play/poses/").json()["results"]
        }
        before_value = json.dumps([poses_by_id[boundary.pk], boundary.pk], separators=(",", ":"))
        before_token = base64.urlsafe_b64encode(before_value.encode()).decode().rstrip("=")

        response = self.client.get(f"/api/play/poses/?before={before_token}")
        self.assertEqual(response.status_code, 200)
        result_ids = [row["id"] for row in response.json()["results"]]

        expected_ids = [interactions[i].pk for i in range(5)]
        self.assertEqual(result_ids, expected_ids)
        boundary_and_later_ids = {interactions[i].pk for i in range(5, 60)}
        self.assertFalse(boundary_and_later_ids & set(result_ids))


class PlaceConversationPushdownTests(APITestCase):
    """`conversation=place:<id>` pushes down into `_queryset`'s own DB filter

    (#3759 review Fix round 2), mirroring the existing `scene:`/room
    branches, rather than falling back to an unbounded-by-place Python scan.
    The FINAL results at each caller are correct either way -- both
    `PlaySearchView` and `PlayReadView._mark_conversation_read` already
    re-filter the fetched rows in Python against `_conversation(row)["key"]
    == conversation` regardless of whether the DB query was scoped -- so this
    is a scan-size/query-shape fix, not a data-integrity one, and the only
    way to actually observe it is to inspect what `_queryset` itself
    returns, before any caller's Python-level re-filter narrows it back down
    to the same correct answer either way.
    """

    def test_queryset_scopes_directly_to_the_named_place(self) -> None:
        account = AccountFactory()
        place_a = PlaceFactory()
        place_b = PlaceFactory()
        # All three writer_account=account (the "party" visibility branch) so
        # every row is visible to `account` regardless of place -- isolating
        # the assertion to the place: filter itself, not visible_to()'s own
        # place__isnull=True room-heard exclusion (a place-scoped interaction
        # is otherwise only visible to its writer/receivers, per
        # InteractionQuerySet.visible_to's own docstring).
        in_place_a = InteractionFactory(place=place_a, writer_account=account)
        InteractionFactory(place=place_b, writer_account=account)
        InteractionFactory(place=None, writer_account=account)

        factory = APIRequestFactory()
        django_request = factory.get("/api/play/search/")
        force_authenticate(django_request, user=account)
        request = Request(django_request)

        queryset, _ = _queryset(request, params={"conversation": f"place:{place_a.pk}"})

        # Only the row actually AT place_a comes back from the DB query
        # itself -- not place_b's row, and not the placeless one -- proving
        # the filter is a real WHERE clause, not merely "whatever happens to
        # survive a later Python re-filter that would produce the same
        # single-row answer regardless."
        self.assertEqual(list(queryset.values_list("id", flat=True)), [in_place_a.pk])


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


class PlayReadViewMarkConversationReadTests(APITestCase):
    """The mark-all-before-snapshot bulk dismissal (#3759 spec section 7).

    `{"conversation": ..., "before": ...}` marks every interaction the account
    can see in that conversation, timestamp <= before, in one call -- the
    bulk sibling of the explicit `{"poses": [...]}` per-pose path above.
    """

    def test_marks_authorized_conversation_history_read(self) -> None:
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        interactions = [InteractionFactory(scene=scene) for _ in range(5)]
        before = max(i.timestamp for i in interactions).isoformat()

        response = self.client.post(
            "/api/play/read/",
            {"conversation": f"scene:{scene.pk}", "before": before},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["marked"], 5)
        for interaction in interactions:
            self.assertTrue(
                InteractionReadReceipt.objects.filter(
                    account=account, interaction=interaction
                ).exists()
            )

    def test_never_marks_an_interaction_outside_visible_to(self) -> None:
        """A row this account cannot see (per `visible_to`) must never get a receipt,

        even though it lives in the SAME scene/conversation and is within the
        `before` bound -- the bulk path must route through the authorized
        `_rows()`/`_queryset()` queryset, never a raw `Interaction.objects.filter(...)`.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        visible = InteractionFactory(scene=scene)
        hidden = InteractionFactory(scene=scene, visibility=InteractionVisibility.VERY_PRIVATE)
        before = max(visible.timestamp, hidden.timestamp).isoformat()

        response = self.client.post(
            "/api/play/read/",
            {"conversation": f"scene:{scene.pk}", "before": before},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["marked"], 1)
        self.assertTrue(
            InteractionReadReceipt.objects.filter(account=account, interaction=visible).exists()
        )
        self.assertFalse(
            InteractionReadReceipt.objects.filter(account=account, interaction=hidden).exists()
        )

    def test_timestamp_after_before_is_not_marked(self) -> None:
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        earlier = InteractionFactory(scene=scene)
        later = InteractionFactory(scene=scene)
        # Force a deterministic ordering: `timestamp` is `auto_now_add`, so a
        # plain create() can't back- or forward-date it -- `.update()` bypasses
        # `save()`'s auto_now_add and the idmapper cache must be flushed after,
        # mirroring `test_interaction_services.test_cannot_delete_after_window`.
        earlier_ts = timezone.now() - timedelta(hours=2)
        later_ts = timezone.now() - timedelta(hours=1)
        Interaction.objects.filter(pk=earlier.pk).update(timestamp=earlier_ts)
        Interaction.objects.filter(pk=later.pk).update(timestamp=later_ts)
        Interaction.flush_cached_instance(earlier, force=True)
        Interaction.flush_cached_instance(later, force=True)

        response = self.client.post(
            "/api/play/read/",
            {"conversation": f"scene:{scene.pk}", "before": earlier_ts.isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["marked"], 1)
        self.assertTrue(
            InteractionReadReceipt.objects.filter(
                account=account, interaction_id=earlier.pk
            ).exists()
        )
        self.assertFalse(
            InteractionReadReceipt.objects.filter(account=account, interaction_id=later.pk).exists()
        )

    def test_repeat_call_is_idempotent(self) -> None:
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        interactions = [InteractionFactory(scene=scene) for _ in range(3)]
        before = max(i.timestamp for i in interactions).isoformat()
        body = {"conversation": f"scene:{scene.pk}", "before": before}

        first = self.client.post("/api/play/read/", body, format="json")
        second = self.client.post("/api/play/read/", body, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["marked"], 3)
        self.assertEqual(second.json()["marked"], 0)
        self.assertEqual(
            InteractionReadReceipt.objects.filter(
                account=account, interaction_id__in=[i.pk for i in interactions]
            ).count(),
            3,
        )

    def test_requires_a_before_timestamp(self) -> None:
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        response = self.client.post(
            "/api/play/read/", {"conversation": f"scene:{scene.pk}"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_both_conversation_and_poses_in_one_request(self) -> None:
        """Supplying both shapes at once is undefined -- reject rather than

        silently favoring the bulk path and dropping `poses` with no signal.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        interaction = InteractionFactory(scene=scene)
        response = self.client.post(
            "/api/play/read/",
            {
                "conversation": f"scene:{scene.pk}",
                "before": interaction.timestamp.isoformat(),
                "poses": [{"id": interaction.pk, "timestamp": interaction.timestamp.isoformat()}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not both", response.json()["detail"])
        self.assertFalse(InteractionReadReceipt.objects.filter(account=account).exists())

    def test_requires_authentication(self) -> None:
        response = self.client.post(
            "/api/play/read/",
            {"conversation": "scene:1", "before": "2026-01-01T00:00:00Z"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_rejects_an_unrecognized_conversation_ref(self) -> None:
        """The actual production bug shape (#3759 review finding C1): a bare

        scene id like ``"42"`` -- what `GameWindow.tsx` used to send before the
        frontend fix -- matches none of `_conversation()`'s own possible output
        shapes. Before this guard, `_queryset` applied no scene filter at all (no
        branch matched), `pairs` filtered down to nothing (no row's real
        `"scene:42"` ref ever equals the literal `"42"`), and the endpoint
        silently reported `{"marked": 0}` with a 200 while having scanned the
        account's entire visible history. Must now be a 400, not a silent no-op.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        interaction = InteractionFactory(scene=scene)

        response = self.client.post(
            "/api/play/read/",
            {"conversation": str(scene.pk), "before": interaction.timestamp.isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(InteractionReadReceipt.objects.filter(account=account).exists())


class PlayConversationsViewTests(APITestCase):
    """`unread`/`directUnread` on `/api/play/conversations/` (#3759 review finding I7).

    The spec's own Design section explicitly staged `unread: 0` here until
    `InteractionReadReceipt` existed -- it now does (this branch's own Task 1/2),
    and `PlayThreadsView` already computes a real `unread` via `has_read`;
    `PlayConversationsView` was never revisited to match.
    """

    def test_unread_counts_only_poses_this_account_has_not_read(self) -> None:
        from world.scenes.read_state_services import mark_poses_read

        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        interactions = [InteractionFactory(scene=scene) for _ in range(3)]
        mark_poses_read(
            account=account,
            poses=[(interactions[0].pk, interactions[0].timestamp.isoformat())],
        )

        response = self.client.get("/api/play/conversations/")

        self.assertEqual(response.status_code, 200)
        row = next(r for r in response.json()["results"] if r["ref"]["key"] == f"scene:{scene.pk}")
        self.assertEqual(row["unread"], 2)
        self.assertEqual(row["directUnread"], 0)


class PlayThreadsViewTests(APITestCase):
    def test_requires_a_conversation_bound(self) -> None:
        """`PlayThreadsView` exists to group ONE conversation's rows into threads

        (per its own docstring/spec) -- without a bound it serialized (and ran an
        unbounded `has_read` IN-query over) the caller's ENTIRE authorized visible
        history. Mirrors `PlaySearchView`'s `has_bound` 400 pattern.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        response = self.client.get("/api/play/threads/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("conversation", response.json()["detail"])

    def test_groups_by_exchange_and_counts_the_answered_pose(self) -> None:
        """Built through the real writer rather than by hand-setting ``thread=``.

        Both rows ARE members under the shipped design - the answered pose is the
        first one, which is what makes it the anchor - so hand-setting both is a
        perfectly producible state and the fixtures elsewhere in this file do
        exactly that. Going through ``create_interaction`` here buys something
        narrower: it proves the writer itself puts the answered pose in the thread
        and orders it first, instead of only proving the reader groups a shape the
        test asserted into existence.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        target, reply = _reply_exchange(scene, account, "root pose", "a reply")
        InteractionFactory(scene=scene, content="unthreaded standalone")

        response = self.client.get(f"/api/play/threads/?conversation=scene:{scene.pk}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        thread_ids = {row["id"] for row in data["results"]}
        self.assertIn(str(reply.thread_id), thread_ids)
        threaded_row = next(r for r in data["results"] if r["id"] == str(reply.thread_id))
        # The anchor opens the exchange and is counted in it.
        self.assertEqual(threaded_row["visiblePoseCount"], 2)
        self.assertEqual(threaded_row["root"]["id"], str(target.pk))
        self.assertEqual(threaded_row["firstVisible"]["id"], str(target.pk))
        self.assertEqual(threaded_row["opening"], "root pose")
        self.assertEqual(threaded_row["latestVisible"]["id"], str(reply.pk))

    def test_a_nested_exchange_is_one_group_keyed_by_its_root(self) -> None:
        """Answering a reply nests a thread; the reader must still see ONE exchange.

        Without the root collapse this reports two groups for one back-and-forth,
        each opening on the wrong pose.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        target, reply = _reply_exchange(scene, account, "he swings", "she gives ground")
        nested = _reply_to(scene, account, reply, "he presses in")

        response = self.client.get(f"/api/play/threads/?conversation=scene:{scene.pk}")

        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        row = results[0]
        target.refresh_from_db()
        self.assertEqual(row["id"], str(target.thread_id))
        self.assertNotEqual(target.thread_id, nested.thread_id)
        self.assertEqual(row["visiblePoseCount"], 3)
        self.assertEqual(row["root"]["id"], str(target.pk))
        self.assertEqual(row["opening"], "he swings")
        self.assertEqual(row["latestVisible"]["id"], str(nested.pk))

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
        thread_of = dict(zip(synthetic_ids, _root_threads(len(synthetic_ids)), strict=True))
        rows = []
        for pose_id in synthetic_ids:
            rows.append(
                {
                    "id": pose_id,
                    "timestamp": shared_timestamp,
                    "thread_id": thread_of[pose_id],
                    "content": f"pose {pose_id}",
                    "mode": "pose",
                    "place": None,
                    "scene": None,
                    "receiver_persona_ids": [],
                    "persona": {"id": 1, "name": "Tester"},
                }
            )
            # A reply, so the group is a genuine thread rather than a lone pose.
            # Its id is above every root id, and the view sorts and pages by the
            # ROOT (`firstVisible`), so it cannot affect the ordering under test.
            rows.append(
                {
                    "id": pose_id + 1000,
                    "timestamp": shared_timestamp,
                    "thread_id": thread_of[pose_id],
                    "content": f"reply to {pose_id}",
                    "mode": "pose",
                    "place": None,
                    "scene": None,
                    "receiver_persona_ids": [],
                    "persona": {"id": 1, "name": "Tester"},
                }
            )

        with patch("world.scenes.play_views._rows", return_value=(rows, None)):
            # The default (no-cursor) request is exactly the path that 500'd before
            # the fix: `start_index = len(results) - limit = 3 > 0`, so `_page()`
            # unconditionally calls `_cursor(page[0])`, which needs `_row_key`'s
            # fallback to resolve -- the missing `latestVisiblePose` key crashed here.
            latest_response = self.client.get("/api/play/threads/?conversation=room")
            self.assertEqual(latest_response.status_code, 200)
            latest_page = latest_response.json()
            self.assertIsNotNone(latest_page["before"])

            earlier_response = self.client.get(
                f"/api/play/threads/?conversation=room&before={latest_page['before']}"
            )
            self.assertEqual(earlier_response.status_code, 200)
            earlier_page = earlier_response.json()

        latest_ids = [int(row["firstVisible"]["id"]) for row in latest_page["results"]]
        earlier_ids = [int(row["firstVisible"]["id"]) for row in earlier_page["results"]]

        # If the tie-break compared `str(id)` instead of `int(id)`, this sorted
        # order would instead be [100, 101, ..., 112, 90, 91, ..., 99] (lexical),
        # and the last-20 window would be a completely different, out-of-order set.
        self.assertEqual(latest_ids, list(range(93, 113)))
        # Only 3 groups (90, 91, 92) sort strictly before the boundary (id 93);
        # `_page()`'s `before` branch must stop there rather than padding the page
        # out to `limit` by overshooting past the boundary. This assertion used to
        # read `list(range(90, 110))` (20 rows, including the boundary row 93 and
        # everything up to 109) -- that was the pre-existing `_page()` overshoot
        # bug found incidentally during #3759, not intended pagination behavior;
        # corrected alongside the `_page()` fix (see `PlayPosesPaginationTests`).
        self.assertEqual(earlier_ids, [90, 91, 92])

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

        Layout (26 groups, page size 20): six two-pose threads at minutes
        01-06, then thread "A" whose root lands at minute 07 (so it
        sorts 7th) but whose reply lands 9 days later, then 19 more two-pose
        threads at minutes 08-26. Requesting everything strictly `after`
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

        def _thread(pose_id: int, timestamp: str, thread_id: str) -> list[dict]:
            """One genuine two-pose thread: a root at `timestamp`, then a reply.

            The reply's id and timestamp sit above every root under test, and the
            view sorts and pages by the root, so the reply cannot move a group.
            """
            return [
                _row(pose_id, timestamp, thread_id),
                _row(pose_id + 5000, "2026-02-01T00:00:00Z", thread_id),
            ]

        # One real thread per group key: t[1..6], then "A", then t[8..26].
        minted = _root_threads(26)
        thread_of = dict(zip([*range(1, 7), "A", *range(8, 27)], minted, strict=True))

        rows = []
        for i in range(1, 7):
            rows.extend(_thread(i, f"2026-01-01T00:{i:02d}:00Z", thread_of[i]))
        rows.append(_row(1000, "2026-01-01T00:07:00Z", thread_of["A"]))  # thread A's root
        rows.append(_row(2000, "2026-01-10T00:00:00Z", thread_of["A"]))  # A's reply, 9 days on
        for i in range(8, 27):
            rows.extend(_thread(i, f"2026-01-01T00:{i:02d}:00Z", thread_of[i]))

        # Build the "after" cursor for legacy pose 9 the same way `_cursor()` does,
        # without importing that private helper: base64(json([timestamp, id])).
        after_value = json.dumps(["2026-01-01T00:09:00Z", 9], separators=(",", ":"))
        after_token = base64.urlsafe_b64encode(after_value.encode()).decode().rstrip("=")

        with patch("world.scenes.play_views._rows", return_value=(rows, None)):
            response = self.client.get(f"/api/play/threads/?conversation=room&after={after_token}")

        self.assertEqual(response.status_code, 200)
        result_ids = [row["id"] for row in response.json()["results"]]
        # Thread "A" (root at minute 07) and legacy 8/9 all sort BEFORE the
        # minute-09 boundary and must never reappear once we've paged past it.
        self.assertNotIn(thread_of["A"], result_ids)
        self.assertNotIn(thread_of[8], result_ids)
        self.assertNotIn(thread_of[9], result_ids)
        self.assertEqual(result_ids[0], thread_of[10])

    def test_omits_poses_that_are_not_part_of_a_thread(self) -> None:
        """The endpoint is an index of reply threads, not a second pose feed.

        `thread_id` is set only on an explicit reply, so an ordinary pose has none
        and used to come back as its own single-pose `legacy:<id>` group. A scene
        where most poses are ordinary narration then reported dozens of "threads"
        and paged them 20 at a time, which no caller can filter client side because
        the paging happens on the server.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        _, first_reply = _reply_exchange(
            scene, account, "you came anyway", "you left the gate open"
        )
        _, second_reply = _reply_exchange(
            scene, account, "keep your voice down", "the steward is at the door"
        )
        for index in range(15):
            InteractionFactory(scene=scene, content=f"ordinary narration {index}")

        response = self.client.get(f"/api/play/threads/?conversation=scene:{scene.pk}")

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(
            {row["id"] for row in results},
            {str(first_reply.thread_id), str(second_reply.thread_id)},
        )
        self.assertTrue(all(row["root"] is not None for row in results))
        # The 15 ordinary poses contribute no group, and the two exchanges each
        # count their answered pose - 2 poses per exchange, not 1.
        self.assertEqual([row["visiblePoseCount"] for row in results], [2, 2])

    def test_a_thread_whose_reply_was_answered_still_shows_that_reply(self) -> None:
        """The render rule for a thread: its members PLUS its children's first members.

        Answering an unanswered reply MOVES that reply into a child thread, so a
        consumer that grouped by ``thread_id`` alone would lose it and go one short
        per answered child. Grouping by ``root`` takes the union of the whole tree,
        so the exchange stays whole. Asserted on the pose that moved.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        target, first = _reply_exchange(scene, account, "he swings", "she gives ground")
        second = _reply_to(scene, account, first, "he presses in")

        # `first` was moved out of the thread it was written into.
        moved = Interaction.objects.get(pk=first.pk)
        self.assertNotEqual(moved.thread_id, target.thread_id)
        self.assertEqual(moved.thread_id, second.thread_id)

        response = self.client.get(f"/api/play/threads/?conversation=scene:{scene.pk}")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]

        self.assertEqual(len(results), 1)
        row = results[0]
        # All three poses, with the answered one opening: nothing went short.
        self.assertEqual(row["visiblePoseCount"], 3)
        self.assertEqual(row["root"]["id"], str(target.pk))
        self.assertEqual(row["latestVisible"]["id"], str(second.pk))

    def test_conversation_with_no_replies_returns_an_empty_page(self) -> None:
        """The common case: nobody used reply, so there is nothing to drill into.

        The consumer renders one line for this rather than listing the poses back.
        """
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        scene = SceneFactory()
        for index in range(4):
            InteractionFactory(scene=scene, content=f"ordinary narration {index}")

        response = self.client.get(f"/api/play/threads/?conversation=scene:{scene.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])


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


class PlayPosesQueryBudgetTests(APITestCase):
    """GET /api/play/poses/ must serve the reply chip without a per-row query.

    Regression guard for #3787. Three page-wide batches serve the chip and the
    grouping key, and none of them scales with the number of replies:

    - ``_thread_anchors`` - one ``Min(id)`` aggregate resolving every thread's
      anchor (and its parent thread's) in a single query.
    - ``_thread_roots`` - the derived top of each nesting tree, one query per
      nesting LEVEL for the whole page. A flat page, like this one, costs one.
    - ``_visible_parents`` - one batched ``visible_to`` check that returns the
      parents' timestamps too, so the chip needs no second lookup.

    That is 76 rather than the 74 of the stored-anchor shape: the anchor used to
    be a column joined in by ``select_related`` and the root another, so both were
    free to read and neither could be wrong. Deriving them costs two flat queries
    and removes two denormalized copies that could drift (a stored ``root`` did
    drift, and cost a real bug on this branch). `/game` is the primary surface
    where the parent chip renders, so this endpoint's own budget is pinned here
    rather than only inheriting ``InteractionViewSet``'s.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def _build_page(self, scene: object, *, reply_count: int) -> None:
        """Always 6 total poses (3 targets + 3 repliers) - only `reply_count`
        of the 3 repliers actually answer anything. Holding the total row count
        constant isolates the reply-handling cost: every OTHER cached_* field's
        per-row fallback cost (favorites, reactions, receivers, target personas,
        action links) stays identical between scenarios, so any difference in query
        count comes only from `_visible_parent_ids` and the anchor read.
        """
        targets = [InteractionFactory(scene=scene) for _ in range(3)]
        repliers = [InteractionFactory(scene=scene) for _ in range(3)]
        for i in range(reply_count):
            thread = InteractionThread.objects.create(
                holder_kind=InteractionThread.HolderKind.SCENE,
                holder_id=scene.pk,
                scene_id=scene.pk,
            )
            # The answered row is the first member, so it is the anchor (#3787).
            targets[i].thread = thread
            targets[i].save(update_fields=["thread"])
            repliers[i].thread = thread
            repliers[i].save(update_fields=["thread"])

    def test_query_budget_with_one_reply(self) -> None:
        """Baseline: 6 total poses, 1 of them a reply."""
        scene = SceneFactory()
        self._build_page(scene, reply_count=1)
        with self.assertNumQueries(76):
            response = self.client.get(f"/api/play/poses/?conversation=scene:{scene.pk}")
        assert response.status_code == 200
        assert len(response.json()["results"]) == 6

    def test_query_budget_does_not_scale_with_reply_count(self) -> None:
        """Same 6 total poses, all 3 are replies: the count must not grow. Each of
        the three batches above resolves the whole page at once, so tripling the
        replies adds no query."""
        scene = SceneFactory()
        self._build_page(scene, reply_count=3)
        with self.assertNumQueries(76):
            response = self.client.get(f"/api/play/poses/?conversation=scene:{scene.pk}")
        assert response.status_code == 200
        assert len(response.json()["results"]) == 6
