"""Service functions for the journal system."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from evennia.accounts.models import AccountDB

from world.achievements.models import StatDefinition
from world.achievements.services import increment_stat
from world.character_sheets.types import PosthumousJournalDisposition
from world.journals.constants import (
    JOURNAL_POST_XP,
    PRAISE_GIVEN_XP,
    PRAISE_RECEIVED_XP,
    RETORT_GIVEN_XP,
    RETORT_RECEIVED_XP,
    PosthumousOverride,
    ResponseType,
)
from world.journals.models import JournalBequestGrant, JournalEntry, JournalTag, WeeklyJournalXP
from world.journals.types import JournalError
from world.progression.services.awards import award_xp

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from evennia_extensions.models import PlayerData
    from world.character_sheets.models import CharacterSheet
    from world.estates.models import EstateSettlement


def player_for_sheet(sheet: CharacterSheet) -> PlayerData | None:
    """The PlayerData currently playing this character sheet, or None (#2996).

    Mirrors ``world.scenes.block_services._sheet_player``'s walk (this app's own copy — no
    cross-app dependency on ``world.scenes`` for the resolution itself); reused by
    ``world.journals.views`` for the mute-filtered author's-view read path, so this one stays
    unprefixed rather than following the private-per-module convention the block/mute service
    pair uses for their own persona-keyed sibling.
    """
    from django.core.exceptions import ObjectDoesNotExist

    try:
        roster_entry = sheet.roster_entry
    except ObjectDoesNotExist:
        return None
    if roster_entry is None:
        return None
    current = roster_entry.current_tenure
    return current.player_data if current is not None else None


def exclude_blocked_and_muted_authors(
    queryset: QuerySet[JournalEntry], *, viewer_account: Any
) -> QuerySet[JournalEntry]:
    """Exclude blocked/muted authors' entries from a journal feed queryset (#2996 Decision 2).

    ``viewer_account`` is typed loosely (mirrors ``block_services.hidden_persona_ids_for_viewer``)
    because DRF's ``request.user`` is ``AbstractBaseUser | AnonymousUser``, not this project's
    ``AccountDB`` — the ``is_authenticated``/``player_data`` duck-typing below works for either.

    An account-level Block hides journals **both directions** — mirrors
    ``block_services.blocked_player_ids_for``'s symmetric contract (partner ids regardless of
    who blocked whom), so calling this for either side of a block excludes the other's entries.
    An account-level Mute is **one-way**: ``mute_services.muted_player_ids_for`` only returns
    targets *this* viewer muted, so it only ever narrows the muter's own feed.

    Batched (the Task 1/2 idiom), not per-row: one ``.exclude()`` against the author's *current*
    player via the roster-tenure walk (mirrors ``block_services.hidden_persona_ids_for_viewer``'s
    account-level branch). Fail-open — no filtering — for an anonymous viewer or one with no
    ``PlayerData`` yet, matching every other #2996 seam's policy.
    """
    if viewer_account is None or not viewer_account.is_authenticated:
        return queryset
    try:
        viewer_player = viewer_account.player_data
    except AttributeError:
        return queryset

    from world.scenes.block_services import blocked_player_ids_for
    from world.scenes.mute_services import muted_player_ids_for

    excluded_ids = blocked_player_ids_for(viewer_player) | muted_player_ids_for(
        viewer_player=viewer_player
    )
    if not excluded_ids:
        return queryset
    return queryset.exclude(
        author__roster_entry__tenures__player_data_id__in=excluded_ids,
        author__roster_entry__tenures__end_date__isnull=True,
    )


def _get_or_reset_weekly_tracker(
    character_sheet: CharacterSheet,
) -> WeeklyJournalXP:
    """Get weekly XP tracker, resetting if the game week has changed."""
    from world.game_clock.week_services import get_current_game_week

    current_week = get_current_game_week()
    tracker, created = WeeklyJournalXP.objects.select_for_update().get_or_create(
        character_sheet=character_sheet,
        defaults={"game_week": current_week},
    )
    if not created and tracker.needs_reset(current_week):
        tracker.reset_week(current_week)
    return tracker


def _emit_stats(character_sheet: CharacterSheet, *stat_keys: str) -> None:
    """Increment achievement stats by key, skipping any that don't exist yet."""
    stats = StatDefinition.objects.filter(key__in=stat_keys)
    for stat in stats:
        increment_stat(character_sheet, stat)


def create_journal_entry(  # noqa: PLR0913 - explicit content/visibility/tag/override kwargs
    *,
    author: CharacterSheet,
    title: str,
    body: str,
    is_public: bool,
    tags: list[str] | None = None,
    posthumous_override: str = PosthumousOverride.INHERIT,
) -> JournalEntry:
    """
    Create a journal entry and award weekly XP.

    Args:
        author: The character writing the entry.
        title: Entry title.
        body: Entry body text.
        is_public: Whether the entry is publicly visible.
        tags: Optional list of tag names to attach.
        posthumous_override: Per-entry disposition override (#3287); INHERIT by default.

    Returns:
        The created JournalEntry.
    """
    with transaction.atomic():
        entry = JournalEntry.objects.create(
            author=author,
            title=title,
            body=body,
            is_public=is_public,
            posthumous_override=posthumous_override,
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

    # #2996 Decision 2 — an account-level block between the responder and the parent's author
    # rejects the response with the shared neutral UNAVAILABLE message (never names blocking;
    # "closed to you" already has many innocent causes here). Fail-open when either side has no
    # current player (can't prove a block, so don't manufacture one).
    from world.scenes.block_services import account_block_active

    author_player = player_for_sheet(author)
    parent_author_player = player_for_sheet(parent.author)
    if (
        author_player is not None
        and parent_author_player is not None
        and account_block_active(player_a=author_player, player_b=parent_author_player)
    ):
        raise JournalError(JournalError.UNAVAILABLE)

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
    posthumous_override: str | None = None,
) -> JournalEntry:
    """
    Edit an existing journal entry. Sets edited_at timestamp for title/body edits.

    ``posthumous_override`` (#3287) is metadata, not editorial content — changing it alone
    does not stamp ``edited_at``.

    Raises:
        ValueError: If the entry is a response (praise/retort).
    """
    if entry.response_type:
        raise JournalError(JournalError.EDIT_RESPONSE)

    update_fields: list[str] = []
    if title is not None:
        entry.title = title
        update_fields.append("title")
    if body is not None:
        entry.body = body
        update_fields.append("body")
    if title is not None or body is not None:
        entry.edited_at = timezone.now()
        update_fields.append("edited_at")
    if posthumous_override is not None:
        entry.posthumous_override = posthumous_override
        update_fields.append("posthumous_override")
    if update_fields:
        entry.save(update_fields=update_fields)
    return entry


def set_sheet_posthumous_disposition(*, sheet: CharacterSheet, disposition: str) -> CharacterSheet:
    """Set a character's sheet-level default posthumous journal disposition (#3287)."""
    sheet.posthumous_journal_disposition = disposition
    sheet.save(update_fields=["posthumous_journal_disposition"])
    return sheet


def reveal_journals_for_settlement(sheet: CharacterSheet, settlement: EstateSettlement) -> int:
    """Stamp ``revealed_at``/``revealed_by_settlement`` on the sheet's REVEAL-effective
    private entries (#3287 Decision 2). Called from ``estates.services.execute_settlement`` —
    the shipped, timer-backed death pipeline — never from any other path.

    - Never mutates ``is_public``; authorship history stays true.
    - Idempotent: only entries with ``revealed_at__isnull=True`` are considered, so a re-run
      never re-stamps (settlement itself is already first-door-wins idempotent, but this
      guard is cheap insurance).
    - SEAL-effective entries are excluded entirely, never touched.

    Returns the number of entries revealed.
    """
    candidates = JournalEntry.objects.filter(
        author=sheet, is_public=False, revealed_at__isnull=True
    ).select_related("author")
    now = timezone.now()
    revealed_count = 0
    for entry in candidates:
        if entry.effective_posthumous_disposition() != PosthumousOverride.REVEAL:
            continue
        entry.revealed_at = now
        entry.revealed_by_settlement = settlement
        entry.save(update_fields=["revealed_at", "revealed_by_settlement"])
        revealed_count += 1
    return revealed_count


def grant_journal_bequest(
    *,
    recipient_sheet: CharacterSheet,
    deceased_sheet: CharacterSheet,
    settlement: EstateSettlement,
) -> JournalBequestGrant:
    """Grant read access to a deceased sheet's non-sealed private entries (#3287 Decision 3).

    Called from ``estates.services.execute_settlement`` when the deceased's will carries a
    ``BequestKind.WRITINGS`` line. Idempotent per (recipient, deceased) pair via
    ``get_or_create`` backed by the model's unique constraint — a settlement re-run never
    mints a duplicate (first-door-wins already guards against that at the caller too).
    """
    grant, _created = JournalBequestGrant.objects.get_or_create(
        recipient_sheet=recipient_sheet,
        deceased_sheet=deceased_sheet,
        defaults={"created_by_settlement": settlement},
    )
    return grant


def sealed_effective_q() -> Q:
    """A ``Q`` matching ``JournalEntry`` rows whose EFFECTIVE posthumous disposition is SEAL.

    SEAL always wins (#3287 Decision 3) — used to exclude sealed entries from a bequest
    recipient's read of a deceased's corpus, regardless of the sheet-level default.
    """
    return Q(posthumous_override=PosthumousOverride.SEAL) | Q(
        posthumous_override=PosthumousOverride.INHERIT,
        author__posthumous_journal_disposition=PosthumousJournalDisposition.SEAL,
    )


def has_journal_bequest_grant(*, recipient_sheet: CharacterSheet, deceased_sheet_id: int) -> bool:
    """Whether ``recipient_sheet`` holds a bequest grant over ``deceased_sheet_id``'s writings."""
    return JournalBequestGrant.objects.filter(
        recipient_sheet=recipient_sheet, deceased_sheet_id=deceased_sheet_id
    ).exists()


def entry_visible_via_bequest(entry: JournalEntry, viewer_sheet: CharacterSheet | None) -> bool:
    """Whether ``viewer_sheet`` may read ``entry`` under a bequest grant (retrieve path).

    SEAL beats a grant — checked first so a sealed entry never needs the grant query.
    """
    if viewer_sheet is None:
        return False
    if entry.effective_posthumous_disposition() == PosthumousOverride.SEAL:
        return False
    return has_journal_bequest_grant(
        recipient_sheet=viewer_sheet, deceased_sheet_id=entry.author_id
    )


def base_entries_queryset() -> QuerySet[JournalEntry]:
    """The annotated/prefetched base queryset every list-style journal read builds on.

    Extracted from ``JournalEntryViewSet._get_base_queryset`` (#3287) so
    ``JournalEntryFilter.filter_deceased`` gets the same tag prefetch + response_count
    annotation the serializer needs, without ``world.journals.filters`` importing
    ``world.journals.views`` (would create a filters.py <-> views.py import cycle).
    """
    return (
        JournalEntry.objects.select_related("author__character")
        .prefetch_related(
            Prefetch("tags", queryset=JournalTag.objects.all(), to_attr="cached_tags"),
        )
        .annotate(response_count=Count("responses"))
        .order_by("-created_at")
        .distinct()
    )


def viewer_sheet_for_request(request: Any) -> CharacterSheet | None:
    """Resolve the requesting account's active CharacterSheet from the X-Character-ID header.

    A small, request-only duplicate of ``web.api.mixins.CharacterContextMixin._get_character``
    + ``JournalEntryViewSet._get_character_sheet`` — needed because
    ``JournalEntryFilter.filter_deceased`` (the FilterSet gating the ``?deceased=``
    bequest-corpus browse, per ``tools/lint_use_filterset.py``'s USE_FILTERSET rule) has
    ``self.request`` but no view instance to call the mixin method on. Mirrors this file's
    existing ``player_for_sheet`` precedent of an app owning its own small copy of a
    resolution walk rather than reaching into another app's private surface.
    """
    from world.character_sheets.models import CharacterSheet

    character_id = request.headers.get("X-Character-ID")
    if not character_id:
        return None
    try:
        character_id = int(character_id)
    except (ValueError, TypeError):
        return None

    available = request.user.get_available_characters()
    character = next((c for c in available if c.id == character_id), None)
    if character is None:
        return None
    try:
        return character.sheet_data
    except CharacterSheet.DoesNotExist:
        return None
