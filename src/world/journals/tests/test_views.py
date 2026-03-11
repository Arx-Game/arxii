"""Tests for journal API views."""

from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.journals.constants import ResponseType
from world.journals.factories import JournalEntryFactory, JournalTagFactory


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
        assert response.status_code == status.HTTP_200_OK
        titles = [e["title"] for e in response.data["results"]]
        assert "Public Post" in titles
        assert "Other Public" in titles
        assert "Private Post" not in titles

    def test_list_includes_response_count(self) -> None:
        """List entries include response_count annotation."""
        response = self.client.get("/api/journals/entries/")
        assert response.status_code == status.HTTP_200_OK
        for entry in response.data["results"]:
            assert "response_count" in entry

    def test_unauthenticated_rejected(self) -> None:
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/journals/entries/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
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
        assert response.status_code == status.HTTP_200_OK
        titles = [e["title"] for e in response.data["results"]]
        assert "Entry A" in titles
        assert "Entry B" not in titles

    def test_filter_by_tag(self) -> None:
        """Can filter entries by tag name."""
        response = self.client.get("/api/journals/entries/?tag=adventure")
        assert response.status_code == status.HTTP_200_OK
        titles = [e["title"] for e in response.data["results"]]
        assert "Entry A" in titles
        assert "Entry B" not in titles


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
        assert response.status_code == status.HTTP_200_OK
        titles = [e["title"] for e in response.data["results"]]
        assert "My Public" in titles
        assert "My Private" in titles

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_mine_no_character(self, mock_get_char: object) -> None:
        """Returns 404 when no character found."""
        mock_get_char.return_value = None
        response = self.client.get("/api/journals/entries/mine/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


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
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Viewable"
        assert "body" in response.data
        assert "responses" in response.data

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_retrieve_own_private_entry(self, mock_get_char: object) -> None:
        """Author can retrieve their own private entry."""
        mock_get_char.return_value = self.character
        response = self.client.get(f"/api/journals/entries/{self.private_entry.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Secret"

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_cannot_retrieve_other_private_entry(self, mock_get_char: object) -> None:
        """Cannot retrieve another character's private entry."""
        mock_get_char.return_value = self.character
        response = self.client.get(f"/api/journals/entries/{self.other_private.pk}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


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

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_create_entry_with_tags(
        self,
        mock_get_char: object,
        mock_award: object,  # noqa: ARG002
        mock_stat: object,  # noqa: ARG002
    ) -> None:
        """Can create an entry with tags."""
        mock_get_char.return_value = self.character
        data = {
            "title": "New Entry",
            "body": "Some text here.",
            "is_public": True,
            "tags": ["adventure", "drama"],
        }
        response = self.client.post("/api/journals/entries/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "New Entry"
        tag_names = [t["name"] for t in response.data["tags"]]
        assert "adventure" in tag_names
        assert "drama" in tag_names

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_create_entry_no_character(
        self,
        mock_get_char: object,
        mock_award: object,  # noqa: ARG002
        mock_stat: object,  # noqa: ARG002
    ) -> None:
        """Returns 404 when no character found."""
        mock_get_char.return_value = None
        data = {"title": "X", "body": "Y", "is_public": False}
        response = self.client.post("/api/journals/entries/", data, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_entry_unauthenticated(
        self,
        mock_award: object,  # noqa: ARG002
        mock_stat: object,  # noqa: ARG002
    ) -> None:
        """Unauthenticated users cannot create entries."""
        self.client.force_authenticate(user=None)
        data = {"title": "X", "body": "Y", "is_public": False}
        response = self.client.post("/api/journals/entries/", data, format="json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
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
        mock_award: object,  # noqa: ARG002
        mock_stat: object,  # noqa: ARG002
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
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["response_type"] == ResponseType.PRAISE

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_cannot_respond_to_private(
        self,
        mock_get_char: object,
        mock_award: object,  # noqa: ARG002
        mock_stat: object,  # noqa: ARG002
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
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("world.journals.views.JournalEntryViewSet._get_character")
    def test_cannot_respond_to_own_entry(
        self,
        mock_get_char: object,
        mock_award: object,  # noqa: ARG002
        mock_stat: object,  # noqa: ARG002
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
        assert response.status_code == status.HTTP_400_BAD_REQUEST
