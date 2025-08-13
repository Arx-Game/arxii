"""
RosterTenure model for tracking player-character relationships.
"""

from functools import cached_property

from django.db import models

from evennia_extensions.mixins import RelatedCacheClearingMixin
from world.roster.managers import RosterTenureManager


class RosterTenure(RelatedCacheClearingMixin, models.Model):
    """
    Tracks when a player plays a character with built-in anonymity.
    Players are identified only as "1st player", "2nd player", etc.
    Links to RosterEntry to keep all roster-related data together.
    """

    player_data = models.ForeignKey(
        "evennia_extensions.PlayerData",
        on_delete=models.CASCADE,
        related_name="tenures",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry", on_delete=models.CASCADE, related_name="tenures"
    )

    # Automatically clear player_data caches when tenure changes
    related_cache_fields = ["player_data"]

    # Anonymity system
    player_number = models.PositiveIntegerField(
        help_text="1st, 2nd, 3rd player of this character",
        default=1,
    )

    # Tenure tracking
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(
        null=True, blank=True, help_text="null = current player"
    )

    # Application tracking
    applied_date = models.DateTimeField(null=True, blank=True)
    approved_date = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "evennia_extensions.PlayerData",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_tenures",
    )

    # Staff notes (visible to staff only)
    tenure_notes = models.TextField(
        blank=True, help_text="Notes about this specific tenure"
    )

    # Photo storage (Cloudinary) - tied to tenure, not character
    # This prevents photo galleries from being wiped when characters change hands
    photo_folder = models.CharField(
        max_length=255,
        blank=True,
        help_text="Cloudinary folder for this tenure's photos",
    )

    # Custom manager
    objects = RosterTenureManager()

    @cached_property
    def cached_media(self):
        """Prefetched media for this tenure."""
        return list(self.media.all())

    @property
    def display_name(self):
        """Returns anonymous display like '2nd player of Ariel'"""
        character_name = (
            self.roster_entry.character.name
            if self.roster_entry
            else "Unknown Character"
        )

        if self.player_number is None:
            return f"Player of {character_name}"

        # Handle special cases for 11th, 12th, 13th
        if 10 <= self.player_number % 100 <= 13:
            suffix = "th"
        else:
            suffixes = {1: "st", 2: "nd", 3: "rd"}
            suffix = suffixes.get(self.player_number % 10, "th")
        return f"{self.player_number}{suffix} player of {character_name}"

    @property
    def is_current(self):
        """True if this is the current active tenure for the character"""
        return self.end_date is None

    @property
    def character(self):
        """Convenience property to access character through roster_entry."""
        return self.roster_entry.character if self.roster_entry else None

    def __str__(self):
        status = "current" if self.is_current else f"ended {self.end_date}"
        return f"{self.display_name} ({status})"

    class Meta:
        unique_together = [
            "roster_entry",
            "player_number",
        ]  # Each character has 1st, 2nd, etc.
        indexes = [
            models.Index(fields=["roster_entry", "end_date"]),  # Find current player
            models.Index(
                fields=["player_data", "end_date"]
            ),  # Find player's current chars
        ]
        verbose_name = "Roster Tenure"
        verbose_name_plural = "Roster Tenures"
