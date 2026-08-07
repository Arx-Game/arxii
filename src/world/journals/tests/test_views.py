"""Tests for journal API views."""

from unittest.mock import patch

from django.test import TestCase, tag
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.journals.constants import ResponseType
from world.journals.factories import JournalEntryFactory, JournalTagFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.scenes.models import Mute


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
