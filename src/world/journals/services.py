"""Service functions for the journal system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone
from evennia.accounts.models import AccountDB

from world.achievements.models import StatDefinition
from world.achievements.services import increment_stat
from world.journals.constants import (
    JOURNAL_POST_XP,
    PRAISE_GIVEN_XP,
    PRAISE_RECEIVED_XP,
    RETORT_GIVEN_XP,
    RETORT_RECEIVED_XP,
    ResponseType,
)
from world.journals.models import JournalEntry, JournalTag, WeeklyJournalXP
from world.journals.types import JournalError
from world.progression.services.awards import award_xp

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def _get_or_reset_weekly_tracker(
    character_sheet: CharacterSheet,
) -> WeeklyJournalXP:
    """Get weekly XP tracker, resetting if a week has passed."""
    tracker, _created = WeeklyJournalXP.objects.select_for_update().get_or_create(
        character_sheet=character_sheet,
    )
    if tracker.needs_reset():
        tracker.reset_week()
    return tracker


def _emit_stats(character_sheet: CharacterSheet, *stat_keys: str) -> None:
    """Increment achievement stats by key, skipping any that don't exist yet."""
    stats = StatDefinition.objects.filter(key__in=stat_keys)
    for stat in stats:
        increment_stat(character_sheet, stat)


def create_journal_entry(
    *,
    author: CharacterSheet,
    title: str,
    body: str,
    is_public: bool,
    tags: list[str] | None = None,
) -> JournalEntry:
    """
    Create a journal entry and award weekly XP.

    Args:
        author: The character writing the entry.
        title: Entry title.
        body: Entry body text.
        is_public: Whether the entry is publicly visible.
        tags: Optional list of tag names to attach.

    Returns:
        The created JournalEntry.
    """
    with transaction.atomic():
        entry = JournalEntry.objects.create(
            author=author,
            title=title,
            body=body,
            is_public=is_public,
        )

        if tags:
            JournalTag.objects.bulk_create(
                [JournalTag(entry=entry, name=tag.lower().strip()) for tag in tags]
            )

        tracker = _get_or_reset_weekly_tracker(author)
        tracker.posts_this_week += 1
        tracker.save(update_fields=["posts_this_week"])

        # Award XP based on post count this week (0-indexed)
        post_index = tracker.posts_this_week - 1
        if post_index < len(JOURNAL_POST_XP):
            xp_amount = JOURNAL_POST_XP[post_index]
            account = author.character.db_account
            award_xp(
                account=account,
                amount=xp_amount,
                description=f"Journal post: {title}",
            )

        stat_keys = ["journals.total_written"]
        if is_public:
            stat_keys.append("journals.total_public")
        _emit_stats(author, *stat_keys)

    return entry


def _award_response_xp(
    tracker: WeeklyJournalXP,
    flag_field: str,
    account: AccountDB,
    amount: int,
    description: str,
) -> None:
    """Award response XP if not already awarded this week."""
    if not getattr(tracker, flag_field):
        setattr(tracker, flag_field, True)
        tracker.save(update_fields=[flag_field])
        award_xp(account=account, amount=amount, description=description)


def create_journal_response(
    *,
    author: CharacterSheet,
    parent: JournalEntry,
    response_type: ResponseType,
    title: str,
    body: str,
) -> JournalEntry:
    """
    Create a praise or retort response to a journal entry.

    Responses are always public. Cannot respond to private entries
    or to your own entries.

    Args:
        author: The character writing the response.
        parent: The journal entry being responded to.
        response_type: One of ResponseType choices.
        title: Response title.
        body: Response body text.

    Returns:
        The created JournalEntry response.

    Raises:
        ValueError: If the parent is private or authored by the same
            character.
    """
    if not parent.is_public:
        raise JournalError(JournalError.PRIVATE_PARENT)

    if parent.author_id == author.pk:
        raise JournalError(JournalError.SELF_RESPONSE)

    with transaction.atomic():
        entry = JournalEntry.objects.create(
            author=author,
            title=title,
            body=body,
            is_public=True,
            parent=parent,
            response_type=response_type,
        )

        author_tracker = _get_or_reset_weekly_tracker(author)
        receiver_tracker = _get_or_reset_weekly_tracker(parent.author)

        author_account = author.character.db_account
        receiver_account = parent.author.character.db_account

        if response_type == ResponseType.PRAISE:
            _award_response_xp(
                author_tracker,
                "praised_this_week",
                author_account,
                PRAISE_GIVEN_XP,
                f"Praised: {parent.title}",
            )
            _award_response_xp(
                receiver_tracker,
                "was_praised_this_week",
                receiver_account,
                PRAISE_RECEIVED_XP,
                f"Received praise on: {parent.title}",
            )
            _emit_stats(author, "journals.praises_given")
            _emit_stats(parent.author, "journals.praises_received")
        else:
            _award_response_xp(
                author_tracker,
                "retorted_this_week",
                author_account,
                RETORT_GIVEN_XP,
                f"Retorted: {parent.title}",
            )
            _award_response_xp(
                receiver_tracker,
                "was_retorted_this_week",
                receiver_account,
                RETORT_RECEIVED_XP,
                f"Received retort on: {parent.title}",
            )
            _emit_stats(author, "journals.retorts_given")
            _emit_stats(parent.author, "journals.retorts_received")

    return entry


def edit_journal_entry(
    *,
    entry: JournalEntry,
    title: str | None = None,
    body: str | None = None,
) -> JournalEntry:
    """
    Edit an existing journal entry. Sets edited_at timestamp.

    Raises:
        ValueError: If the entry is a response (praise/retort).
    """
    if entry.response_type:
        raise JournalError(JournalError.EDIT_RESPONSE)

    if title is not None:
        entry.title = title
    if body is not None:
        entry.body = body
    entry.edited_at = timezone.now()
    update_fields = ["edited_at"]
    if title is not None:
        update_fields.append("title")
    if body is not None:
        update_fields.append("body")
    entry.save(update_fields=update_fields)
    return entry
