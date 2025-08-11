"""
Extensions to Evennia models.
This app extends Evennia's core models rather than replacing them.
"""

from functools import cached_property

from django.db import models
from evennia.accounts.models import AccountDB

from evennia_extensions.mixins import RelatedCacheClearingMixin


class MediaType(models.TextChoices):
    """Media type choices for player uploads."""

    PHOTO = "photo", "Photo"
    PORTRAIT = "portrait", "Character Portrait"
    GALLERY = "gallery", "Gallery Image"


class PlayerData(RelatedCacheClearingMixin, models.Model):
    """
    Extends Evennia's AccountDB with additional player data.
    Uses evennia_extensions pattern instead of replacing Account entirely.
    Replaces all ArxI attribute usage with proper model fields.
    """

    account = models.OneToOneField(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="player_data",
        primary_key=True,
    )

    # Clear account's cached properties when player data changes
    related_cache_fields = ["account"]

    # Player preferences (replaces attributes like db.hide_from_watch)
    display_name = models.CharField(
        max_length=100, blank=True, help_text="How they appear to others"
    )
    karma = models.PositiveIntegerField(default=0)
    hide_from_watch = models.BooleanField(default=False)
    private_mode = models.BooleanField(default=False)

    # Staff data
    gm_notes = models.TextField(blank=True, help_text="Staff notes about player")

    # Session tracking (replaces attributes)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    # Media settings
    profile_picture = models.ForeignKey(
        "PlayerMedia",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profile_for_players",
        help_text="Profile picture for this account",
    )
    max_storage = models.PositiveIntegerField(
        default=0,
        help_text="Max number of media files this player may store",
    )
    max_file_size = models.PositiveIntegerField(
        default=0,
        help_text="Max upload size per file in KB",
    )

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    @property
    def avatar_url(self):
        if not self.profile_picture:
            return None
        return self.profile_picture.cloudinary_url

    @cached_property
    def cached_tenures(self):
        """Cached list of all tenures for this player. Use with prefetch_related."""
        return list(self.tenures.all())

    @property
    def cached_active_tenures(self):
        """List of currently active tenures for this player (uses cached data)."""
        return [tenure for tenure in self.cached_tenures if tenure.is_current]

    def get_available_characters(self):
        """Return characters this player is actively playing using cached data."""
        return [
            tenure.roster_entry.character
            for tenure in self.cached_active_tenures
            if tenure.roster_entry.roster.is_active
        ]

    def get_current_character(self):
        """Get the character this player is currently logged in as"""
        # This would be set when player switches characters via @ic command
        # For now, return the first available character if any
        characters = self.get_available_characters()
        return characters[0] if characters else None

    def get_pending_applications(self):
        """Get all pending applications for this player"""
        from world.roster.models import ApplicationStatus, RosterApplication

        return RosterApplication.objects.filter(
            player_data=self, status=ApplicationStatus.PENDING
        )

    def can_approve_applications(self):
        """Check if this player has any application approval permissions"""
        # This will integrate with the trust system when implemented
        # For now, just check if they're staff
        return self.account.is_staff

    def get_approval_scope(self):
        """Get the scope of applications this player can approve"""
        # This will return specific character types, houses, etc. when trust system
        # is implemented
        # For now, return all if staff, none otherwise
        from world.roster.models import ApprovalScope

        if self.account.is_staff:
            return ApprovalScope.ALL
        return ApprovalScope.NONE

    def __str__(self):
        return f"PlayerData for {self.account.username}"

    class Meta:
        verbose_name = "Player Data"
        verbose_name_plural = "Player Data"


class Artist(models.Model):
    """Represents a player offering art commissions."""

    player_data = models.OneToOneField(
        PlayerData, on_delete=models.CASCADE, related_name="artist_profile"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    commission_notes = models.TextField(blank=True)
    accepting_commissions = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Artist"
        verbose_name_plural = "Artists"


class PlayerMedia(models.Model):
    """Media files uploaded by players."""

    player_data = models.ForeignKey(
        PlayerData, on_delete=models.CASCADE, related_name="media"
    )
    cloudinary_public_id = models.CharField(
        max_length=255, help_text="Cloudinary public ID for this media"
    )
    cloudinary_url = models.URLField(help_text="Full Cloudinary URL")
    media_type = models.CharField(
        max_length=20, choices=MediaType.choices, default=MediaType.PHOTO
    )
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        Artist,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_media",
        help_text="Artist who created this media",
    )
    uploaded_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        title = self.title or "Untitled"
        return f"{self.media_type} for {self.player_data.account.username} ({title})"

    class Meta:
        ordering = ["-uploaded_date"]
        indexes = [models.Index(fields=["player_data", "media_type"])]


class ObjectDisplayData(models.Model):
    """
    Generic display data for any Evennia object.

    Provides customizable names, descriptions, and thumbnails that can be used
    by any object in the game (characters, rooms, items, etc.). This replaces
    the need for object-specific display models and allows unified handling
    of object presentation.
    """

    object = models.OneToOneField(
        "objects.ObjectDB",
        on_delete=models.CASCADE,
        related_name="display_data",
        primary_key=True,
        help_text="The object this display data belongs to",
    )

    # Display names
    colored_name = models.CharField(
        max_length=255, blank=True, help_text="Name with color formatting codes"
    )
    longname = models.CharField(
        max_length=255,
        blank=True,
        help_text="Full object name with titles/descriptions",
    )

    # Descriptions
    permanent_description = models.TextField(
        blank=True, help_text="Object's permanent description"
    )
    temporary_description = models.TextField(
        blank=True, help_text="Temporary description (masks, illusions, etc.)"
    )

    # Visual representation
    thumbnail = models.ForeignKey(
        PlayerMedia,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="thumbnailed_objects",
        help_text="Visual representation for this object",
    )

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def get_display_description(self):
        """Get the appropriate description, with temporary overriding permanent."""
        return self.temporary_description or self.permanent_description or ""

    def get_display_name(self, include_colored=True):
        """
        Get the appropriate display name with fallback hierarchy.

        Args:
            include_colored (bool): Whether to include colored names

        Returns:
            str: The most appropriate display name
        """
        if include_colored and self.colored_name:
            return self.colored_name
        elif self.longname:
            return self.longname
        else:
            return self.object.key

    def __str__(self):
        return f"Display data for {self.object.key}"

    class Meta:
        verbose_name = "Object Display Data"
        verbose_name_plural = "Object Display Data"


class PlayerAllowList(models.Model):
    """
    Players this account allows to contact them (friends/allowlist).
    """

    owner = models.ForeignKey(
        PlayerData, on_delete=models.CASCADE, related_name="allow_list"
    )
    allowed_player = models.ForeignKey(
        PlayerData, on_delete=models.CASCADE, related_name="allowed_by"
    )
    added_date = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(
        max_length=200, blank=True, help_text="Optional note about this player"
    )

    def __str__(self):
        owner_name = self.owner.account.username
        allowed_name = self.allowed_player.account.username
        return f"{owner_name} allows {allowed_name}"

    class Meta:
        unique_together = ["owner", "allowed_player"]
        verbose_name = "Player Allow List Entry"
        verbose_name_plural = "Player Allow List Entries"


class PlayerBlockList(models.Model):
    """
    Players this account blocks from contacting them.
    """

    owner = models.ForeignKey(
        PlayerData, on_delete=models.CASCADE, related_name="block_list"
    )
    blocked_player = models.ForeignKey(
        PlayerData, on_delete=models.CASCADE, related_name="blocked_by"
    )
    blocked_date = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(
        max_length=200, blank=True, help_text="Optional reason for blocking"
    )

    def __str__(self):
        owner_name = self.owner.account.username
        blocked_name = self.blocked_player.account.username
        return f"{owner_name} blocks {blocked_name}"

    class Meta:
        unique_together = ["owner", "blocked_player"]
        verbose_name = "Player Block List Entry"
        verbose_name_plural = "Player Block List Entries"
