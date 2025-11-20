"""
Custom managers and querysets for the roster system.
"""

from django.db import models


class RosterEntryQuerySet(models.QuerySet):
    """Custom queryset for RosterEntry with filtering methods."""

    def active_rosters(self):
        """Filter to only entries in active rosters."""
        return self.filter(roster__is_active=True)

    def available_characters(self):
        """Filter to characters accepting applications."""
        return self.filter(roster__allow_applications=True).exclude(
            tenures__end_date__isnull=True,
        )

    def exclude_frozen(self):
        """Exclude frozen characters."""
        return self.filter(frozen=False)

    def by_roster_type(self, roster_type):
        """Filter by roster type name."""
        return self.filter(roster__name=roster_type)

    def exclude_roster_types(self, roster_types):
        """Exclude specific roster types."""
        return self.exclude(roster__name__in=roster_types)

    def exclude_characters_for_player(self, player_data):
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

    def get_queryset(self):
        return RosterEntryQuerySet(self.model, using=self._db)

    def active_rosters(self):
        return self.get_queryset().active_rosters()

    def available_characters(self):
        return self.get_queryset().available_characters()

    def exclude_frozen(self):
        return self.get_queryset().exclude_frozen()

    def by_roster_type(self, roster_type):
        return self.get_queryset().by_roster_type(roster_type)

    def exclude_roster_types(self, roster_types):
        return self.get_queryset().exclude_roster_types(roster_types)

    def exclude_characters_for_player(self, player_data):
        return self.get_queryset().exclude_characters_for_player(player_data)


class RosterApplicationQuerySet(models.QuerySet):
    """Custom queryset for RosterApplication."""

    def pending(self):
        """Get all pending applications."""
        return self.filter(status="pending")

    def for_character(self, character):
        """Get all applications for a specific character."""
        return self.filter(character=character)

    def for_player(self, player_data):
        """Get all applications by a specific player."""
        return self.filter(player_data=player_data)

    def approved(self):
        """Get all approved applications."""
        return self.filter(status="approved")

    def denied(self):
        """Get all denied applications."""
        return self.filter(status="denied")


class RosterApplicationManager(models.Manager):
    """Custom manager for RosterApplication."""

    def get_queryset(self):
        return RosterApplicationQuerySet(self.model, using=self._db)

    def pending(self):
        return self.get_queryset().pending()

    def for_character(self, character):
        return self.get_queryset().for_character(character)

    def for_player(self, player_data):
        return self.get_queryset().for_player(player_data)

    def approved(self):
        return self.get_queryset().approved()

    def denied(self):
        return self.get_queryset().denied()

    def awaiting_review(self):
        """Get pending applications ordered by application date"""
        return self.pending().order_by("applied_date")

    def recently_reviewed(self, days=7):
        """Get applications reviewed in the last N days"""
        from datetime import timedelta

        from django.utils import timezone

        cutoff_date = timezone.now() - timedelta(days=days)
        return (
            self.get_queryset()
            .filter(reviewed_date__gte=cutoff_date)
            .exclude(status="pending")
        )


class RosterTenureQuerySet(models.QuerySet):
    """Custom queryset for RosterTenure."""

    def current(self):
        """Get current (active) tenures."""
        return self.filter(end_date__isnull=True)

    def ended(self):
        """Get ended tenures."""
        return self.filter(end_date__isnull=False)

    def for_player(self, player_data):
        """Get tenures for a specific player."""
        return self.filter(player_data=player_data)

    def for_character(self, character):
        """Get tenures for a specific character."""
        return self.filter(character=character)


class RosterTenureManager(models.Manager):
    """Custom manager for RosterTenure."""

    def get_queryset(self):
        return RosterTenureQuerySet(self.model, using=self._db)

    def current(self):
        return self.get_queryset().current()

    def ended(self):
        return self.get_queryset().ended()

    def for_player(self, player_data):
        return self.get_queryset().for_player(player_data)

    def for_character(self, character):
        return self.get_queryset().for_character(character)
