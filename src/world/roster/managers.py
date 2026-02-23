"""
Custom managers and querysets for the roster system.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from evennia_extensions.models import PlayerData


class RosterEntryQuerySet(models.QuerySet):
    """Custom queryset for RosterEntry with filtering methods."""

    def active_rosters(self) -> RosterEntryQuerySet:
        """Filter to only entries in active rosters."""
        return self.filter(roster__is_active=True)

    def available_characters(self) -> RosterEntryQuerySet:
        """Filter to characters accepting applications."""
        return self.filter(roster__allow_applications=True).exclude(
            tenures__end_date__isnull=True,
        )

    def exclude_frozen(self) -> RosterEntryQuerySet:
        """Exclude frozen characters."""
        return self.filter(frozen=False)

    def by_roster_type(self, roster_type: str) -> RosterEntryQuerySet:
        """Filter by roster type name."""
        return self.filter(roster__name=roster_type)

    def exclude_roster_types(self, roster_types: list[str]) -> RosterEntryQuerySet:
        """Exclude specific roster types."""
        return self.exclude(roster__name__in=roster_types)

    def exclude_characters_for_player(self, player_data: PlayerData) -> RosterEntryQuerySet:
        """Exclude characters player has access to or pending applications."""
        # Characters player is already playing
        current_chars = player_data.get_available_characters()
        queryset = self

        if current_chars:
            queryset = queryset.exclude(character__in=current_chars)

        # Characters with pending applications from this player
        pending_apps = player_data.applications.filter(status="pending").values_list(
            "character_id",
            flat=True,
        )
        if pending_apps:
            queryset = queryset.exclude(character_id__in=pending_apps)

        return queryset


class RosterEntryManager(models.Manager):
    """Custom manager for RosterEntry."""

    def get_queryset(self) -> RosterEntryQuerySet:
        return RosterEntryQuerySet(self.model, using=self._db)

    def active_rosters(self) -> RosterEntryQuerySet:
        return self.get_queryset().active_rosters()

    def available_characters(self) -> RosterEntryQuerySet:
        return self.get_queryset().available_characters()

    def exclude_frozen(self) -> RosterEntryQuerySet:
        return self.get_queryset().exclude_frozen()

    def by_roster_type(self, roster_type: str) -> RosterEntryQuerySet:
        return self.get_queryset().by_roster_type(roster_type)

    def exclude_roster_types(self, roster_types: list[str]) -> RosterEntryQuerySet:
        return self.get_queryset().exclude_roster_types(roster_types)

    def exclude_characters_for_player(self, player_data: PlayerData) -> RosterEntryQuerySet:
        return self.get_queryset().exclude_characters_for_player(player_data)


class RosterApplicationQuerySet(models.QuerySet):
    """Custom queryset for RosterApplication."""

    def pending(self) -> RosterApplicationQuerySet:
        """Get all pending applications."""
        return self.filter(status="pending")

    def for_character(self, character: ObjectDB) -> RosterApplicationQuerySet:
        """Get all applications for a specific character."""
        return self.filter(character=character)

    def for_player(self, player_data: PlayerData) -> RosterApplicationQuerySet:
        """Get all applications by a specific player."""
        return self.filter(player_data=player_data)

    def approved(self) -> RosterApplicationQuerySet:
        """Get all approved applications."""
        return self.filter(status="approved")

    def denied(self) -> RosterApplicationQuerySet:
        """Get all denied applications."""
        return self.filter(status="denied")


class RosterApplicationManager(models.Manager):
    """Custom manager for RosterApplication."""

    def get_queryset(self) -> RosterApplicationQuerySet:
        return RosterApplicationQuerySet(self.model, using=self._db)

    def pending(self) -> RosterApplicationQuerySet:
        return self.get_queryset().pending()

    def for_character(self, character: ObjectDB) -> RosterApplicationQuerySet:
        return self.get_queryset().for_character(character)

    def for_player(self, player_data: PlayerData) -> RosterApplicationQuerySet:
        return self.get_queryset().for_player(player_data)

    def approved(self) -> RosterApplicationQuerySet:
        return self.get_queryset().approved()

    def denied(self) -> RosterApplicationQuerySet:
        return self.get_queryset().denied()

    def awaiting_review(self) -> RosterApplicationQuerySet:
        """Get pending applications ordered by application date"""
        return self.pending().order_by("applied_date")

    def recently_reviewed(self, days: int = 7) -> RosterApplicationQuerySet:
        """Get applications reviewed in the last N days"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.get_queryset().filter(reviewed_date__gte=cutoff_date).exclude(status="pending")


class RosterTenureQuerySet(models.QuerySet):
    """Custom queryset for RosterTenure."""

    def current(self) -> RosterTenureQuerySet:
        """Get current (active) tenures."""
        return self.filter(end_date__isnull=True)

    def ended(self) -> RosterTenureQuerySet:
        """Get ended tenures."""
        return self.filter(end_date__isnull=False)

    def for_player(self, player_data: PlayerData) -> RosterTenureQuerySet:
        """Get tenures for a specific player."""
        return self.filter(player_data=player_data)

    def for_character(self, character: ObjectDB) -> RosterTenureQuerySet:
        """Get tenures for a specific character."""
        return self.filter(character=character)


class RosterTenureManager(models.Manager):
    """Custom manager for RosterTenure."""

    def get_queryset(self) -> RosterTenureQuerySet:
        return RosterTenureQuerySet(self.model, using=self._db)

    def current(self) -> RosterTenureQuerySet:
        return self.get_queryset().current()

    def ended(self) -> RosterTenureQuerySet:
        return self.get_queryset().ended()

    def for_player(self, player_data: PlayerData) -> RosterTenureQuerySet:
        return self.get_queryset().for_player(player_data)

    def for_character(self, character: ObjectDB) -> RosterTenureQuerySet:
        return self.get_queryset().for_character(character)
