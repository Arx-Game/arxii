"""Tests for the StoryNote API (canonical three-layer rework).

StoryNote is append-only OOC authorial memory: never plain-player-visible,
never editable or deletable. The API follows the strict three-layer pattern:

- Layer 1 (CanAccessStoryNotes.has_permission): authenticated-only.
- Layer 1 object scope (has_object_permission): staff / story owner /
  active GM / Lead GM of the story's primary table — governs retrieve
  WITHOUT any ``?story=`` param (Issue-1 regression).
- Layer 2 (StoryNoteSerializer.validate_story): create-scope.
- List scope (StoryNoteViewSet.get_queryset): defense-in-depth, mirrors
  the bulletin / aggregate viewsets.

Permission matrix exercised:
- staff: list (with and without ?story=), create, retrieve own note
- non-staff story owner: list, create, retrieve by pk without ?story=
- active GM of the story: list + retrieve
- cross-story isolation: owner of X cannot see / retrieve / create on Y
- non-owner authenticated player: list 200 + empty, retrieve 404, create 400
- append-only: PATCH 405, DELETE 405
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.stories.factories import StoryFactory, StoryNoteFactory


class StoryNoteApiSetup(APITestCase):
    """Shared fixtures mirroring the bulletin GMProfile/owner/active-GM pattern.

    Accounts:
    - staff: staff account
    - owner_x: non-staff account owning story_x
    - owner_y: non-staff account owning story_y (isolation foil)
    - active_gm_user: non-staff account with a GMProfile in story_x.active_gms
    - lead_gm_user: non-staff account whose GMProfile owns story_x.primary_table
    - outsider: plain authenticated account with no relation to any story

    Stories:
    - story_x: owned by owner_x, active_gm_user is an active GM, primary_table
      owned by lead_gm_user's GMProfile
    - story_y: owned by owner_y only (isolation foil)

    Notes:
    - note_x: a seeded StoryNote on story_x
    - note_y: a seeded StoryNote on story_y
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="note_staff", is_staff=True)
        cls.owner_x = AccountFactory(username="note_owner_x")
        cls.owner_y = AccountFactory(username="note_owner_y")
        cls.active_gm_user = AccountFactory(username="note_active_gm")
        cls.lead_gm_user = AccountFactory(username="note_lead_gm")
        cls.outsider = AccountFactory(username="note_outsider")

        cls.active_gm_profile = GMProfileFactory(account=cls.active_gm_user)
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_user)
        cls.lead_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.story_x = StoryFactory(
            owners=[cls.owner_x],
            active_gms=[cls.active_gm_profile],
            primary_table=cls.lead_table,
        )
        cls.story_y = StoryFactory(owners=[cls.owner_y])

        cls.note_x = StoryNoteFactory(story=cls.story_x, body="x: seed idea")
        cls.note_y = StoryNoteFactory(story=cls.story_y, body="y: seed idea")

    def _auth(self, user: object) -> None:
        self.client.force_authenticate(user=user)

    def _list(self, story_pk: int | None = None) -> object:
        params = {"story": story_pk} if story_pk is not None else {}
        return self.client.get(reverse("storynote-list"), params)

    def _retrieve(self, pk: int) -> object:
        return self.client.get(reverse("storynote-detail", kwargs={"pk": pk}))

    def _create(self, story_pk: int, body: str = "appended note body") -> object:
        return self.client.post(
            reverse("storynote-list"),
            {"story": story_pk, "body": body},
            format="json",
        )

    @staticmethod
    def _ids(resp: object) -> set[int]:
        return {row["id"] for row in resp.json()["results"]}


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------


class StoryNoteStaffTests(StoryNoteApiSetup):
    """Staff: full access regardless of ?story= param."""

    def test_staff_list_with_story_param(self) -> None:
        self._auth(self.staff)
        resp = self._list(self.story_x.pk)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(self.note_x.pk, self._ids(resp))

    def test_staff_list_without_story_param(self) -> None:
        self._auth(self.staff)
        resp = self._list()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = self._ids(resp)
        self.assertIn(self.note_x.pk, ids)
        self.assertIn(self.note_y.pk, ids)

    def test_staff_can_create(self) -> None:
        self._auth(self.staff)
        resp = self._create(self.story_x.pk, "staff: betrayal arc")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_staff_can_retrieve_note(self) -> None:
        self._auth(self.staff)
        resp = self._retrieve(self.note_x.pk)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["id"], self.note_x.pk)


# ---------------------------------------------------------------------------
# Non-staff story owner — the Issue-1 regression
# ---------------------------------------------------------------------------


class StoryNoteOwnerTests(StoryNoteApiSetup):
    """Non-staff story owner: list, create, AND retrieve by pk WITHOUT ?story=.

    ``test_owner_can_retrieve_note_without_story_param`` is the Issue-1
    regression: the old has_permission read request.query_params["story"] on
    SAFE methods, so a detail GET (no ?story=) returned 403 before
    has_object_permission ran. With the rework it returns 200.
    """

    def test_owner_can_list(self) -> None:
        self._auth(self.owner_x)
        resp = self._list(self.story_x.pk)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(self.note_x.pk, self._ids(resp))

    def test_owner_can_create(self) -> None:
        self._auth(self.owner_x)
        resp = self._create(self.story_x.pk, "owner: later twist")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_owner_can_retrieve_note_without_story_param(self) -> None:
        """Issue-1 regression: detail GET with no ?story= must be 200."""
        self._auth(self.owner_x)
        resp = self._retrieve(self.note_x.pk)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["id"], self.note_x.pk)


# ---------------------------------------------------------------------------
# Active GM of the story
# ---------------------------------------------------------------------------


class StoryNoteActiveGmTests(StoryNoteApiSetup):
    """Active GM (story.active_gms) can list + retrieve notes on that story."""

    def test_active_gm_can_list(self) -> None:
        self._auth(self.active_gm_user)
        resp = self._list(self.story_x.pk)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn(self.note_x.pk, self._ids(resp))

    def test_active_gm_can_retrieve(self) -> None:
        self._auth(self.active_gm_user)
        resp = self._retrieve(self.note_x.pk)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["id"], self.note_x.pk)

    def test_lead_gm_can_retrieve(self) -> None:
        """Lead GM of the story's primary table also has access."""
        self._auth(self.lead_gm_user)
        resp = self._retrieve(self.note_x.pk)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Cross-story isolation
# ---------------------------------------------------------------------------


class StoryNoteCrossStoryIsolationTests(StoryNoteApiSetup):
    """Owner of story X must not reach story Y's notes by any route."""

    def test_owner_x_list_filtered_to_y_excludes_y_notes(self) -> None:
        self._auth(self.owner_x)
        resp = self._list(self.story_y.pk)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn(self.note_y.pk, self._ids(resp))

    def test_owner_x_retrieve_y_note_is_404(self) -> None:
        self._auth(self.owner_x)
        resp = self._retrieve(self.note_y.pk)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_x_create_on_y_is_400(self) -> None:
        self._auth(self.owner_x)
        resp = self._create(self.story_y.pk, "x trying to write on y")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Non-owner authenticated player (canonical scoped behavior)
# ---------------------------------------------------------------------------


class StoryNoteOutsiderTests(StoryNoteApiSetup):
    """Plain authenticated non-owner: matches the bulletin analogue.

    With a scoped get_queryset the analogue returns 200 + empty list (NOT
    403). Retrieving a foreign note is 404; creating is rejected 400 by
    validate_story.
    """

    def test_outsider_list_is_200_and_empty(self) -> None:
        self._auth(self.outsider)
        resp = self._list(self.story_x.pk)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["results"], [])

    def test_outsider_retrieve_foreign_note_is_404(self) -> None:
        self._auth(self.outsider)
        resp = self._retrieve(self.note_x.pk)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_outsider_create_is_400(self) -> None:
        self._auth(self.outsider)
        resp = self._create(self.story_x.pk, "outsider note")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_is_denied(self) -> None:
        resp = self._list(self.story_x.pk)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Append-only enforcement
# ---------------------------------------------------------------------------


class StoryNoteAppendOnlyTests(StoryNoteApiSetup):
    """PATCH and DELETE are not allowed — strictly 405 (tightened)."""

    def test_patch_is_405(self) -> None:
        self._auth(self.staff)
        resp = self.client.patch(
            reverse("storynote-detail", kwargs={"pk": self.note_x.pk}),
            {"body": "edited"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_is_405(self) -> None:
        self._auth(self.staff)
        resp = self.client.delete(
            reverse("storynote-detail", kwargs={"pk": self.note_x.pk}),
        )
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
