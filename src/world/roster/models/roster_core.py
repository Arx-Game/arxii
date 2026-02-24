"""
Core roster models: Roster and RosterEntry.
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from evennia.objects.models import ObjectDB

if TYPE_CHECKING:
    from world.roster.models.tenures import RosterTenure

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.roster.managers import RosterEntryManager


class Roster(NaturalKeyMixin, models.Model):
    """
    Groups of characters by status (Active, Inactive, Available, etc.).
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="e.g., Active, Inactive, Available",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this roster category",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Can characters in this roster be played?",
    )
    is_public = models.BooleanField(
        default=True,
        help_text="Can characters in this roster be seen by players?",
    )
    allow_applications = models.BooleanField(
        default=True,
        help_text="Can players apply for characters in this roster?",
    )
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order")

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    class Meta:
        ordering: ClassVar[list[str]] = ["sort_order", "name"]


class RosterEntry(models.Model):
    """
    Bridge table linking characters to rosters. This is the core way to distinguish
    playable characters (and major NPCs) from regular game objects.
    Character's current roster status (Active, Inactive, etc.) lives here.
    """

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="roster_entry",
    )
    roster = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name="entries")

    # Profile picture - references specific media from character's current tenure
    profile_picture = models.ForeignKey(
        "roster.TenureMedia",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profile_for_entries",
        help_text="Profile picture for this character",
    )

    def clean(self) -> None:
        """Validate that profile picture belongs to this character's tenure."""
        super().clean()
        if self.profile_picture:
            if self.profile_picture.tenure.roster_entry != self:
                raise ValidationError(
                    {
                        "profile_picture": "Profile picture must belong to this "
                        "character's tenure.",
                    },
                )

    # Movement tracking
    joined_roster = models.DateTimeField(auto_now_add=True)
    previous_roster = models.ForeignKey(
        Roster,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="former_entries",
    )

    last_puppeted = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this character last entered the game world",
    )

    # Character status
    frozen = models.BooleanField(
        default=False,
        help_text="Character temporarily frozen (rarely used)",
    )

    # Staff notes
    gm_notes = models.TextField(blank=True)

    # Custom manager
    objects = RosterEntryManager()

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    @cached_property
    def cached_tenures(self) -> list[RosterTenure]:
        """Cached list of tenures for this entry."""
        return list(self.tenures.order_by("-start_date"))

    @property
    def current_tenure(self) -> RosterTenure | None:
        """Most recent tenure without an end date."""
        current = [tenure for tenure in self.cached_tenures if tenure.is_current]
        return current[0] if current else None

    @property
    def accepts_applications(self) -> bool:
        """Return True if this character can accept applications."""
        return self.roster.allow_applications and self.current_tenure is None

    def move_to_roster(self, new_roster: Roster) -> None:
        """Move character to a different roster"""
        self.previous_roster = self.roster
        self.roster = new_roster
        self.joined_roster = timezone.now()
        self.save()

    def __str__(self) -> str:
        return f"{self.character.name} ({self.roster.name})"

    class Meta:
        verbose_name = "Roster Entry"
        verbose_name_plural = "Roster Entries"
