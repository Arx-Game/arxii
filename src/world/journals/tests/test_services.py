"""Tests for journal service functions."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import RetortConsent
from world.game_clock.factories import GameClockFactory
from world.journals.constants import (
    CONDEMN_GIVEN_XP,
    CONDEMN_RECEIVED_XP,
    JOURNAL_POST_XP,
    PRAISE_GIVEN_XP,
    PRAISE_RECEIVED_XP,
    RETORT_GIVEN_XP,
    RETORT_RECEIVED_XP,
    JournalKind,
    ResponseType,
)
from world.journals.factories import JournalEntryFactory
from world.journals.models import JournalEntry, JournalTag, WeeklyJournalXP
from world.journals.services import (
    can_retort,
    create_journal_entry,
    create_journal_response,
    edit_journal_entry,
    journal_settings,
    mark_journals_visited,
    set_retort_consent,
    visible_entries_q,
)
from world.journals.types import JournalError
from world.relationships.constants import TrackSign
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.roster.factories import PlayerDataFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.scenes.models import Block, Mute


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class CreateJournalEntryTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.game_clock.week_services import get_current_game_week

        cls.current_week = get_current_game_week()
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
            # The author's sheet is credited with the earn (#3748) — the account holds
            # the balance, the character holds the record of having earned it.
            character=self.author,
        )

    def test_second_post_awards_2_xp(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        tracker, _ = WeeklyJournalXP.objects.get_or_create(
            character_sheet=self.author, defaults={"game_week": self.current_week}
        )
        tracker.posts_this_week = 1
        tracker.game_week = self.current_week
        tracker.save(update_fields=["posts_this_week", "game_week"])

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
            # The author's sheet is credited with the earn (#3748) — the account holds
            # the balance, the character holds the record of having earned it.
            character=self.author,
        )

    def test_third_post_awards_1_xp(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        tracker, _ = WeeklyJournalXP.objects.get_or_create(
            character_sheet=self.author, defaults={"game_week": self.current_week}
        )
        tracker.posts_this_week = 2
        tracker.game_week = self.current_week
        tracker.save(update_fields=["posts_this_week", "game_week"])

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
            # The author's sheet is credited with the earn (#3748) — the account holds
            # the balance, the character holds the record of having earned it.
            character=self.author,
        )

    def test_fourth_post_no_xp(
        self,
        mock_award,
        mock_stat,  # noqa: ARG002
    ) -> None:
        tracker, _ = WeeklyJournalXP.objects.get_or_create(
            character_sheet=self.author, defaults={"game_week": self.current_week}
        )
        tracker.posts_this_week = 3
        tracker.game_week = self.current_week
        tracker.save(update_fields=["posts_this_week", "game_week"])

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

    def test_create_journal_entry_updates_introductions_cache(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        """A non-ENTRY kind is appended into an already-warm ``introductions`` cache
        directly, with no re-query (#3816: PrunedCachedProperty write-site mutation)."""
        _ = self.author.introductions  # warm the cache
        entry = create_journal_entry(
            author=self.author,
            title="First Journal",
            body="Body",
            is_public=True,
            kind=JournalKind.FIRST_JOURNAL,
        )
        with self.assertNumQueries(0):
            introductions = self.author.introductions
        self.assertEqual(introductions, [entry])

    def test_create_journal_entry_does_not_warm_a_cold_introductions_cache(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        """No cache warmed yet: the write site must not read (and thus load) it."""
        entry = create_journal_entry(
            author=self.author,
            title="First Journal",
            body="Body",
            is_public=True,
            kind=JournalKind.FIRST_JOURNAL,
        )
        self.assertNotIn("introductions", self.author.__dict__)
        self.assertEqual(self.author.introductions, [entry])


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class JournalXPOptOutTests(TestCase):
    """#3466: an honoring journal (Rite of Honors) is not the author's own weekly post."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.sheet = CharacterSheetFactory()
        cls.sheet.character.db_account = cls.account
        cls.sheet.character.save()

    def test_award_weekly_xp_false_writes_no_tracker(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        create_journal_entry(
            author=self.sheet, title="t", body="b", is_public=True, award_weekly_xp=False
        )
        assert not WeeklyJournalXP.objects.filter(character_sheet=self.sheet).exists()

    def test_default_still_awards(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        create_journal_entry(author=self.sheet, title="t", body="b", is_public=True)
        assert WeeklyJournalXP.objects.filter(character_sheet=self.sheet).exists()


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class CreateJournalResponseTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.game_clock.week_services import get_current_game_week

        cls.current_week = get_current_game_week()
        cls.author_account = AccountFactory(username="journal_author")
        cls.responder_account = AccountFactory(username="journal_responder")
        cls.author = CharacterSheetFactory()
        cls.author.character.db_account = cls.author_account
        cls.author.character.save()
        cls.responder = CharacterSheetFactory()
        cls.responder.character.db_account = cls.responder_account
        cls.responder.character.save()
        # ADR-0307 (#3941): Retort/Condemn are consent-gated. This class predates the
        # gate and exercises the XP/stat plumbing, not the gate itself — open the door
        # so its existing retort tests keep testing what they always tested.
        cls.author.retort_consent = RetortConsent.ANYONE
        cls.author.save(update_fields=["retort_consent"])

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
        tracker, _ = WeeklyJournalXP.objects.get_or_create(
            character_sheet=self.responder, defaults={"game_week": self.current_week}
        )
        tracker.praised_this_week = True
        tracker.game_week = self.current_week
        tracker.save(update_fields=["praised_this_week", "game_week"])

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
        tracker, _ = WeeklyJournalXP.objects.get_or_create(
            character_sheet=self.responder, defaults={"game_week": self.current_week}
        )
        tracker.retorted_this_week = True
        tracker.game_week = self.current_week
        tracker.save(update_fields=["retorted_this_week", "game_week"])

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


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class JournalResponseBlockMuteTest(TestCase):
    """#2996 Decision 2 — account block/mute at the journal-reaction seam.

    Block is the documented exception to write-then-filter here: a rejection at
    ``create_journal_response`` can't leak because "this entry isn't available to respond to"
    already has many innocent causes (private, deleted, moderation, ...). Mute is the ordinary
    write-then-filter shape — the response persists; the view layer excludes it from the
    entry author's own read (covered separately in ``test_views.py``).
    """

    @classmethod
    def setUpTestData(cls) -> None:
        author_tenure = RosterTenureFactory(player_data=PlayerDataFactory())
        cls.author = author_tenure.roster_entry.character_sheet
        cls.author_player = author_tenure.player_data
        responder_tenure = RosterTenureFactory(player_data=PlayerDataFactory())
        cls.responder = responder_tenure.roster_entry.character_sheet
        cls.responder_player = responder_tenure.player_data

    def _make_public_entry(self) -> JournalEntry:
        return JournalEntry.objects.create(
            author=self.author,
            title="Public Entry",
            body="Body",
            is_public=True,
        )

    def test_block_rejects_with_neutral_message_and_writes_nothing(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        Block.objects.create(
            owner=self.author_player,
            blocked_player=self.responder_player,
            account_level=True,
        )
        parent = self._make_public_entry()

        with self.assertRaises(JournalError) as ctx:
            create_journal_response(
                author=self.responder,
                parent=parent,
                response_type=ResponseType.PRAISE,
                title="Well done!",
                body="Body",
            )

        self.assertEqual(ctx.exception.user_message, JournalError.UNAVAILABLE)
        self.assertNotIn("block", ctx.exception.user_message.lower())
        self.assertFalse(JournalEntry.objects.filter(title="Well done!").exists())

    def test_block_is_symmetric(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        """The block owner doesn't matter -- either direction rejects the response."""
        Block.objects.create(
            owner=self.responder_player,
            blocked_player=self.author_player,
            account_level=True,
        )
        parent = self._make_public_entry()

        with self.assertRaises(JournalError):
            create_journal_response(
                author=self.responder,
                parent=parent,
                response_type=ResponseType.PRAISE,
                title="Well done!",
                body="Body",
            )

    def test_no_block_allows_response(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        parent = self._make_public_entry()
        response = create_journal_response(
            author=self.responder,
            parent=parent,
            response_type=ResponseType.PRAISE,
            title="Well done!",
            body="Body",
        )
        self.assertTrue(JournalEntry.objects.filter(pk=response.pk).exists())

    def test_mute_does_not_block_the_write(
        self,
        mock_award,  # noqa: ARG002
        mock_stat,  # noqa: ARG002
    ) -> None:
        """Mute is a read-side filter only -- the write always persists normally (#2996)."""
        Mute.objects.create(
            owner=self.author_player,
            muted_persona=PersonaFactory(),
            muted_player=self.responder_player,
            account_level=True,
        )
        parent = self._make_public_entry()
        response = create_journal_response(
            author=self.responder,
            parent=parent,
            response_type=ResponseType.PRAISE,
            title="Well done!",
            body="Body",
        )
        self.assertTrue(JournalEntry.objects.filter(pk=response.pk).exists())


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


def _with_account(sheet):
    sheet.character.db_account = AccountFactory()
    sheet.character.save()
    return sheet


class VisibleEntriesQTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer = CharacterSheetFactory()
        cls.reader = CharacterSheetFactory()
        cls.white = JournalEntryFactory(author=cls.writer, is_public=True)
        cls.black = JournalEntryFactory(author=cls.writer, is_public=False)
        cls.revealed = JournalEntryFactory(
            author=cls.writer, is_public=False, revealed_at=timezone.now()
        )

    def _ids(self, viewer, is_staff=False):
        q = visible_entries_q(viewer_sheet=viewer, is_staff=is_staff)
        return set(JournalEntry.objects.filter(q).values_list("id", flat=True))

    def test_stranger_sees_white_and_revealed(self) -> None:
        self.assertEqual(self._ids(self.reader), {self.white.id, self.revealed.id})

    def test_author_sees_own_black(self) -> None:
        self.assertEqual(self._ids(self.writer), {self.white.id, self.black.id, self.revealed.id})

    def test_staff_sees_everything(self) -> None:
        self.assertEqual(
            self._ids(self.reader, is_staff=True),
            {self.white.id, self.black.id, self.revealed.id},
        )

    def test_no_character_sees_white_and_revealed(self) -> None:
        self.assertEqual(self._ids(None), {self.white.id, self.revealed.id})


class CanRetortTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer = CharacterSheetFactory()
        cls.viewer = CharacterSheetFactory()
        cls.negative = RelationshipTrackFactory(name="Rivalry", sign=TrackSign.NEGATIVE)
        cls.positive = RelationshipTrackFactory(name="Friendship", sign=TrackSign.POSITIVE)

    def test_default_consent_and_no_relationship_is_closed(self) -> None:
        self.assertFalse(can_retort(viewer_sheet=self.viewer, author=self.writer))

    def test_anyone_consent_opens_it(self) -> None:
        self.writer.retort_consent = RetortConsent.ANYONE
        self.writer.save(update_fields=["retort_consent"])
        self.assertTrue(can_retort(viewer_sheet=self.viewer, author=self.writer))

    def test_negative_track_either_direction_opens_it(self) -> None:
        rel = CharacterRelationshipFactory(
            source=self.writer, target=self.viewer, is_pending=False, is_active=True
        )
        RelationshipTrackProgressFactory(relationship=rel, track=self.negative)
        self.assertTrue(can_retort(viewer_sheet=self.viewer, author=self.writer))

    def test_positive_track_does_not(self) -> None:
        rel = CharacterRelationshipFactory(
            source=self.viewer, target=self.writer, is_pending=False, is_active=True
        )
        RelationshipTrackProgressFactory(relationship=rel, track=self.positive)
        self.assertFalse(can_retort(viewer_sheet=self.viewer, author=self.writer))

    def test_pending_relationship_does_not(self) -> None:
        rel = CharacterRelationshipFactory(
            source=self.viewer, target=self.writer, is_pending=True, is_active=True
        )
        RelationshipTrackProgressFactory(relationship=rel, track=self.negative)
        self.assertFalse(can_retort(viewer_sheet=self.viewer, author=self.writer))

    def test_no_viewer_is_closed(self) -> None:
        self.assertFalse(can_retort(viewer_sheet=None, author=self.writer))


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class CondemnAndConsentGateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.writer = _with_account(CharacterSheetFactory())
        cls.responder = _with_account(CharacterSheetFactory())
        cls.entry = JournalEntryFactory(author=cls.writer, is_public=True)

    def test_retort_refused_without_consent(self, mock_award, mock_stat) -> None:  # noqa: ARG002
        with self.assertRaises(JournalError) as ctx:
            create_journal_response(
                author=self.responder,
                parent=self.entry,
                response_type=ResponseType.RETORT,
                title="t",
                body="b",
            )
        self.assertEqual(ctx.exception.user_message, JournalError.UNAVAILABLE)

    def test_condemn_awards_the_retort_schedule_when_open(self, mock_award, mock_stat) -> None:  # noqa: ARG002
        self.writer.retort_consent = RetortConsent.ANYONE
        self.writer.save(update_fields=["retort_consent"])
        response = create_journal_response(
            author=self.responder,
            parent=self.entry,
            response_type=ResponseType.CONDEMN,
            title="t",
            body="b",
        )
        self.assertEqual(response.response_type, ResponseType.CONDEMN)
        amounts = sorted(call.kwargs["amount"] for call in mock_award.call_args_list)
        self.assertEqual(amounts, sorted([CONDEMN_GIVEN_XP, CONDEMN_RECEIVED_XP]))

    def test_praise_is_never_gated(self, mock_award, mock_stat) -> None:  # noqa: ARG002
        response = create_journal_response(
            author=self.responder,
            parent=self.entry,
            response_type=ResponseType.PRAISE,
            title="t",
            body="b",
        )
        self.assertEqual(response.response_type, ResponseType.PRAISE)


@patch("world.journals.services.increment_stat")
@patch("world.journals.services.award_xp")
class AboutAndIcStampTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.author = _with_account(CharacterSheetFactory())
        cls.subject = CharacterSheetFactory()

    def test_about_is_stored_and_editable(self, mock_award, mock_stat) -> None:  # noqa: ARG002
        entry = create_journal_entry(
            author=self.author, title="t", body="b", is_public=True, about=self.subject
        )
        self.assertEqual(entry.about_id, self.subject.pk)
        edit_journal_entry(entry=entry, clear_about=True)
        entry.refresh_from_db()
        self.assertIsNone(entry.about_id)
        self.assertIsNone(entry.edited_at)  # about is metadata, not editorial content

    def test_ic_timestamp_stamped_from_the_clock(self, mock_award, mock_stat) -> None:  # noqa: ARG002
        GameClockFactory()
        entry = create_journal_entry(author=self.author, title="t", body="b", is_public=True)
        self.assertIsNotNone(entry.ic_timestamp)

    def test_ic_timestamp_null_without_a_clock(self, mock_award, mock_stat) -> None:  # noqa: ARG002
        entry = create_journal_entry(author=self.author, title="t", body="b", is_public=True)
        self.assertIsNone(entry.ic_timestamp)


class SettingsAndVisitTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_set_retort_consent(self) -> None:
        set_retort_consent(sheet=self.sheet, consent=RetortConsent.ANYONE)
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.retort_consent, RetortConsent.ANYONE)

    def test_invalid_consent_raises(self) -> None:
        with self.assertRaises(JournalError):
            set_retort_consent(sheet=self.sheet, consent="everyone")

    def test_mark_visited_and_settings(self) -> None:
        at = timezone.now() - timedelta(minutes=1)
        mark_journals_visited(sheet=self.sheet, at=at)
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.journals_visited_at, at)
        settings = journal_settings(sheet=self.sheet)
        self.assertEqual(settings.retort_consent, RetortConsent.RIVALS)
        self.assertEqual(settings.posts_this_week, 0)
        self.assertEqual(settings.rewarded_posts_per_week, 3)
