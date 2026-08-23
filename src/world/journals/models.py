"""Journal system models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from world.character_sheets.models import CharacterSheet
from world.journals.constants import PosthumousOverride, ResponseType

if TYPE_CHECKING:
    from world.game_clock.models import GameWeek


class JournalEntry(SharedMemoryModel):
    """A single journal entry written by a character."""

    author = models.ForeignKey(
        CharacterSheet,
        on_delete=models.CASCADE,
        related_name="journal_entries",
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_public = models.BooleanField(default=False)

    # Response linking
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="responses",
    )
    response_type = models.CharField(
        max_length=10,
        choices=ResponseType.choices,
        null=True,
        blank=True,
    )

    # Related threads (Spec A §2.2)
    related_threads = models.ManyToManyField(
        "arxii.Thread",
        blank=True,
        related_name="related_journal_entries",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    # IC timestamp — placeholder for IC time system
    ic_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="System-derived IC timestamp. Populated when IC time system exists.",
    )

    # Posthumous disposition (#3287) — the black journal afterlife. INHERIT (default) falls
    # through to the author's CharacterSheet.posthumous_journal_disposition; REVEAL/SEAL pin
    # this one entry. revealed_at/revealed_by_settlement are stamped ONLY by
    # world.journals.services.reveal_journals_for_settlement, called from
    # estates.services.execute_settlement — never any other path. is_public is never mutated
    # by a reveal, so authorship history stays true even after the entry surfaces.
    posthumous_override = models.CharField(
        max_length=7,
        choices=PosthumousOverride.choices,
        default=PosthumousOverride.INHERIT,
    )
    revealed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Stamped at estate settlement when this private entry's disposition is REVEAL.",
    )
    revealed_by_settlement = models.ForeignKey(
        "arxii.EstateSettlement",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revealed_journal_entries",
        help_text="Which settlement revealed this entry — audit trail (#3287 spec Decision 2).",
    )

    class Meta:
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["author", "-created_at"]),
            models.Index(fields=["is_public", "-created_at"]),
            models.Index(fields=["revealed_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(
                        parent__isnull=True,
                        response_type__isnull=True,
                    )
                    | models.Q(
                        parent__isnull=False,
                        response_type__isnull=False,
                    )
                ),
                name="response_fields_consistent",
            ),
        ]

    @cached_property
    def cached_tags(self) -> list:
        """Tags for this entry. Supports Prefetch(to_attr=)."""
        return list(self.tags.all())

    @cached_property
    def cached_responses(self) -> list:
        """Responses to this entry. Supports Prefetch(to_attr=)."""
        return list(self.responses.all())

    def effective_posthumous_disposition(self) -> str:
        """Resolve INHERIT to the author's sheet-level default (#3287).

        Returns a plain string comparable to both ``PosthumousOverride`` and
        ``CharacterSheet.PosthumousJournalDisposition`` values — the two TextChoices
        deliberately share the "reveal"/"seal" literals.
        """
        if self.posthumous_override != PosthumousOverride.INHERIT:
            return self.posthumous_override
        return self.author.posthumous_journal_disposition

    def __str__(self) -> str:
        return f"{self.title} by {self.author}"


class JournalTag(SharedMemoryModel):
    """Freeform tag on a journal entry."""

    entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name="tags",
    )
    name = models.CharField(max_length=100, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entry", "name"], name="unique_tag_per_entry"),
        ]

    def __str__(self) -> str:
        return self.name


class WeeklyJournalXP(SharedMemoryModel):
    """Tracks weekly journal XP caps per character."""

    character_sheet = models.OneToOneField(
        CharacterSheet,
        on_delete=models.CASCADE,
        related_name="weekly_journal_xp",
    )
    game_week = models.ForeignKey(
        "arxii.GameWeek",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="journal_xp_trackers",
        help_text="GameWeek these counters belong to",
    )
    posts_this_week = models.PositiveSmallIntegerField(default=0)
    praised_this_week = models.BooleanField(default=False)
    was_praised_this_week = models.BooleanField(default=False)
    retorted_this_week = models.BooleanField(default=False)
    was_retorted_this_week = models.BooleanField(default=False)

    def needs_reset(self, current_week: GameWeek) -> bool:
        """Check if this tracker is for a different game week."""
        return self.game_week_id != current_week.pk

    def reset_week(self, current_week: GameWeek) -> None:
        """Reset all weekly counters and set to current game week."""
        self.posts_this_week = 0
        self.praised_this_week = False
        self.was_praised_this_week = False
        self.retorted_this_week = False
        self.was_retorted_this_week = False
        self.game_week = current_week
        self.save(
            update_fields=[
                "posts_this_week",
                "praised_this_week",
                "was_praised_this_week",
                "retorted_this_week",
                "was_retorted_this_week",
                "game_week",
            ]
        )

    def __str__(self) -> str:
        return f"WeeklyJournalXP for {self.character_sheet}"


class JournalBequestGrant(SharedMemoryModel):
    """A bequest of writings: read access to a deceased sheet's non-sealed private entries.

    Minted ONLY inside ``estates.services.execute_settlement`` (via
    ``world.journals.services.grant_journal_bequest``) when the deceased's will carries a
    ``BequestKind.WRITINGS`` line — never any other way, so the grant's mere existence proves
    a settlement happened (#3287 Decision 3). SEAL beats a grant: a sealed entry stays
    unreadable even to a granted recipient — enforced at the read path, not here.
    """

    recipient_sheet = models.ForeignKey(
        CharacterSheet,
        on_delete=models.CASCADE,
        related_name="journal_bequests_received",
    )
    deceased_sheet = models.ForeignKey(
        CharacterSheet,
        on_delete=models.CASCADE,
        related_name="journal_bequests_granted",
    )
    created_by_settlement = models.ForeignKey(
        "arxii.EstateSettlement",
        on_delete=models.CASCADE,
        related_name="journal_bequest_grants",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["deceased_sheet_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient_sheet", "deceased_sheet"],
                name="unique_journal_bequest_grant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.recipient_sheet} inherits {self.deceased_sheet}'s writings"
