"""Tests for journal service functions."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.journals.constants import (
    JOURNAL_POST_XP,
    PRAISE_GIVEN_XP,
    PRAISE_RECEIVED_XP,
    RETORT_GIVEN_XP,
    RETORT_RECEIVED_XP,
    ResponseType,
)
from world.journals.models import JournalEntry, JournalTag, WeeklyJournalXP
from world.journals.services import (
    create_journal_entry,
    create_journal_response,
    edit_journal_entry,
)
from world.journals.types import JournalError


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class CreateJournalEntryTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.author = CharacterSheetFactory()
        cls.author.character.db_account = cls.account
        cls.author.character.save()

    def test_creates_entry(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        entry = create_journal_entry(
            author=self.author,
            title="My Journal",
            body="Some text",
            is_public=True,
        )
        self.assertEqual(entry.title, "My Journal")
        self.assertEqual(entry.body, "Some text")
        self.assertTrue(entry.is_public)
        self.assertEqual(entry.author, self.author)

    def test_first_post_awards_5_xp(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        create_journal_entry(
            author=self.author,
            title="First",
            body="Body",
            is_public=True,
        )
        mock_award.assert_called_once_with(
            account=self.account,
            amount=JOURNAL_POST_XP[0],
            description="Journal post: First",
        )

    def test_second_post_awards_2_xp(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        tracker, _ = WeeklyJournalXP.objects.get_or_create(character_sheet=self.author)
        tracker.posts_this_week = 1
        tracker.save()

        create_journal_entry(
            author=self.author,
            title="Second",
            body="Body",
            is_public=True,
        )
        mock_award.assert_called_once_with(
            account=self.account,
            amount=JOURNAL_POST_XP[1],
            description="Journal post: Second",
        )

    def test_third_post_awards_1_xp(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        tracker, _ = WeeklyJournalXP.objects.get_or_create(character_sheet=self.author)
        tracker.posts_this_week = 2
        tracker.save()

        create_journal_entry(
            author=self.author,
            title="Third",
            body="Body",
            is_public=True,
        )
        mock_award.assert_called_once_with(
            account=self.account,
            amount=JOURNAL_POST_XP[2],
            description="Journal post: Third",
        )

    def test_fourth_post_no_xp(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        tracker, _ = WeeklyJournalXP.objects.get_or_create(character_sheet=self.author)
        tracker.posts_this_week = 3
        tracker.save()

        create_journal_entry(
            author=self.author,
            title="Fourth",
            body="Body",
            is_public=True,
        )
        mock_award.assert_not_called()

    def test_private_entry_still_counts_toward_weekly_posts(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        create_journal_entry(
            author=self.author,
            title="Private",
            body="Body",
            is_public=False,
        )
        tracker = WeeklyJournalXP.objects.get(character_sheet=self.author)
        self.assertEqual(tracker.posts_this_week, 1)
        # Still awards XP for 1st post
        mock_award.assert_called_once()

    def test_tags_are_created(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        entry = create_journal_entry(
            author=self.author,
            title="Tagged",
            body="Body",
            is_public=True,
            tags=["adventure", "mystery"],
        )
        tag_names = set(JournalTag.objects.filter(entry=entry).values_list("name", flat=True))
        self.assertEqual(tag_names, {"adventure", "mystery"})

    @patch("world.journals.services.StatDefinition.objects")
    def test_emits_achievement_stats(
        self,
        mock_stat_qs: MagicMock,
        mock_award: MagicMock,  # noqa: ARG002
        mock_increment: MagicMock,
    ) -> None:
        """Creating a journal entry increments achievement stats."""
        mock_stat_obj = MagicMock()
        mock_stat_qs.filter.return_value = [mock_stat_obj]
        create_journal_entry(
            author=self.author,
            title="Achievement",
            body=".",
            is_public=True,
        )
        mock_increment.assert_called()

    def test_no_tags_when_none(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        entry = create_journal_entry(
            author=self.author,
            title="No Tags",
            body="Body",
            is_public=True,
        )
        self.assertEqual(JournalTag.objects.filter(entry=entry).count(), 0)


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class CreateJournalResponseTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.author_account = AccountFactory(username="journal_author")
        cls.responder_account = AccountFactory(username="journal_responder")
        cls.author = CharacterSheetFactory()
        cls.author.character.db_account = cls.author_account
        cls.author.character.save()
        cls.responder = CharacterSheetFactory()
        cls.responder.character.db_account = cls.responder_account
        cls.responder.character.save()

    def _make_public_entry(self) -> JournalEntry:
        return JournalEntry.objects.create(
            author=self.author,
            title="Public Entry",
            body="Body",
            is_public=True,
        )

    def test_praise_awards_xp_to_giver_and_receiver(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        parent = self._make_public_entry()
        create_journal_response(
            author=self.responder,
            parent=parent,
            response_type=ResponseType.PRAISE,
            title="Great!",
            body="Well done",
        )
        calls = mock_award.call_args_list
        giver_calls = [c for c in calls if c.kwargs.get("account") == self.responder_account]
        receiver_calls = [c for c in calls if c.kwargs.get("account") == self.author_account]
        self.assertEqual(len(giver_calls), 1)
        self.assertEqual(giver_calls[0].kwargs["amount"], PRAISE_GIVEN_XP)
        self.assertEqual(len(receiver_calls), 1)
        self.assertEqual(receiver_calls[0].kwargs["amount"], PRAISE_RECEIVED_XP)

    def test_retort_awards_xp_to_giver_and_receiver(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        parent = self._make_public_entry()
        create_journal_response(
            author=self.responder,
            parent=parent,
            response_type=ResponseType.RETORT,
            title="Nah",
            body="Disagree",
        )
        calls = mock_award.call_args_list
        giver_calls = [c for c in calls if c.kwargs.get("account") == self.responder_account]
        receiver_calls = [c for c in calls if c.kwargs.get("account") == self.author_account]
        self.assertEqual(len(giver_calls), 1)
        self.assertEqual(giver_calls[0].kwargs["amount"], RETORT_GIVEN_XP)
        self.assertEqual(len(receiver_calls), 1)
        self.assertEqual(receiver_calls[0].kwargs["amount"], RETORT_RECEIVED_XP)

    def test_second_praise_in_week_no_giver_xp(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        parent = self._make_public_entry()
        tracker, _ = WeeklyJournalXP.objects.get_or_create(character_sheet=self.responder)
        tracker.praised_this_week = True
        tracker.save()

        create_journal_response(
            author=self.responder,
            parent=parent,
            response_type=ResponseType.PRAISE,
            title="Another praise",
            body="Also good",
        )
        calls = mock_award.call_args_list
        giver_calls = [c for c in calls if c.kwargs.get("account") == self.responder_account]
        self.assertEqual(len(giver_calls), 0)

    def test_second_retort_in_week_no_giver_xp(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        parent = self._make_public_entry()
        tracker, _ = WeeklyJournalXP.objects.get_or_create(character_sheet=self.responder)
        tracker.retorted_this_week = True
        tracker.save()

        create_journal_response(
            author=self.responder,
            parent=parent,
            response_type=ResponseType.RETORT,
            title="Another retort",
            body="Still no",
        )
        calls = mock_award.call_args_list
        giver_calls = [c for c in calls if c.kwargs.get("account") == self.responder_account]
        self.assertEqual(len(giver_calls), 0)

    def test_cannot_respond_to_private_entry(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        private_entry = JournalEntry.objects.create(
            author=self.author,
            title="Private",
            body="Body",
            is_public=False,
        )
        with self.assertRaises(JournalError, msg="private"):
            create_journal_response(
                author=self.responder,
                parent=private_entry,
                response_type=ResponseType.PRAISE,
                title="Praise",
                body="Body",
            )

    def test_cannot_respond_to_own_entry(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        parent = self._make_public_entry()
        with self.assertRaises(JournalError, msg="own"):
            create_journal_response(
                author=self.author,
                parent=parent,
                response_type=ResponseType.PRAISE,
                title="Self praise",
                body="Body",
            )

    def test_responses_are_always_public(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        parent = self._make_public_entry()
        entry = create_journal_response(
            author=self.responder,
            parent=parent,
            response_type=ResponseType.PRAISE,
            title="Praise",
            body="Body",
        )
        self.assertTrue(entry.is_public)

    def test_response_links_to_parent(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        parent = self._make_public_entry()
        entry = create_journal_response(
            author=self.responder,
            parent=parent,
            response_type=ResponseType.RETORT,
            title="Retort",
            body="Body",
        )
        self.assertEqual(entry.parent, parent)
        self.assertEqual(entry.response_type, ResponseType.RETORT)

    @patch("world.journals.services.StatDefinition.objects")
    def test_praise_emits_response_stats(
        self,
        mock_stat_qs: MagicMock,
        mock_award: MagicMock,  # noqa: ARG002
        mock_increment: MagicMock,
    ) -> None:
        """Praising emits praises_given and praises_received stats."""
        mock_stat_obj = MagicMock()
        mock_stat_qs.filter.return_value = [mock_stat_obj]
        parent = self._make_public_entry()
        create_journal_response(
            author=self.responder,
            parent=parent,
            response_type=ResponseType.PRAISE,
            title="Nice!",
            body="Good.",
        )
        mock_increment.assert_called()

    @patch("world.journals.services.StatDefinition.objects")
    def test_retort_emits_response_stats(
        self,
        mock_stat_qs: MagicMock,
        mock_award: MagicMock,  # noqa: ARG002
        mock_increment: MagicMock,
    ) -> None:
        """Retorting emits retorts_given and retorts_received stats."""
        mock_stat_obj = MagicMock()
        mock_stat_qs.filter.return_value = [mock_stat_obj]
        parent = self._make_public_entry()
        create_journal_response(
            author=self.responder,
            parent=parent,
            response_type=ResponseType.RETORT,
            title="No!",
            body="Wrong.",
        )
        mock_increment.assert_called()


class EditJournalEntryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_edit_title_and_body(self) -> None:
        entry = JournalEntry.objects.create(
            author=self.sheet,
            title="Original",
            body="Old.",
            is_public=True,
        )
        updated = edit_journal_entry(entry=entry, title="Updated", body="New.")
        self.assertEqual(updated.title, "Updated")
        self.assertEqual(updated.body, "New.")
        self.assertIsNotNone(updated.edited_at)

    def test_edit_sets_edited_at(self) -> None:
        entry = JournalEntry.objects.create(
            author=self.sheet,
            title="Original",
            body="Content.",
            is_public=True,
        )
        self.assertIsNone(entry.edited_at)
        updated = edit_journal_entry(entry=entry, body="Changed.")
        self.assertIsNotNone(updated.edited_at)

    def test_cannot_edit_response_entry(self) -> None:
        parent = JournalEntry.objects.create(
            author=self.sheet,
            title="Parent",
            body=".",
            is_public=True,
        )
        other = CharacterSheetFactory()
        response = JournalEntry.objects.create(
            author=other,
            title="Praise",
            body="Nice.",
            is_public=True,
            parent=parent,
            response_type=ResponseType.PRAISE,
        )
        with self.assertRaises(JournalError):
            edit_journal_entry(entry=response, body="Changed.")
