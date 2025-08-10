"""
Roster system models for character management.
Handles character rosters, player tenures, applications, and tenure-specific settings.
"""

from functools import cached_property

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from evennia_extensions.mixins import RelatedCacheClearingMixin
from world.roster.managers import (
    RosterApplicationManager,
    RosterEntryManager,
    RosterTenureManager,
)


class ApplicationStatus(models.TextChoices):
    """Application status choices"""

    PENDING = "pending", "Pending Review"
    APPROVED = "approved", "Approved"
    DENIED = "denied", "Denied"
    WITHDRAWN = "withdrawn", "Withdrawn"


class PlotInvolvement(models.TextChoices):
    """Plot involvement level choices"""

    HIGH = "high", "High - Very Active"
    MEDIUM = "medium", "Medium - Moderate"
    LOW = "low", "Low - Minimal"
    NONE = "none", "None - Social Only"


class RosterType(models.TextChoices):
    """Common roster type names for validation"""

    ACTIVE = "Active", "Active"
    INACTIVE = "Inactive", "Inactive"
    AVAILABLE = "Available", "Available"
    RESTRICTED = "Restricted", "Restricted"  # Characters requiring special approval
    FROZEN = "Frozen", "Frozen"


class ApprovalScope(models.TextChoices):
    """Approval scope choices for staff permissions"""

    ALL = "all", "All Characters"
    HOUSE = "house", "House Characters Only"
    STORY = "story", "Story Characters Only"
    NONE = "none", "No Approval Rights"


class ValidationErrorCodes:
    """Error codes for validation failures - for use with DRF serializers"""

    # Basic validation errors
    CHARACTER_NOT_ON_ROSTER = "character_not_on_roster"
    ALREADY_PLAYING_CHARACTER = "already_playing_character"
    CHARACTER_ALREADY_PLAYED = "character_already_played"
    DUPLICATE_PENDING_APPLICATION = "duplicate_pending_application"

    # Policy validation errors
    RESTRICTED_REQUIRES_REVIEW = "restricted_requires_review"
    INACTIVE_ROSTER = "inactive_roster"
    INSUFFICIENT_TRUST_LEVEL = "insufficient_trust_level"
    STORY_CONFLICT = "story_conflict"
    ROSTER_PERMISSION_DENIED = "roster_permission_denied"
    APPLICATION_LIMIT_EXCEEDED = "application_limit_exceeded"


class ValidationMessages:
    """User-friendly validation messages - for use with DRF serializers"""

    # Basic validation messages
    CHARACTER_NOT_ON_ROSTER = "Character is not on the roster"
    ALREADY_PLAYING_CHARACTER = "You are already playing this character"
    CHARACTER_ALREADY_PLAYED = "Character is already being played"
    DUPLICATE_PENDING_APPLICATION = (
        "You already have a pending application for this character"
    )

    # Policy validation messages
    RESTRICTED_REQUIRES_REVIEW = (
        "Character requires special approval and trust evaluation"
    )
    INACTIVE_ROSTER = "Character is in an inactive roster"
    INSUFFICIENT_TRUST_LEVEL = "Character requires higher trust level"
    STORY_CONFLICT = "Player involved in conflicting storylines"
    ROSTER_PERMISSION_DENIED = "Player not allowed to apply to this roster type"
    APPLICATION_LIMIT_EXCEEDED = "Too many pending applications"


# We'll add the managers after the model definitions to avoid circular imports


class Roster(models.Model):
    """
    Groups of characters by status (Active, Inactive, Available, etc.).
    """

    name = models.CharField(
        max_length=50, unique=True, help_text="e.g., Active, Inactive, Available"
    )
    description = models.TextField(
        blank=True, help_text="Description of this roster category"
    )
    is_active = models.BooleanField(
        default=True, help_text="Can characters in this roster be played?"
    )
    is_public = models.BooleanField(
        default=True, help_text="Can characters in this roster be seen by players?"
    )
    allow_applications = models.BooleanField(
        default=True,
        help_text="Can players apply for characters in this roster?",
    )
    sort_order = models.PositiveIntegerField(default=0, help_text="Display order")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["sort_order", "name"]


class RosterEntry(models.Model):
    """
    Bridge table linking characters to rosters. This is the core way to distinguish
    playable characters (and major NPCs) from regular game objects.
    Character's current roster status (Active, Inactive, etc.) lives here.
    """

    character = models.OneToOneField(
        ObjectDB, on_delete=models.CASCADE, related_name="roster_entry"
    )
    roster = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name="entries")

    # Profile picture - references specific media from character's current tenure
    profile_picture = models.ForeignKey(
        "TenureMedia",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profile_for_entries",
        help_text="Profile picture for this character",
    )

    def clean(self):
        """Validate that profile picture belongs to this character's tenure."""
        super().clean()
        if self.profile_picture:
            if self.profile_picture.tenure.roster_entry != self:
                raise ValidationError(
                    {
                        "profile_picture": "Profile picture must belong to this "
                        "character's tenure."
                    }
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

    # Character status
    frozen = models.BooleanField(
        default=False, help_text="Character temporarily frozen (rarely used)"
    )

    # Staff notes
    gm_notes = models.TextField(blank=True)

    # Custom manager
    objects = RosterEntryManager()

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    @cached_property
    def cached_tenures(self):
        """Cached list of tenures for this entry."""
        return list(self.tenures.order_by("-start_date"))

    @property
    def current_tenure(self):
        """Most recent tenure without an end date."""
        current = [tenure for tenure in self.cached_tenures if tenure.is_current]
        return current[0] if current else None

    @property
    def accepts_applications(self):
        """Return True if this character can accept applications."""
        return self.roster.allow_applications and self.current_tenure is None

    def move_to_roster(self, new_roster):
        """Move character to a different roster"""
        self.previous_roster = self.roster
        self.roster = new_roster
        self.joined_roster = timezone.now()
        self.save()

    def __str__(self):
        return f"{self.character.name} ({self.roster.name})"

    class Meta:
        verbose_name = "Roster Entry"
        verbose_name_plural = "Roster Entries"


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
        RosterEntry, on_delete=models.CASCADE, related_name="tenures"
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


class RosterApplication(models.Model):
    """
    Tracks applications before they become tenures.
    Separate from tenure to keep application data clean.
    """

    # Using ApplicationStatus TextChoices defined above

    # Custom manager
    objects = RosterApplicationManager()

    player_data = models.ForeignKey(
        "evennia_extensions.PlayerData",
        on_delete=models.CASCADE,
        related_name="applications",
    )
    character = models.ForeignKey(
        ObjectDB, on_delete=models.CASCADE, related_name="applications"
    )

    # Application status
    status = models.CharField(
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING,
    )

    # Dates
    applied_date = models.DateTimeField(auto_now_add=True)
    reviewed_date = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "evennia_extensions.PlayerData",
        null=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_applications",
    )

    # Application content
    application_text = models.TextField(help_text="Why player wants this character")
    review_notes = models.TextField(blank=True, help_text="Staff notes on application")

    def approve(self, staff_player_data):
        """Approve application and create tenure"""
        if self.status != ApplicationStatus.PENDING:
            return False

        # Create the tenure
        player_number = self.character.roster_entry.tenures.count() + 1
        tenure = RosterTenure.objects.create(
            player_data=self.player_data,
            roster_entry=self.character.roster_entry,
            player_number=player_number,
            start_date=timezone.now(),
            applied_date=self.applied_date,
            approved_date=timezone.now(),
            approved_by=staff_player_data,
        )

        # Update application
        self.status = ApplicationStatus.APPROVED
        self.reviewed_date = timezone.now()
        self.reviewed_by = staff_player_data
        self.save()

        # Send approval email
        try:
            from world.roster.email_service import RosterEmailService

            RosterEmailService.send_application_approved(self, tenure)
        except Exception:
            # Don't fail the approval if email fails
            pass

        return tenure

    def get_policy_review_info(self):
        """
        Get comprehensive policy information for reviewers.

        Returns a dict with all policy considerations for this application.
        """
        # Import at method level to avoid circular imports with DRF serializers
        from world.roster.policy_service import RosterPolicyService

        return RosterPolicyService.get_comprehensive_policy_info(self)

    def deny(self, staff_player_data, reason=""):
        """Deny application"""
        if self.status != ApplicationStatus.PENDING:
            return False

        self.status = ApplicationStatus.DENIED
        self.reviewed_date = timezone.now()
        self.reviewed_by = staff_player_data
        if reason:
            self.review_notes = reason
        self.save()

        # Send denial email
        try:
            from world.roster.email_service import RosterEmailService

            RosterEmailService.send_application_denied(self)
        except Exception:
            # Don't fail the denial if email fails
            pass

        return True

    def withdraw(self):
        """Player withdraws their own application"""
        if self.status != ApplicationStatus.PENDING:
            return False

        self.status = ApplicationStatus.WITHDRAWN
        self.reviewed_date = timezone.now()
        self.save()
        return True

    # Validation logic moved to serializers for better separation of concerns

    # Application creation logic moved to serializers for better validation handling

    def __str__(self):
        return (
            f"{self.player_data.account.username} applying for "
            f"{self.character.name} ({self.status})"
        )

    class Meta:
        unique_together = ["player_data", "character"]  # One app per player per char
        ordering = ["-applied_date"]
        verbose_name = "Roster Application"
        verbose_name_plural = "Roster Applications"


class TenureDisplaySettings(models.Model):
    """
    Character-specific UI and display settings tied to a tenure.
    Each setting gets its own column for proper indexing and validation.
    """

    tenure = models.OneToOneField(
        RosterTenure, on_delete=models.CASCADE, related_name="display_settings"
    )

    # Display preferences
    public_character_info = models.BooleanField(
        default=True, help_text="Show character in public roster listings"
    )
    show_online_status = models.BooleanField(
        default=True, help_text="Show when this character is online"
    )
    allow_pages = models.BooleanField(
        default=True, help_text="Allow other players to page this character"
    )
    allow_tells = models.BooleanField(
        default=True, help_text="Allow other players to send tells to this character"
    )

    # Roleplay preferences
    rp_preferences = models.CharField(
        max_length=500, blank=True, help_text="Freeform RP preferences and notes"
    )
    plot_involvement = models.CharField(
        max_length=20,
        choices=PlotInvolvement.choices,
        default=PlotInvolvement.MEDIUM,
    )

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Display settings for {self.tenure.character.name}"

    class Meta:
        verbose_name = "Tenure Display Settings"
        verbose_name_plural = "Tenure Display Settings"


class TenureMedia(models.Model):
    """Bridge between player media and character tenures."""

    tenure = models.ForeignKey(
        RosterTenure, on_delete=models.CASCADE, related_name="media"
    )
    media = models.ForeignKey(
        "evennia_extensions.PlayerMedia",
        on_delete=models.CASCADE,
        related_name="tenure_links",
    )

    # Organization
    sort_order = models.PositiveIntegerField(default=0)

    # Visibility
    is_public = models.BooleanField(default=True, help_text="Visible to other players")

    def __str__(self):
        title = self.media.title or "Untitled"
        return f"{self.media.media_type} for {self.tenure.character.name} ({title})"

    class Meta:
        ordering = ["sort_order", "-media__uploaded_date"]
        indexes = [models.Index(fields=["tenure", "sort_order"])]
        verbose_name = "Tenure Media"
        verbose_name_plural = "Tenure Media"


class PlayerMail(models.Model):
    """
    Mail system with tenure targeting.
    Players send "mail Ariel" → routes to current player via RosterTenure.
    """

    # Sender info
    sender_account = models.ForeignKey(
        AccountDB, on_delete=models.CASCADE, related_name="sent_mail"
    )
    sender_character = models.ForeignKey(
        ObjectDB,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_mail",
        help_text="Character context when mail was sent",
    )

    # Recipient info (references tenure for anonymity)
    recipient_tenure = models.ForeignKey(
        RosterTenure,
        on_delete=models.CASCADE,
        related_name="received_mail",
        help_text="Mail targets the character, routes to current player via roster entry",
    )

    # Mail content
    subject = models.CharField(max_length=200)
    message = models.TextField()

    # State tracking
    sent_date = models.DateTimeField(auto_now_add=True)
    read_date = models.DateTimeField(null=True, blank=True)
    archived = models.BooleanField(default=False)

    # Thread support
    in_reply_to = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies"
    )

    @property
    def is_read(self):
        """True if recipient has read this mail"""
        return self.read_date is not None

    def mark_read(self):
        """Mark mail as read"""
        if not self.is_read:
            self.read_date = timezone.now()
            self.save()

    def get_thread_messages(self):
        """Get all messages in this thread"""
        # Find root message
        root = self
        while root.in_reply_to:
            root = root.in_reply_to

        # Get all replies in chronological order
        return PlayerMail.objects.filter(
            models.Q(pk=root.pk) | models.Q(in_reply_to=root)
        ).order_by("sent_date")

    def __str__(self):
        return (
            f"Mail from {self.sender_account.username} to "
            f"{self.recipient_tenure.roster_entry.character.name}"
        )

    class Meta:
        ordering = ["-sent_date"]
        indexes = [
            models.Index(fields=["recipient_tenure", "read_date"]),
            models.Index(fields=["sender_account", "sent_date"]),
        ]
