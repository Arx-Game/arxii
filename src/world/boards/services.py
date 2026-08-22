"""Service layer for the boards system (#3286).

Permission logic lives here, not in the Actions/viewsets that call it —
mirrors the ``world.covenants`` shape (``CovenantError`` raised, callers map
it to a user-facing failure). Post rights:

- **LOCATION board**: any character physically present in the board's room
  may post; the author must also be present to remove their own post
  (spec Decision 3 — presence is required for post AND remove-own, but NOT
  for editing your own post remotely).
- **ORG board**: a member whose rank grants ``can_post_to_board`` may post;
  any active member may read; removal of another member's post requires
  ``can_moderate_board`` (or staff); the author may always remove their own.

Soft-delete only (``removed_by_persona``/``removed_at``) — never hard-delete.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.boards.models import Board, BoardPost
from world.boards.types import BoardError

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from evennia_extensions.models import RoomProfile
    from world.scenes.models import Persona
    from world.societies.models import Organization


def get_or_create_location_board(room_profile: RoomProfile) -> Board:
    """Get or create the LOCATION board anchored to this room (#3286).

    Called both from the NOTICE_BOARD room-feature install strategy
    (``world.room_features.services.handle_notice_board_progression``) and
    lazily at first post to a NOTICE_BOARD room, so either path is idempotent.
    """
    board, _ = Board.objects.get_or_create(
        room_profile=room_profile,
        defaults={"name": "Notice Board"},
    )
    return board


def get_or_create_org_board(organization: Organization) -> Board:
    """Get or create the ORG board anchored to this organization (#3286)."""
    board, _ = Board.objects.get_or_create(
        organization=organization,
        defaults={"name": f"{organization.name} Board"},
    )
    return board


def _active_org_membership(persona: Persona, organization: Organization):
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return (
        OrganizationMembership.objects.filter(
            persona=persona,
            organization=organization,
            left_at__isnull=True,
            exiled_at__isnull=True,
        )
        .select_related("rank")
        .first()
    )


def _persona_present_in_room(persona: Persona, room_profile: RoomProfile) -> bool:
    """Whether ``persona``'s character currently stands in ``room_profile``'s room.

    RoomProfile shares ObjectDB's pk (#2608), so the room's own pk is the
    profile id — no join needed beyond the character's location.
    """
    character = persona.character_sheet.character
    location = character.location if character is not None else None
    return location is not None and location.pk == room_profile.pk


def can_post_to_board(
    persona: Persona, board: Board, *, actor_room_profile: RoomProfile | None
) -> bool:
    """Whether ``persona`` may post a new notice to ``board`` right now."""
    if board.is_location_board:
        return (
            actor_room_profile is not None
            and actor_room_profile.pk == board.room_profile_id
            and _persona_present_in_room(persona, board.room_profile)
        )
    membership = _active_org_membership(persona, board.organization)
    return (
        membership is not None and membership.rank is not None and membership.rank.can_post_to_board
    )


def can_moderate_board(persona: Persona, board: Board, *, is_staff: bool = False) -> bool:
    """Whether ``persona`` may remove ANY post on ``board`` (not just their own)."""
    if is_staff:
        return True
    if board.is_location_board:
        return False
    membership = _active_org_membership(persona, board.organization)
    return (
        membership is not None
        and membership.rank is not None
        and membership.rank.can_moderate_board
    )


@transaction.atomic
def create_board_post(
    *,
    board: Board,
    author_persona: Persona,
    title: str,
    body: str,
    actor_room_profile: RoomProfile | None = None,
) -> BoardPost:
    """Pin a new notice to ``board`` as ``author_persona`` (#3286).

    Raises ``BoardError`` when the persona lacks posting rights.
    """
    if not can_post_to_board(author_persona, board, actor_room_profile=actor_room_profile):
        if board.is_location_board:
            raise BoardError(BoardError.NOT_PRESENT)
        raise BoardError(BoardError.NOT_AUTHORIZED_TO_POST)
    return BoardPost.objects.create(
        board=board,
        author_persona=author_persona,
        title=title,
        body=body,
    )


@transaction.atomic
def edit_board_post(
    *,
    post: BoardPost,
    editor_persona: Persona,
    title: str,
    body: str,
) -> BoardPost:
    """Edit a notice's title/body — author-only, regardless of board kind (#3286).

    Raises ``BoardError`` when the editor isn't the author or the post was
    already removed.
    """
    if post.is_removed:
        raise BoardError(BoardError.ALREADY_REMOVED)
    if post.author_persona_id != editor_persona.pk:
        raise BoardError(BoardError.NOT_AUTHOR)
    post.title = title
    post.body = body
    post.edited_at = timezone.now()
    post.save(update_fields=["title", "body", "edited_at"])
    return post


@transaction.atomic
def remove_board_post(
    *,
    post: BoardPost,
    remover_persona: Persona,
    actor_room_profile: RoomProfile | None = None,
    is_staff: bool = False,
) -> BoardPost:
    """Soft-delete a notice: stamp ``removed_by_persona``/``removed_at`` (#3286).

    Author removes own (LOCATION boards require the author be present in the
    room, same as posting); ``can_moderate_board`` or staff removes any post
    on an ORG board; staff can always remove any post.
    """
    if post.is_removed:
        raise BoardError(BoardError.ALREADY_REMOVED)

    board = post.board
    is_author = post.author_persona_id == remover_persona.pk

    if is_staff:
        pass
    elif is_author:
        if board.is_location_board and not (
            actor_room_profile is not None
            and actor_room_profile.pk == board.room_profile_id
            and _persona_present_in_room(remover_persona, board.room_profile)
        ):
            raise BoardError(BoardError.NOT_PRESENT)
    elif not can_moderate_board(remover_persona, board, is_staff=is_staff):
        raise BoardError(BoardError.NOT_AUTHORIZED_TO_REMOVE)

    post.removed_by_persona = remover_persona
    post.removed_at = timezone.now()
    post.save(update_fields=["removed_by_persona", "removed_at"])
    return post


def visible_posts_for_board(board: Board) -> QuerySet[BoardPost]:
    """Active posts on ``board``, newest-first, capped to ``max_active_posts``.

    Older posts fall off the display but stay in the DB (no auto-expiry at
    MVP, per spec Decision 5). Callers apply block/mute exclusion on top via
    ``exclude_blocked_and_muted_board_authors``.
    """
    pks = list(
        board.posts.active()
        .order_by("-created_at")
        .values_list("pk", flat=True)[: board.max_active_posts]
    )
    return (
        BoardPost.objects.filter(pk__in=pks)
        .select_related("author_persona")
        .order_by("-created_at")
    )


def exclude_blocked_and_muted_board_authors(
    queryset: QuerySet[BoardPost], *, viewer_account
) -> QuerySet[BoardPost]:
    """Exclude blocked/muted authors' posts from a board read (mirrors journals #2996).

    Batched, fail-open for an anonymous viewer or one with no ``PlayerData``
    yet — same policy as ``world.journals.services.exclude_blocked_and_muted_authors``.
    """
    if viewer_account is None or not viewer_account.is_authenticated:
        return queryset
    try:
        viewer_player = viewer_account.player_data
    except AttributeError:
        return queryset

    from world.scenes.block_services import blocked_player_ids_for  # noqa: PLC0415
    from world.scenes.mute_services import muted_player_ids_for  # noqa: PLC0415

    excluded_ids = blocked_player_ids_for(viewer_player) | muted_player_ids_for(
        viewer_player=viewer_player
    )
    if not excluded_ids:
        return queryset
    return queryset.exclude(
        author_persona__character_sheet__roster_entry__tenures__player_data_id__in=excluded_ids,
        author_persona__character_sheet__roster_entry__tenures__end_date__isnull=True,
    )
