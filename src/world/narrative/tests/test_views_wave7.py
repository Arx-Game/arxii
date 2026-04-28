"""Tests for Wave 7 narrative API endpoints.

Task 7.1: POST /api/stories/{id}/send-ooc/
Task 7.2: GET/POST /api/narrative/gemits/
Task 7.3: GET/POST/DELETE /api/narrative/story-mutes/
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from core_management.test_utils import suppress_permission_errors
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.factories import GemitFactory, UserStoryMuteFactory
from world.narrative.models import Gemit, NarrativeMessage, NarrativeMessageDelivery, UserStoryMute
from world.narrative.services import send_narrative_message
from world.stories.constants import StoryScope
from world.stories.factories import StoryFactory


def _make_sheet_for_account(account):
    """Create a character + sheet attached to the given account."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return CharacterSheetFactory(character=char)


# ---------------------------------------------------------------------------
# Task 7.1: Story-scoped OOC sender
# ---------------------------------------------------------------------------


class SendOOCPermissionTest(APITestCase):
    """Permission tests for POST /api/stories/{id}/send-ooc/."""

    @classmethod
    def setUpTestData(cls):
        cls.lead_gm_account = AccountFactory()
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_account)
        cls.gm_table = GMTableFactory(gm=cls.lead_gm_profile)

        cls.player_account = AccountFactory()
        cls.other_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        # CHARACTER-scope story linked to gm_table
        cls.char_sheet = _make_sheet_for_account(cls.player_account)
        cls.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=cls.char_sheet,
            primary_table=cls.gm_table,
        )

    def _url(self):
        return reverse("story-detail", kwargs={"pk": self.story.pk}) + "send-ooc/"

    def test_lead_gm_can_send_ooc(self):
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.post(self._url(), {"body": "An OOC announcement."}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert NarrativeMessage.objects.filter(related_story=self.story).exists()

    def test_staff_can_send_ooc(self):
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.post(self._url(), {"body": "Staff OOC notice."}, format="json")
        assert response.status_code == status.HTTP_201_CREATED

    @suppress_permission_errors
    def test_non_lead_gm_player_rejected(self):
        self.client.force_authenticate(user=self.other_account)
        response = self.client.post(self._url(), {"body": "Hacker OOC."}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @suppress_permission_errors
    def test_unauthenticated_rejected(self):
        response = self.client.post(self._url(), {"body": "Anon OOC."}, format="json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_empty_body_rejected(self):
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.post(self._url(), {"body": ""}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class SendOOCDispatchTest(APITestCase):
    """Content tests for POST /api/stories/{id}/send-ooc/.

    Uses setUp (not setUpTestData) so each test starts with a clean story
    — NarrativeMessage.objects.get(related_story=...) won't find multiple rows.
    """

    def setUp(self):
        self.lead_gm_account = AccountFactory()
        self.lead_gm_profile = GMProfileFactory(account=self.lead_gm_account)
        self.gm_table = GMTableFactory(gm=self.lead_gm_profile)

        self.player_account = AccountFactory()
        self.char_sheet = _make_sheet_for_account(self.player_account)

        self.story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=self.char_sheet,
            primary_table=self.gm_table,
        )

    def _url(self):
        return reverse("story-detail", kwargs={"pk": self.story.pk}) + "send-ooc/"

    def test_response_has_correct_fields(self):
        self.client.force_authenticate(user=self.lead_gm_account)
        response = self.client.post(
            self._url(), {"body": "A notice.", "ooc_note": "Staff note."}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.data
        assert data["body"] == "A notice."
        assert data["category"] == NarrativeCategory.STORY
        assert data["related_story"] == self.story.pk

    def test_related_story_populated(self):
        self.client.force_authenticate(user=self.lead_gm_account)
        self.client.post(self._url(), {"body": "Notice."}, format="json")
        msg = NarrativeMessage.objects.get(related_story=self.story)
        assert msg.related_story == self.story

    def test_delivery_row_created_for_character_scope(self):
        """CHARACTER scope: delivery goes to story.character_sheet."""
        self.client.force_authenticate(user=self.lead_gm_account)
        self.client.post(self._url(), {"body": "Notice."}, format="json")
        assert NarrativeMessageDelivery.objects.filter(
            message__related_story=self.story,
            recipient_character_sheet=self.char_sheet,
        ).exists()

    def test_ooc_note_persisted(self):
        self.client.force_authenticate(user=self.lead_gm_account)
        self.client.post(
            self._url(), {"body": "IC notice.", "ooc_note": "GM private note."}, format="json"
        )
        msg = NarrativeMessage.objects.get(related_story=self.story)
        assert msg.ooc_note == "GM private note."

    def test_no_primary_table_rejects_non_staff(self):
        """Story without a primary_table cannot have a Lead GM — non-staff rejected."""
        story_no_table = StoryFactory(scope=StoryScope.CHARACTER, primary_table=None)
        other_gm_account = AccountFactory()
        GMProfileFactory(account=other_gm_account)
        url = reverse("story-detail", kwargs={"pk": story_no_table.pk}) + "send-ooc/"
        self.client.force_authenticate(user=other_gm_account)
        response = self.client.post(url, {"body": "Notice."}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# Task 7.2: Gemit ViewSet
# ---------------------------------------------------------------------------


GEMITS_URL = "/api/narrative/gemits/"


class GemitListTest(APITestCase):
    """GET /api/narrative/gemits/ — any authenticated user can list."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.staff = AccountFactory(is_staff=True)

    def test_authenticated_can_list(self):
        GemitFactory()
        GemitFactory()
        self.client.force_authenticate(user=self.user)
        response = self.client.get(GEMITS_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 2

    @suppress_permission_errors
    def test_unauthenticated_rejected(self):
        response = self.client.get(GEMITS_URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


class GemitFilterTest(APITestCase):
    """Filtering by related_era and related_story."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.story = StoryFactory()
        cls.gemit_with_story = GemitFactory(related_story=cls.story)
        cls.gemit_no_story = GemitFactory()

    def test_filter_by_related_story(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(GEMITS_URL, {"related_story": self.story.pk})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == self.gemit_with_story.pk


class GemitBroadcastTest(APITestCase):
    """POST /api/narrative/gemits/ — staff-only broadcast."""

    def setUp(self):
        self.staff = AccountFactory(is_staff=True)
        self.regular = AccountFactory()

    def test_staff_creates_gemit(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(GEMITS_URL, {"body": "Server announcement!"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Gemit.objects.filter(body="Server announcement!").exists()

    def test_gemit_response_has_correct_shape(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(GEMITS_URL, {"body": "Broadcast."}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.data
        assert "id" in data
        assert "body" in data
        assert "sent_at" in data

    @suppress_permission_errors
    def test_non_staff_rejected(self):
        self.client.force_authenticate(user=self.regular)
        response = self.client.post(GEMITS_URL, {"body": "Hacker broadcast."}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_empty_body_rejected(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(GEMITS_URL, {"body": ""}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_blank_body_rejected(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(GEMITS_URL, {"body": "   "}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_related_story_optional(self):
        story = StoryFactory()
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            GEMITS_URL,
            {"body": "Story-linked broadcast.", "related_story": story.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        gemit = Gemit.objects.get(pk=response.data["id"])
        assert gemit.related_story == story

    def test_gemit_row_created_on_broadcast(self):
        """Broadcast creates persistent Gemit row regardless of session push."""
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(GEMITS_URL, {"body": "Broadcast."}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Gemit.objects.filter(pk=response.data["id"]).exists()


# ---------------------------------------------------------------------------
# Task 7.3: UserStoryMute ViewSet
# ---------------------------------------------------------------------------


MUTES_URL = "/api/narrative/story-mutes/"


class UserStoryMuteListTest(APITestCase):
    """GET /api/narrative/story-mutes/ — list own mutes."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.other = AccountFactory()
        cls.story = StoryFactory()

    def test_lists_own_mutes(self):
        UserStoryMuteFactory(account=self.user, story=self.story)
        UserStoryMuteFactory(account=self.other)  # different user
        self.client.force_authenticate(user=self.user)
        response = self.client.get(MUTES_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["story"] == self.story.pk

    @suppress_permission_errors
    def test_unauthenticated_rejected(self):
        response = self.client.get(MUTES_URL)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


class UserStoryMuteCreateTest(APITestCase):
    """POST /api/narrative/story-mutes/ — mute a story."""

    def setUp(self):
        self.user = AccountFactory()
        self.story = StoryFactory()

    def test_create_mute(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(MUTES_URL, {"story": self.story.pk}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert UserStoryMute.objects.filter(account=self.user, story=self.story).exists()

    def test_mute_response_shape(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(MUTES_URL, {"story": self.story.pk}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.data
        assert "id" in data
        assert data["story"] == self.story.pk
        assert "muted_at" in data

    def test_missing_story_rejected(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(MUTES_URL, {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_mute_rejected_by_serializer(self):
        """Serializer validate() catches duplicate before DB unique constraint fires."""
        UserStoryMuteFactory(account=self.user, story=self.story)
        self.client.force_authenticate(user=self.user)
        response = self.client.post(MUTES_URL, {"story": self.story.pk}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class UserStoryMuteDuplicateTest(TransactionTestCase):
    """Duplicate mute (same account+story) is rejected at the DB constraint level."""

    def test_duplicate_mute_rejected(self):
        user = AccountFactory()
        story = StoryFactory()
        UserStoryMuteFactory(account=user, story=story)
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(MUTES_URL, {"story": story.pk}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class UserStoryMuteDeleteTest(APITestCase):
    """DELETE /api/narrative/story-mutes/{id}/ — unmute."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory()
        cls.other = AccountFactory()
        cls.story = StoryFactory()

    def setUp(self):
        self.mute = UserStoryMuteFactory(account=self.user, story=self.story)

    def _url(self):
        return f"{MUTES_URL}{self.mute.pk}/"

    def test_owner_can_delete(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self._url())
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not UserStoryMute.objects.filter(pk=self.mute.pk).exists()

    @suppress_permission_errors
    def test_non_owner_rejected(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.delete(self._url())
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )

    def test_staff_can_delete_own_mute(self):
        """Staff can manage their own mutes; admin panel manages others' mutes."""
        staff = AccountFactory(is_staff=True)
        staff_mute = UserStoryMuteFactory(account=staff, story=self.story)
        self.client.force_authenticate(user=staff)
        url = f"{MUTES_URL}{staff_mute.pk}/"
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT


# ---------------------------------------------------------------------------
# Task 7.3: Mute suppression in send_narrative_message
# ---------------------------------------------------------------------------


class MuteSuppressTest(TestCase):
    """UserStoryMute suppresses real-time push but preserves delivery row."""

    def test_muted_user_skips_realtime_push_but_delivery_row_created(self):
        """Muted user: delivery row EXISTS, character.msg NOT called."""
        user = AccountFactory()
        sheet = _make_sheet_for_account(user)
        story = StoryFactory()
        UserStoryMuteFactory(account=user, story=story)

        fake_session = mock.Mock()
        with (
            mock.patch.object(sheet.character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(sheet.character, "msg") as msg_mock,
        ):
            msg = send_narrative_message(
                recipients=[sheet],
                body="Hidden from muted user.",
                category=NarrativeCategory.STORY,
                related_story=story,
            )

        # Delivery row still created.
        assert NarrativeMessageDelivery.objects.filter(
            message=msg, recipient_character_sheet=sheet
        ).exists()
        # Real-time push skipped.
        msg_mock.assert_not_called()

    def test_non_muted_user_receives_realtime_push(self):
        """Non-muted user gets real-time push as normal."""
        user = AccountFactory()
        sheet = _make_sheet_for_account(user)
        story = StoryFactory()
        # No UserStoryMute created.

        fake_session = mock.Mock()
        with (
            mock.patch.object(sheet.character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(sheet.character, "msg") as msg_mock,
        ):
            send_narrative_message(
                recipients=[sheet],
                body="Visible to non-muted user.",
                category=NarrativeCategory.STORY,
                related_story=story,
            )

        msg_mock.assert_called_once()

    def test_mute_on_different_story_does_not_suppress(self):
        """Mute on story A does not suppress push for story B."""
        user = AccountFactory()
        sheet = _make_sheet_for_account(user)
        story_a = StoryFactory()
        story_b = StoryFactory()
        UserStoryMuteFactory(account=user, story=story_a)

        fake_session = mock.Mock()
        with (
            mock.patch.object(sheet.character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(sheet.character, "msg") as msg_mock,
        ):
            send_narrative_message(
                recipients=[sheet],
                body="Story B message.",
                category=NarrativeCategory.STORY,
                related_story=story_b,  # Different story — mute doesn't apply.
            )

        msg_mock.assert_called_once()

    def test_no_related_story_no_mute_suppression(self):
        """Messages without related_story are never mute-suppressed."""
        user = AccountFactory()
        sheet = _make_sheet_for_account(user)
        story = StoryFactory()
        UserStoryMuteFactory(account=user, story=story)

        fake_session = mock.Mock()
        with (
            mock.patch.object(sheet.character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(sheet.character, "msg") as msg_mock,
        ):
            send_narrative_message(
                recipients=[sheet],
                body="System message, no story.",
                category=NarrativeCategory.SYSTEM,
                related_story=None,  # No story — mute irrelevant.
            )

        msg_mock.assert_called_once()

    def test_mixed_muted_and_not_muted_recipients(self):
        """In a multi-recipient send, only muted users skip the push."""
        muted_user = AccountFactory()
        unmuted_user = AccountFactory()
        muted_sheet = _make_sheet_for_account(muted_user)
        unmuted_sheet = _make_sheet_for_account(unmuted_user)
        story = StoryFactory()
        UserStoryMuteFactory(account=muted_user, story=story)

        muted_session = mock.Mock()
        unmuted_session = mock.Mock()
        with (
            mock.patch.object(muted_sheet.character.sessions, "all", return_value=[muted_session]),
            mock.patch.object(muted_sheet.character, "msg") as muted_msg_mock,
            mock.patch.object(
                unmuted_sheet.character.sessions, "all", return_value=[unmuted_session]
            ),
            mock.patch.object(unmuted_sheet.character, "msg") as unmuted_msg_mock,
        ):
            send_narrative_message(
                recipients=[muted_sheet, unmuted_sheet],
                body="Mixed broadcast.",
                category=NarrativeCategory.STORY,
                related_story=story,
            )

        muted_msg_mock.assert_not_called()
        unmuted_msg_mock.assert_called_once()
