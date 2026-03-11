"""Journal system models."""

from datetime import timedelta

from django.db import models
from django.utils import timezone

from world.character_sheets.models import CharacterSheet
from world.journals.constants import ResponseType


class JournalEntry(models.Model):
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

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    # IC timestamp — placeholder for IC time system
    ic_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="System-derived IC timestamp. Populated when IC time system exists.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["author", "-created_at"]),
            models.Index(fields=["is_public", "-created_at"]),
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

    def __str__(self) -> str:
        return f"{self.title} by {self.author}"


class JournalTag(models.Model):
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


class WeeklyJournalXP(models.Model):
    """Tracks weekly journal XP caps per character."""

    character_sheet = models.OneToOneField(
        CharacterSheet,
        on_delete=models.CASCADE,
        related_name="weekly_journal_xp",
    )
    posts_this_week = models.PositiveSmallIntegerField(default=0)
    praised_this_week = models.BooleanField(default=False)
    was_praised_this_week = models.BooleanField(default=False)
    retorted_this_week = models.BooleanField(default=False)
    was_retorted_this_week = models.BooleanField(default=False)
    week_reset_at = models.DateTimeField(auto_now_add=True)

    def needs_reset(self) -> bool:
        """Check if a week has passed since last reset."""
        return timezone.now() - self.week_reset_at >= timedelta(days=7)

    def reset_week(self) -> None:
        """Reset all weekly counters and update timestamp."""
        self.posts_this_week = 0
        self.praised_this_week = False
        self.was_praised_this_week = False
        self.retorted_this_week = False
        self.was_retorted_this_week = False
        self.week_reset_at = timezone.now()
        self.save(
            update_fields=[
                "posts_this_week",
                "praised_this_week",
                "was_praised_this_week",
                "retorted_this_week",
                "was_retorted_this_week",
                "week_reset_at",
            ]
        )

    def __str__(self) -> str:
        return f"WeeklyJournalXP for {self.character_sheet}"
