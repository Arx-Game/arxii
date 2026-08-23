"""Models for the boards system (#3286).

``Board`` is anchored to EITHER a ``RoomProfile`` (LOCATION board — the
Notice Board room feature's write surface) OR an ``Organization`` (ORG
board) — never both, never neither (enforced by a DB check constraint, no
JSON, ADR-0007). ``BoardPost`` rows are soft-deleted only (``removed_by_persona``
/ ``removed_at``) — moderation is auditable, never a hard-delete of story data.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.boards.constants import DEFAULT_MAX_ACTIVE_POSTS

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
ROOM_PROFILE_MODEL = "arxii.RoomProfile"
ORGANIZATION_MODEL = "arxii.Organization"
PERSONA_MODEL = "arxii.Persona"


class Board(SharedMemoryModel):
    """A persistent bulletin board — either a room's notice board or an org board.

    Exactly one of ``room_profile``/``organization`` is set (DB check
    constraint). Each anchor holds at most one board (unique constraint on the
    non-null side) — mirrors ``RoomFeatureInstance``'s one-per-room shape.
    """

    room_profile = models.ForeignKey(
        ROOM_PROFILE_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="boards",
        help_text="LOCATION board anchor: the room this board physically stands in.",
    )
    organization = models.ForeignKey(
        ORGANIZATION_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="boards",
        help_text="ORG board anchor: the organization this board belongs to.",
    )
    name = models.CharField(max_length=100, help_text="Display name for this board.")
    max_active_posts = models.PositiveSmallIntegerField(
        default=DEFAULT_MAX_ACTIVE_POSTS,
        help_text=(
            "Newest-first display cap. Older posts fall off the display but are "
            "retained in the DB (no auto-expiry at MVP)."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(room_profile__isnull=False) ^ models.Q(organization__isnull=False)
                ),
                name="board_exactly_one_anchor",
            ),
            models.UniqueConstraint(
                fields=["room_profile"],
                condition=models.Q(room_profile__isnull=False),
                name="unique_board_per_room",
            ),
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(organization__isnull=False),
                name="unique_board_per_org",
            ),
        ]

    def __str__(self) -> str:
        anchor = (
            f"room #{self.room_profile_id}"
            if self.room_profile_id
            else (f"org #{self.organization_id}")
        )
        return f"{self.name} ({anchor})"

    @property
    def is_location_board(self) -> bool:
        return self.room_profile_id is not None

    @property
    def is_org_board(self) -> bool:
        return self.organization_id is not None


class BoardPostQuerySet(models.QuerySet):
    """Custom queryset for BoardPost with soft-delete + display-cap helpers."""

    def active(self) -> BoardPostQuerySet:
        """Posts not soft-removed (``removed_at IS NULL``)."""
        return self.filter(removed_at__isnull=True)


class BoardPost(SharedMemoryModel):
    """A single IC notice pinned to a Board, authored by a Persona.

    Soft-delete only: ``remove_board_post`` stamps ``removed_by_persona``/
    ``removed_at`` rather than deleting the row, so moderation stays auditable.
    """

    board = models.ForeignKey(
        Board,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    author_persona = models.ForeignKey(
        PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="board_posts",
        help_text="The face that signed this notice (masked personas post under the mask).",
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    removed_by_persona = models.ForeignKey(
        PERSONA_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="board_posts_removed",
        help_text="Who took this post down (author, org moderator, or staff persona).",
    )
    removed_at = models.DateTimeField(null=True, blank=True)

    objects = BoardPostQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["board", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"BoardPost(#{self.pk}, board=#{self.board_id}, {self.title!r})"

    @property
    def is_removed(self) -> bool:
        return self.removed_at is not None
