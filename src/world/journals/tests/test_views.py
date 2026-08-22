"""Tests for journal API views."""

from unittest.mock import patch

from django.test import TestCase, tag
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import PosthumousJournalDisposition
from world.estates.factories import EstateSettlementFactory
from world.journals.constants import PosthumousOverride, ResponseType
from world.journals.factories import (
    JournalBequestGrantFactory,
    JournalEntryFactory,
    JournalTagFactory,
)
from world.roster.factories import PlayerDataFactory, RosterTenureFactory
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
