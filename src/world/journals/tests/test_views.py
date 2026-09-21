"""Tests for journal API views."""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import PosthumousJournalDisposition, RetortConsent
from world.estates.factories import EstateSettlementFactory
from world.journals.constants import JournalKind, PosthumousOverride, ResponseType
from world.journals.factories import (
    JournalBequestGrantFactory,
    JournalEntryFactory,
    JournalTagFactory,
)
from world.journals.services import annotate_can_retort, base_entries_queryset, can_retort
from world.relationships.constants import LabelAwareness, TypeValence
from world.relationships.factories import RelationshipTypeFactory
from world.relationships.services import declare_label, get_or_create_side
from world.roster.factories import PlayerDataFactory, RosterTenureFactory, grant_test_tenure
from world.scenes.factories import PersonaFactory
from world.scenes.models import Block, Mute


class JournalEntryListTests(TestCase):
    """Tests for listing public journal entries."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        cls.user = AccountFactory()
        cls.sheet1 = CharacterSheetFactory()
        cls.sheet2 = CharacterSheetFactory()
        cls.public_entry = JournalEntryFactory(
            author=cls.sheet1, title="Public Post", is_public=True
        )
        cls.private_entry = JournalEntryFactory(
            author=cls.sheet1, title="Private Post", is_public=False
        )
        cls.other_public = JournalEntryFactory(
            author=cls.sheet2, title="Other Public", is_public=True
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_only_public(self) -> None:
        """Public listing excludes private entries."""
        response = self.client.get("/api/journals/entries/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [e["title"] for e in response.data["results"]]
        self.assertIn("Public Post", titles)
        self.assertIn("Other Public", titles)
        self.assertNotIn("Private Post", titles)

    def test_list_includes_response_count(self) -> None:
        """List entries include response_count annotation."""
        response = self.client.get("/api/journals/entries/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for entry in response.data["results"]:
            self.assertIn("response_count", entry)

    def test_list_rows_carry_body_and_kind(self) -> None:
        """Collapsed rows carry body (first-lines preview) and kind (banding) (#3941)."""
        response = self.client.get("/api/journals/entries/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for entry in response.data["results"]:
            self.assertEqual(entry["kind"], JournalKind.ENTRY)
        rows = {e["id"]: e for e in response.data["results"]}
        self.assertEqual(rows[self.public_entry.pk]["body"], self.public_entry.body)

    def test_unauthenticated_rejected(self) -> None:
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/journals/entries/")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class JournalEntryFilterTests(TestCase):
    """Tests for filtering journal entries."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        cls.user = AccountFactory()
        cls.sheet1 = CharacterSheetFactory()
        cls.sheet2 = CharacterSheetFactory()
        cls.entry1 = JournalEntryFactory(author=cls.sheet1, title="Entry A", is_public=True)
        cls.entry2 = JournalEntryFactory(author=cls.sheet2, title="Entry B", is_public=True)
        cls.tag = JournalTagFactory(entry=cls.entry1, name="adventure")

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_filter_by_author(self) -> None:
        """Can filter entries by author character ID."""
        response = self.client.get(f"/api/journals/entries/?author={self.sheet1.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [e["title"] for e in response.data["results"]]
        self.assertIn("Entry A", titles)
        self.assertNotIn("Entry B", titles)

    def test_filter_by_tag(self) -> None:
        """Can filter entries by tag name."""
        response = self.client.get("/api/journals/entries/?tag=adventure")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [e["title"] for e in response.data["results"]]
        self.assertIn("Entry A", titles)
        self.assertNotIn("Entry B", titles)


class JournalEntryFeedBlockMuteTests(TestCase):
    """#2996 Decision 2 — journal feed visibility: block hides both directions, mute one-way."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.viewer_player = PlayerDataFactory()
        cls.viewer_tenure = RosterTenureFactory(player_data=cls.viewer_player)

        cls.blocked_player = PlayerDataFactory()
        cls.blocked_tenure = RosterTenureFactory(player_data=cls.blocked_player)
        cls.blocked_entry = JournalEntryFactory(
            author=cls.blocked_tenure.roster_entry.character_sheet,
            title="From Blocked",
            is_public=True,
        )

        cls.muted_player = PlayerDataFactory()
        cls.muted_tenure = RosterTenureFactory(player_data=cls.muted_player)
        cls.muted_entry = JournalEntryFactory(
            author=cls.muted_tenure.roster_entry.character_sheet,
            title="From Muted",
            is_public=True,
        )

        cls.control_player = PlayerDataFactory()
        cls.control_tenure = RosterTenureFactory(player_data=cls.control_player)
        cls.control_entry = JournalEntryFactory(
            author=cls.control_tenure.roster_entry.character_sheet,
            title="From Control",
            is_public=True,
        )

    def setUp(self) -> None:
        self.client = APIClient()

    def _titles(self) -> list[str]:
        response = self.client.get("/api/journals/entries/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [e["title"] for e in response.data["results"]]

    def test_no_block_or_mute_shows_everything(self) -> None:
        self.client.force_authenticate(user=self.viewer_player.account)
        titles = self._titles()
        self.assertIn("From Blocked", titles)
        self.assertIn("From Muted", titles)
        self.assertIn("From Control", titles)

    def test_blocked_authors_entry_hidden_from_viewer(self) -> None:
        Block.objects.create(
            owner=self.viewer_player, blocked_player=self.blocked_player, account_level=True
        )
        self.client.force_authenticate(user=self.viewer_player.account)
        titles = self._titles()
        self.assertNotIn("From Blocked", titles)
        self.assertIn("From Control", titles)

    def test_block_hides_the_viewers_own_entries_from_the_blocked_author_too(self) -> None:
        """Both directions (#2996): the blocked account also loses the viewer's entries."""
        Block.objects.create(
            owner=self.viewer_player, blocked_player=self.blocked_player, account_level=True
        )
        viewer_entry = JournalEntryFactory(
            author=self.viewer_tenure.roster_entry.character_sheet,
            title="From Viewer",
            is_public=True,
        )
        self.client.force_authenticate(user=self.blocked_player.account)
        titles = self._titles()
        self.assertNotIn(viewer_entry.title, titles)
        self.assertIn("From Control", titles)

    def test_mute_hides_only_from_the_muters_own_feed(self) -> None:
        Mute.objects.create(
            owner=self.viewer_player,
            muted_persona=PersonaFactory(),
            muted_player=self.muted_player,
            account_level=True,
        )
        self.client.force_authenticate(user=self.viewer_player.account)
        titles = self._titles()
        self.assertNotIn("From Muted", titles)
        self.assertIn("From Control", titles)

        # The muted author's own feed (and any other viewer's) is unaffected -- one-way.
        self.client.force_authenticate(user=self.muted_player.account)
        other_titles = self._titles()
        self.assertIn("From Muted", other_titles)

    def test_anonymous_viewer_rejected_not_crashed(self) -> None:
        response = self.client.get("/api/journals/entries/")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class JournalEntryMineTests(TestCase):
    """Tests for the 'mine' endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.public_entry = JournalEntryFactory(author=cls.sheet, title="My Public", is_public=True)
        cls.private_entry = JournalEntryFactory(
            author=cls.sheet, title="My Private", is_public=False
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_mine_includes_private(self, mock_get_char: object) -> None:
        """Own entries endpoint includes private entries."""
        mock_get_char.return_value = self.character
        response = self.client.get("/api/journals/entries/mine/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [e["title"] for e in response.data["results"]]
        self.assertIn("My Public", titles)
        self.assertIn("My Private", titles)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_mine_no_character(self, mock_get_char: object) -> None:
        """Returns 404 when no character found."""
        mock_get_char.return_value = None
        response = self.client.get("/api/journals/entries/mine/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class JournalEntryRetrieveTests(TestCase):
    """Tests for retrieving a single journal entry."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.other_sheet = CharacterSheetFactory()
        cls.public_entry = JournalEntryFactory(author=cls.sheet, title="Viewable", is_public=True)
        cls.private_entry = JournalEntryFactory(author=cls.sheet, title="Secret", is_public=False)
        cls.other_private = JournalEntryFactory(
            author=cls.other_sheet, title="Other Secret", is_public=False
        )

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_retrieve_public_entry(self) -> None:
        """Any authenticated user can retrieve a public entry."""
        response = self.client.get(f"/api/journals/entries/{self.public_entry.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Viewable")
        self.assertIn("body", response.data)
        self.assertIn("responses", response.data)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_retrieve_own_private_entry(self, mock_get_char: object) -> None:
        """Author can retrieve their own private entry."""
        mock_get_char.return_value = self.character
        response = self.client.get(f"/api/journals/entries/{self.private_entry.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Secret")

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_cannot_retrieve_other_private_entry(self, mock_get_char: object) -> None:
        """Cannot retrieve another character's private entry."""
        mock_get_char.return_value = self.character
        response = self.client.get(f"/api/journals/entries/{self.other_private.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class JournalEntryCreateTests(TestCase):
    """Tests for creating journal entries."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        cls.character.db_account = cls.user
        cls.character.save()
        cls.sheet = CharacterSheetFactory(character=cls.character)

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @tag("postgres")
    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_create_entry_with_tags(
        self,
        mock_get_char: object,
        mock_award: object,
        mock_stat: object,
    ) -> None:
        """Can create an entry with tags.

        PG-only: ``create_journal_entry`` uses ``JournalTag.objects.bulk_create``,
        which skips the SharedMemoryModel idmap update. On the SQLite tier
        the integer-PK sequence resets between tests, so reused PKs collide
        with stale tag instances cached from prior tests (e.g. test_models'
        ``test_unique_tag_per_entry`` cached a "combat" tag at the reused
        pk). The prefetch in the create-response path then returns those
        stale-named instances. PG never reuses PKs after rollback, so the
        idmap collision can't occur in the parity tier.
        """
        mock_get_char.return_value = self.character
        data = {
            "title": "New Entry",
            "body": "Some text here.",
            "is_public": True,
            "tags": ["adventure", "drama"],
        }
        response = self.client.post("/api/journals/entries/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "New Entry")
        tag_names = [t["name"] for t in response.data["tags"]]
        self.assertIn("adventure", tag_names)
        self.assertIn("drama", tag_names)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_create_entry_no_character(
        self,
        mock_get_char: object,
        mock_award: object,
        mock_stat: object,
    ) -> None:
        """Returns 404 when no character found."""
        mock_get_char.return_value = None
        data = {"title": "X", "body": "Y", "is_public": False}
        response = self.client.post("/api/journals/entries/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_entry_unauthenticated(
        self,
        mock_award: object,
        mock_stat: object,
    ) -> None:
        """Unauthenticated users cannot create entries."""
        self.client.force_authenticate(user=None)
        data = {"title": "X", "body": "Y", "is_public": False}
        response = self.client.post("/api/journals/entries/", data, format="json")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class JournalEntryEditViewTests(TestCase):
    """Test PATCH /api/journals/entries/<id>/ endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.entry = JournalEntryFactory(author=self.sheet, is_public=True)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_edit_own_entry(self, mock_get_char: object) -> None:
        """Can PATCH own entry."""
        mock_get_char.return_value = self.character
        response = self.client.patch(
            f"/api/journals/entries/{self.entry.id}/",
            {"title": "Updated Title"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Updated Title")

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_cannot_edit_others_entry(self, mock_get_char: object) -> None:
        """Cannot PATCH someone else's entry."""
        other = CharacterSheetFactory()
        other_char = other.character
        mock_get_char.return_value = other_char
        response = self.client.patch(
            f"/api/journals/entries/{self.entry.id}/",
            {"title": "Hacked"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_cannot_edit_response_entry(self, mock_get_char: object) -> None:
        """PATCH on a praise/retort returns 400."""
        mock_get_char.return_value = self.character
        praise = JournalEntryFactory(
            author=self.sheet,
            parent=self.entry,
            response_type=ResponseType.PRAISE,
            is_public=True,
        )
        response = self.client.patch(
            f"/api/journals/entries/{praise.id}/",
            {"title": "Changed"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class JournalResponseCreateTests(TestCase):
    """Tests for creating responses (praise/retort) to journal entries."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Set up test data."""
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        cls.character.db_account = cls.user
        cls.character.save()
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.other_user = AccountFactory()
        cls.other_character = CharacterFactory()
        cls.other_character.db_account = cls.other_user
        cls.other_character.save()
        cls.other_sheet = CharacterSheetFactory(character=cls.other_character)
        cls.target_entry = JournalEntryFactory(
            author=cls.other_sheet, title="Target", is_public=True
        )
        cls.private_entry = JournalEntryFactory(
            author=cls.other_sheet,
            title="Private Target",
            is_public=False,
        )
        cls.own_entry = JournalEntryFactory(author=cls.sheet, title="Own Entry", is_public=True)

    def setUp(self) -> None:
        """Set up test client."""
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_create_praise_response(
        self,
        mock_get_char: object,
        mock_award: object,
        mock_stat: object,
    ) -> None:
        """Can create a praise response to a public entry."""
        mock_get_char.return_value = self.character
        data = {
            "title": "Well done!",
            "body": "Great entry.",
            "response_type": ResponseType.PRAISE,
        }
        response = self.client.post(
            f"/api/journals/entries/{self.target_entry.pk}/respond/",
            data,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["response_type"], ResponseType.PRAISE)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_cannot_respond_to_private(
        self,
        mock_get_char: object,
        mock_award: object,
        mock_stat: object,
    ) -> None:
        """Cannot respond to a private entry."""
        mock_get_char.return_value = self.character
        data = {
            "title": "Hmm",
            "body": "Nope.",
            "response_type": ResponseType.PRAISE,
        }
        response = self.client.post(
            f"/api/journals/entries/{self.private_entry.pk}/respond/",
            data,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_cannot_respond_to_own_entry(
        self,
        mock_get_char: object,
        mock_award: object,
        mock_stat: object,
    ) -> None:
        """Cannot respond to your own entry."""
        mock_get_char.return_value = self.character
        data = {
            "title": "Self praise",
            "body": "I'm great.",
            "response_type": ResponseType.PRAISE,
        }
        response = self.client.post(
            f"/api/journals/entries/{self.own_entry.pk}/respond/",
            data,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class JournalResponseMuteViewTests(TestCase):
    """#2996 Decision 2 — mute excludes a response from the entry AUTHOR's own read.

    The response persists normally (write-then-filter, covered in
    ``test_services.JournalResponseBlockMuteTest``); this covers the read-side exclusion at
    ``JournalEntryViewSet.retrieve``, scoped to the entry's own author reading their own entry.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.author_account = AccountFactory()
        cls.author_character = CharacterFactory()
        cls.author_character.db_account = cls.author_account
        cls.author_character.save()
        cls.author_sheet = CharacterSheetFactory(character=cls.author_character)
        cls.author_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.author_character,
            player_data__account=cls.author_account,
        )

        cls.muted_account = AccountFactory()
        cls.muted_character = CharacterFactory()
        cls.muted_character.db_account = cls.muted_account
        cls.muted_character.save()
        cls.muted_sheet = CharacterSheetFactory(character=cls.muted_character)
        cls.muted_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.muted_character,
            player_data__account=cls.muted_account,
        )

        cls.control_account = AccountFactory()
        cls.control_character = CharacterFactory()
        cls.control_character.db_account = cls.control_account
        cls.control_character.save()
        cls.control_sheet = CharacterSheetFactory(character=cls.control_character)
        cls.control_tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.control_character,
            player_data__account=cls.control_account,
        )

        cls.entry = JournalEntryFactory(author=cls.author_sheet, title="My Entry", is_public=True)
        cls.muted_response = JournalEntryFactory(
            author=cls.muted_sheet,
            parent=cls.entry,
            response_type=ResponseType.PRAISE,
            title="From Muted",
            is_public=True,
        )
        cls.control_response = JournalEntryFactory(
            author=cls.control_sheet,
            parent=cls.entry,
            response_type=ResponseType.PRAISE,
            title="From Control",
            is_public=True,
        )

    def setUp(self) -> None:
        self.client = APIClient()

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_author_view_excludes_muted_responder(self, mock_get_char: object) -> None:
        Mute.objects.create(
            owner=self.author_tenure.player_data,
            muted_persona=PersonaFactory(),
            muted_player=self.muted_tenure.player_data,
            account_level=True,
        )
        self.client.force_authenticate(user=self.author_account)
        mock_get_char.return_value = self.author_character

        response = self.client.get(f"/api/journals/entries/{self.entry.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [r["title"] for r in response.data["responses"]]
        self.assertNotIn("From Muted", titles)
        self.assertIn("From Control", titles)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_non_author_view_is_unaffected_by_authors_mute(self, mock_get_char: object) -> None:
        """Only the entry AUTHOR's own read is filtered -- any other viewer sees everything."""
        Mute.objects.create(
            owner=self.author_tenure.player_data,
            muted_persona=PersonaFactory(),
            muted_player=self.muted_tenure.player_data,
            account_level=True,
        )
        self.client.force_authenticate(user=self.control_account)
        mock_get_char.return_value = self.control_character

        response = self.client.get(f"/api/journals/entries/{self.entry.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [r["title"] for r in response.data["responses"]]
        self.assertIn("From Muted", titles)
        self.assertIn("From Control", titles)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_no_mute_shows_all_responses(self, mock_get_char: object) -> None:
        self.client.force_authenticate(user=self.author_account)
        mock_get_char.return_value = self.author_character

        response = self.client.get(f"/api/journals/entries/{self.entry.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [r["title"] for r in response.data["responses"]]
        self.assertIn("From Muted", titles)
        self.assertIn("From Control", titles)


class JournalPosthumousLeakTableTests(TestCase):
    """Viewset visibility tests for the #3287 spec's leak table.

    Rows covered: public feed pre-death (private stays hidden), SEALED entries post-death
    (never readable by anyone, feed or bequest), bequest read (recipient-only, no grant = no
    access), and revealed entries riding the same block/mute gate as ordinary public entries.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()
        cls.viewer_character = CharacterFactory()
        cls.viewer_sheet = CharacterSheetFactory(character=cls.viewer_character)

        cls.deceased_sheet = CharacterSheetFactory()
        cls.settlement = EstateSettlementFactory(character_sheet=cls.deceased_sheet)

        cls.unrevealed_private = JournalEntryFactory(
            author=cls.deceased_sheet, title="Still Private", is_public=False
        )
        cls.revealed_entry = JournalEntryFactory(
            author=cls.deceased_sheet,
            title="Revealed After Death",
            is_public=False,
            revealed_at=timezone.now(),
            revealed_by_settlement=cls.settlement,
        )
        cls.sealed_entry = JournalEntryFactory(
            author=cls.deceased_sheet,
            title="Sealed Forever",
            is_public=False,
            posthumous_override=PosthumousOverride.SEAL,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_public_feed_excludes_unrevealed_private(self) -> None:
        """Pre-death privacy unchanged: an unrevealed private entry never hits the feed."""
        response = self.client.get("/api/journals/entries/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [e["title"] for e in response.data["results"]]
        self.assertNotIn("Still Private", titles)
        self.assertNotIn("Sealed Forever", titles)

    def test_public_feed_includes_revealed_entry(self) -> None:
        """A revealed private entry surfaces in the public feed, still marked private."""
        response = self.client.get("/api/journals/entries/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = {e["title"]: e for e in response.data["results"]}
        self.assertIn("Revealed After Death", results)
        entry = results["Revealed After Death"]
        self.assertFalse(entry["is_public"])
        self.assertTrue(entry["is_posthumous"])

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_sealed_entry_never_retrievable_by_anyone(self, mock_get_char: object) -> None:
        """SEAL beats everything -- not even a granted bequest recipient can read it."""
        JournalBequestGrantFactory(
            recipient_sheet=self.viewer_sheet,
            deceased_sheet=self.deceased_sheet,
            created_by_settlement=self.settlement,
        )
        mock_get_char.return_value = self.viewer_character
        response = self.client.get(f"/api/journals/entries/{self.sealed_entry.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_deceased_corpus_without_grant_is_empty(self, mock_get_char: object) -> None:
        """No JournalBequestGrant -- browsing the deceased's corpus returns nothing."""
        mock_get_char.return_value = self.viewer_character
        response = self.client.get(f"/api/journals/entries/?deceased={self.deceased_sheet.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"], [])

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_granted_recipient_browses_non_sealed_corpus(self, mock_get_char: object) -> None:
        """A grant surfaces the non-sealed private entries, excluding the sealed one."""
        JournalBequestGrantFactory(
            recipient_sheet=self.viewer_sheet,
            deceased_sheet=self.deceased_sheet,
            created_by_settlement=self.settlement,
        )
        mock_get_char.return_value = self.viewer_character
        response = self.client.get(f"/api/journals/entries/?deceased={self.deceased_sheet.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [e["title"] for e in response.data["results"]]
        self.assertIn("Still Private", titles)
        self.assertIn("Revealed After Death", titles)
        self.assertNotIn("Sealed Forever", titles)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_deceased_listing_shape_is_unchanged(self, mock_get_char: object) -> None:
        """#3941 regression: ``?deceased=`` must keep its pre-#3941 response shape.

        No ``since_visit_count`` and no ``visited_at`` key (the bequest corpus isn't the
        viewer's own stream), and ``mark_visit=1`` must not stamp the viewer's
        ``journals_visited_at`` -- covers both the no-grant (empty) and granted
        (non-empty) cases.
        """
        mock_get_char.return_value = self.viewer_character
        self.assertIsNone(self.viewer_sheet.journals_visited_at)

        no_grant = self.client.get(
            f"/api/journals/entries/?deceased={self.deceased_sheet.pk}&mark_visit=1"
        )
        self.assertEqual(no_grant.status_code, status.HTTP_200_OK)
        self.assertNotIn("since_visit_count", no_grant.data)
        self.assertNotIn("visited_at", no_grant.data)
        self.viewer_sheet.refresh_from_db()
        self.assertIsNone(self.viewer_sheet.journals_visited_at)

        JournalBequestGrantFactory(
            recipient_sheet=self.viewer_sheet,
            deceased_sheet=self.deceased_sheet,
            created_by_settlement=self.settlement,
        )
        granted = self.client.get(
            f"/api/journals/entries/?deceased={self.deceased_sheet.pk}&mark_visit=1"
        )
        self.assertEqual(granted.status_code, status.HTTP_200_OK)
        self.assertNotIn("since_visit_count", granted.data)
        self.assertNotIn("visited_at", granted.data)
        self.viewer_sheet.refresh_from_db()
        self.assertIsNone(self.viewer_sheet.journals_visited_at)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_granted_recipient_can_retrieve_non_sealed_entry(self, mock_get_char: object) -> None:
        JournalBequestGrantFactory(
            recipient_sheet=self.viewer_sheet,
            deceased_sheet=self.deceased_sheet,
            created_by_settlement=self.settlement,
        )
        mock_get_char.return_value = self.viewer_character
        response = self.client.get(f"/api/journals/entries/{self.unrevealed_private.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_non_recipient_cannot_retrieve_private_entry(self, mock_get_char: object) -> None:
        """No grant at all -- the entry stays 404, same as any other private entry."""
        mock_get_char.return_value = self.viewer_character
        response = self.client.get(f"/api/journals/entries/{self.unrevealed_private.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class JournalPosthumousDispositionEndpointTests(TestCase):
    """GET/PATCH /api/journals/entries/disposition/ -- the sheet-level default (#3287)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()
        cls.character = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_get_returns_current_default(self, mock_get_char: object) -> None:
        mock_get_char.return_value = self.character
        response = self.client.get("/api/journals/entries/disposition/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["posthumous_journal_disposition"], PosthumousJournalDisposition.REVEAL
        )

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_patch_sets_seal(self, mock_get_char: object) -> None:
        mock_get_char.return_value = self.character
        response = self.client.patch(
            "/api/journals/entries/disposition/",
            {"disposition": "seal"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.sheet.refresh_from_db()
        self.assertEqual(
            self.sheet.posthumous_journal_disposition, PosthumousJournalDisposition.SEAL
        )

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_patch_rejects_invalid_value(self, mock_get_char: object) -> None:
        mock_get_char.return_value = self.character
        response = self.client.patch(
            "/api/journals/entries/disposition/",
            {"disposition": "nonsense"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class VisibilityRuleTests(TestCase):
    """#3941 Decision 1 — the one visibility rule, exercised through the list/retrieve API."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()
        cls.staff = AccountFactory(is_staff=True)
        cls.writer = CharacterSheetFactory()
        cls.reader = CharacterSheetFactory()
        cls.white = JournalEntryFactory(author=cls.writer, title="White", is_public=True)
        cls.black = JournalEntryFactory(author=cls.writer, title="Black", is_public=False)

    def setUp(self) -> None:
        self.client = APIClient()

    def _titles(self, user, character, **params):
        self.client.force_authenticate(user=user)
        with patch(
            "world.journals.views.JournalEntryViewSet._get_character", return_value=character
        ):
            response = self.client.get("/api/journals/entries/", params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {e["title"] for e in response.data["results"]}

    def test_reader_sees_white_only(self) -> None:
        self.assertEqual(self._titles(self.user, self.reader.character), {"White"})

    def test_author_sees_own_black_in_the_stream(self) -> None:
        self.assertEqual(self._titles(self.user, self.writer.character), {"White", "Black"})

    def test_staff_sees_black(self) -> None:
        self.assertEqual(self._titles(self.staff, self.reader.character), {"White", "Black"})

    def test_black_only_is_staff_only(self) -> None:
        self.assertEqual(self._titles(self.staff, self.reader.character, black_only=1), {"Black"})
        self.assertEqual(self._titles(self.user, self.reader.character, black_only=1), {"White"})

    def test_staff_retrieves_a_black_entry(self) -> None:
        self.client.force_authenticate(user=self.staff)
        with patch(
            "world.journals.views.JournalEntryViewSet._get_character",
            return_value=self.reader.character,
        ):
            response = self.client.get(f"/api/journals/entries/{self.black.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reader_cannot_retrieve_a_black_entry(self) -> None:
        self.client.force_authenticate(user=self.user)
        with patch(
            "world.journals.views.JournalEntryViewSet._get_character",
            return_value=self.reader.character,
        ):
            response = self.client.get(f"/api/journals/entries/{self.black.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class NewFiltersAndFieldsTests(TestCase):
    """#3941 — writer/about/kind/post_mortem filters and the new row fields."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()
        cls.reader = CharacterSheetFactory()
        cls.ilsavet = CharacterSheetFactory()
        cls.ilsavet.character.db_key = "Ilsavet"
        cls.ilsavet.character.save()
        cls.corvin = CharacterSheetFactory()
        cls.corvin.character.db_key = "Corvin"
        cls.corvin.character.save()
        cls.about_corvin = JournalEntryFactory(
            author=cls.ilsavet, title="About Corvin", is_public=True, about=cls.corvin
        )
        cls.plain = JournalEntryFactory(author=cls.ilsavet, title="Plain", is_public=True)
        cls.intro = JournalEntryFactory(
            author=cls.corvin, title="First", is_public=True, kind=JournalKind.FIRST_JOURNAL
        )
        cls.post_mortem = JournalEntryFactory(
            author=cls.corvin, title="Dead", is_public=False, revealed_at=timezone.now()
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _get(self, **params):
        with patch(
            "world.journals.views.JournalEntryViewSet._get_character",
            return_value=self.reader.character,
        ):
            response = self.client.get("/api/journals/entries/", params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_writer_name_search(self) -> None:
        titles = {e["title"] for e in self._get(writer="ilsa")["results"]}
        self.assertEqual(titles, {"About Corvin", "Plain"})

    def test_about_filter_and_fields(self) -> None:
        rows = self._get(about=self.corvin.pk)["results"]
        self.assertEqual([r["title"] for r in rows], ["About Corvin"])
        self.assertEqual(rows[0]["about"], self.corvin.pk)
        self.assertEqual(rows[0]["about_name"], "Corvin")
        self.assertFalse(rows[0]["can_retort"])
        self.assertFalse(rows[0]["is_own"])
        self.assertIn("ic_timestamp", rows[0])
        self.assertIn("author_persona_id", rows[0])

    def test_kind_and_introductions_alias(self) -> None:
        first_journal_titles = {e["title"] for e in self._get(kind="first_journal")["results"]}
        self.assertEqual(first_journal_titles, {"First"})
        introductions_titles = {e["title"] for e in self._get(kind="introductions")["results"]}
        self.assertEqual(introductions_titles, {"First"})

    def test_post_mortem_filter(self) -> None:
        self.assertEqual({e["title"] for e in self._get(post_mortem=1)["results"]}, {"Dead"})

    def test_visited_at_names_the_previous_visit_and_since_cuts_on_it(self) -> None:
        """The stream hands back the mark it is about to move, and ``?since=`` reads it.

        The reader cannot ask the server for "since my last visit" once the server has
        stamped the mark to now -- so the response names the moment instead, and the cut
        is the client passing that same moment back.
        """
        # No mark yet: nothing to point at, everything counts as new, and this request marks.
        first = self._get(mark_visit=1)
        self.assertIsNone(first["visited_at"])
        self.assertEqual(first["since_visit_count"], 4)
        self.reader.refresh_from_db()
        mark = self.reader.journals_visited_at
        self.assertIsNotNone(mark)

        # A later request reports the mark as stored, and nothing is newer than it yet.
        second = self._get()
        self.assertEqual(parse_datetime(second["visited_at"]), mark)
        self.assertEqual(second["since_visit_count"], 0)

        # One entry written after that moment, and the cut returns exactly it.
        JournalEntryFactory(author=self.ilsavet, title="Written since", is_public=True)
        cut = self._get(since=second["visited_at"])
        self.assertEqual([row["title"] for row in cut["results"]], ["Written since"])

    def test_mark_visit_zero_does_not_mark(self) -> None:
        """``?mark_visit=0`` must not be parsed as truthy (Python's bool("0") is True)."""
        self.assertIsNone(self.reader.journals_visited_at)
        self._get(mark_visit=0)
        self.reader.refresh_from_db()
        self.assertIsNone(self.reader.journals_visited_at)


class CanRetortAnnotationTests(TestCase):
    """#3941/#3957 — the ``viewer_can_retort`` annotation is ``services.can_retort`` in SQL.

    Two spellings of one rule (ADR-0307), so they are held against each other on every
    case the rule distinguishes: no viewer, the viewer's own entry, a writer open to
    anyone, a mutual hostile relationship label held with the viewer (#3957 — each side
    must have declared the other hostile), and a one-sided hostile label (never enough).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.viewer = CharacterSheetFactory()
        cls.viewer_tenure = grant_test_tenure(cls.viewer)
        cls.rival = RelationshipTypeFactory(name="Rival", valence=TypeValence.HOSTILE)

        stranger = CharacterSheetFactory()
        open_writer = CharacterSheetFactory()
        open_writer.retort_consent = RetortConsent.ANYONE
        open_writer.save(update_fields=["retort_consent"])

        mutual_rival = CharacterSheetFactory()
        mutual_rival_tenure = grant_test_tenure(mutual_rival)
        declare_label(
            side=get_or_create_side(source=cls.viewer, target=mutual_rival),
            type=cls.rival,
            awareness=LabelAwareness.PUBLIC,
            tenure=cls.viewer_tenure,
        )
        declare_label(
            side=get_or_create_side(source=mutual_rival, target=cls.viewer),
            type=cls.rival,
            awareness=LabelAwareness.PUBLIC,
            tenure=mutual_rival_tenure,
        )

        one_sided_rival = CharacterSheetFactory()
        one_sided_rival_tenure = grant_test_tenure(one_sided_rival)
        # Only ONE direction declares hostile — #3957's mutual_hostile requires both.
        declare_label(
            side=get_or_create_side(source=one_sided_rival, target=cls.viewer),
            type=cls.rival,
            awareness=LabelAwareness.PUBLIC,
            tenure=one_sided_rival_tenure,
        )

        cls.expected = {
            JournalEntryFactory(author=stranger, is_public=True).pk: False,
            JournalEntryFactory(author=open_writer, is_public=True).pk: True,
            JournalEntryFactory(author=mutual_rival, is_public=True).pk: True,
            JournalEntryFactory(author=one_sided_rival, is_public=True).pk: False,
            # Own entry: never retortable, whatever the consent or the labels say.
            JournalEntryFactory(author=cls.viewer, is_public=True).pk: False,
        }

    def _annotated(self, viewer: object) -> dict:
        rows = annotate_can_retort(base_entries_queryset(), viewer)
        return {entry.pk: bool(entry.viewer_can_retort) for entry in rows}

    def _predicate(self, viewer: object) -> dict:
        return {
            entry.pk: can_retort(viewer_sheet=viewer, author=entry.author)
            for entry in base_entries_queryset()
        }

    def test_annotation_and_service_agree_for_a_viewer(self) -> None:
        self.assertEqual(self._annotated(self.viewer), self.expected)
        self.assertEqual(self._predicate(self.viewer), self.expected)

    def test_annotation_and_service_agree_without_a_viewer(self) -> None:
        closed = dict.fromkeys(self.expected, False)
        self.assertEqual(self._annotated(None), closed)
        self.assertEqual(self._predicate(None), closed)


class JournalListQueryCountTests(TestCase):
    """#3941 — the feed's query count must not grow with the number of rows.

    Five entries by five different writers, all on the default RIVALS consent, which is
    the case that has to ask the database: serialized one row at a time it was one EXISTS
    per row, and the annotation is why it is now one for the page.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()
        cls.reader = CharacterSheetFactory()
        for index in range(5):
            JournalEntryFactory(
                author=CharacterSheetFactory(), title=f"Entry {index}", is_public=True
            )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _get(self, page_size: int) -> dict:
        with patch(
            "world.journals.views.JournalEntryViewSet._get_character",
            return_value=self.reader.character,
        ):
            response = self.client.get("/api/journals/entries/", {"page_size": page_size})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_query_count_is_flat_across_page_sizes(self) -> None:
        # Warm first: the row-independent lookups (the viewer's sheet, each author's
        # primary persona) are idmapper-cached, and it is the per-ROW cost being measured.
        self.assertEqual(len(self._get(5)["results"]), 5)
        self._get(2)

        with CaptureQueriesContext(connection) as two_rows:
            self.assertEqual(len(self._get(2)["results"]), 2)
        with CaptureQueriesContext(connection) as five_rows:
            self.assertEqual(len(self._get(5)["results"]), 5)

        self.assertEqual(
            len(five_rows.captured_queries),
            len(two_rows.captured_queries),
            f"the feed runs a query per row: {[q['sql'] for q in five_rows.captured_queries]}",
        )


class CreateEditWithAboutTests(TestCase):
    """#3941 — POST/PATCH accept and clear ``about``."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()
        cls.author = CharacterSheetFactory()
        cls.author.character.db_account = cls.user
        cls.author.character.save()
        cls.subject = CharacterSheetFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("world.journals.services.award_xp")
    @patch("world.journals.services.increment_stat")
    def test_create_then_clear_about(self, mock_stat, mock_award) -> None:
        with patch(
            "world.journals.views.JournalEntryViewSet._get_character",
            return_value=self.author.character,
        ):
            created = self.client.post(
                "/api/journals/entries/",
                {"title": "t", "body": "b", "is_public": True, "about": self.subject.pk},
                format="json",
            )
            self.assertEqual(created.status_code, status.HTTP_201_CREATED)
            self.assertEqual(created.data["about"], self.subject.pk)
            edited = self.client.patch(
                f"/api/journals/entries/{created.data['id']}/", {"about": None}, format="json"
            )
        self.assertEqual(edited.status_code, status.HTTP_200_OK)
        self.assertIsNone(edited.data["about"])


class SettingsEndpointTests(TestCase):
    """#3941, ADR-0307 — GET/PATCH the settings endpoint."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory()
        cls.sheet = CharacterSheetFactory()

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_and_patch_consent(self) -> None:
        with patch(
            "world.journals.views.JournalEntryViewSet._get_character",
            return_value=self.sheet.character,
        ):
            got = self.client.get("/api/journals/entries/disposition/")
            self.assertEqual(got.data["retort_consent"], "rivals")
            self.assertEqual(got.data["rewarded_posts_per_week"], 3)
            self.assertEqual(got.data["posts_this_week"], 0)
            patched = self.client.patch(
                "/api/journals/entries/disposition/", {"retort_consent": "anyone"}, format="json"
            )
        self.assertEqual(patched.status_code, status.HTTP_200_OK)
        self.assertEqual(patched.data["retort_consent"], "anyone")
        self.assertEqual(patched.data["posthumous_journal_disposition"], "reveal")
