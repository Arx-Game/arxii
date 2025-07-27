"""
Roster system models for character management.
Handles character rosters, player tenures, applications, and tenure-specific settings.
"""

from django.db import models
from django.utils import timezone
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB


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

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

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


class RosterTenure(models.Model):
    """
    Tracks when a player plays a character with built-in anonymity.
    Players are identified only as "1st player", "2nd player", etc.
    Separate from RosterEntry - this is about WHO played WHEN.
    """

    player_data = models.ForeignKey(
        "evennia_extensions.PlayerData",
        on_delete=models.CASCADE,
        related_name="tenures",
    )
    character = models.ForeignKey(
        ObjectDB, on_delete=models.CASCADE, related_name="tenures"
    )

    # Anonymity system
    player_number = models.PositiveIntegerField(
        help_text="1st, 2nd, 3rd player of this character"
    )

    # Tenure tracking
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(
        null=True, blank=True, help_text="null = current player"
    )

    # Application tracking
    applied_date = models.DateTimeField()
    approved_date = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "evennia_extensions.PlayerData",
        null=True,
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

    @property
    def display_name(self):
        """Returns anonymous display like '2nd player of Ariel'"""
        suffixes = {1: "st", 2: "nd", 3: "rd"}
        suffix = suffixes.get(self.player_number, "th")
        return f"{self.player_number}{suffix} player of {self.character.name}"

    @property
    def is_current(self):
        """True if this is the current active tenure for the character"""
        return self.end_date is None

    def __str__(self):
        status = "current" if self.is_current else f"ended {self.end_date}"
        return f"{self.display_name} ({status})"

    class Meta:
        unique_together = [
            "character",
            "player_number",
        ]  # Each character has 1st, 2nd, etc.
        indexes = [
            models.Index(fields=["character", "end_date"]),  # Find current player
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

    STATUS_CHOICES = [
        ("pending", "Pending Review"),
        ("approved", "Approved"),
        ("denied", "Denied"),
        ("withdrawn", "Withdrawn"),
    ]

    player_data = models.ForeignKey(
        "evennia_extensions.PlayerData",
        on_delete=models.CASCADE,
        related_name="applications",
    )
    character = models.ForeignKey(
        ObjectDB, on_delete=models.CASCADE, related_name="applications"
    )

    # Application status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

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
        if self.status != "pending":
            return False

        # Create the tenure
        player_number = self.character.tenures.count() + 1
        tenure = RosterTenure.objects.create(
            player_data=self.player_data,
            character=self.character,
            player_number=player_number,
            start_date=timezone.now(),
            applied_date=self.applied_date,
            approved_date=timezone.now(),
            approved_by=staff_player_data,
        )

        # Update application
        self.status = "approved"
        self.reviewed_date = timezone.now()
        self.reviewed_by = staff_player_data
        self.save()

        return tenure

    def deny(self, staff_player_data, reason=""):
        """Deny application"""
        if self.status != "pending":
            return False

        self.status = "denied"
        self.reviewed_date = timezone.now()
        self.reviewed_by = staff_player_data
        if reason:
            self.review_notes = reason
        self.save()

        return True

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
        choices=[
            ("high", "High - Very Active"),
            ("medium", "Medium - Moderate"),
            ("low", "Low - Minimal"),
            ("none", "None - Social Only"),
        ],
        default="medium",
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
    """
    Photo galleries and media tied to tenures, not characters.
    This prevents media from being wiped when characters change hands.
    """

    MEDIA_TYPE_CHOICES = [
        ("photo", "Photo"),
        ("portrait", "Character Portrait"),
        ("gallery", "Gallery Image"),
    ]

    tenure = models.ForeignKey(
        RosterTenure, on_delete=models.CASCADE, related_name="media"
    )

    # Cloudinary integration
    cloudinary_public_id = models.CharField(
        max_length=255, help_text="Cloudinary public ID for this media"
    )
    cloudinary_url = models.URLField(help_text="Full Cloudinary URL")

    # Media metadata
    media_type = models.CharField(
        max_length=20, choices=MEDIA_TYPE_CHOICES, default="photo"
    )
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)

    # Organization
    sort_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(
        default=False, help_text="Primary photo for this character"
    )

    # Visibility
    is_public = models.BooleanField(default=True, help_text="Visible to other players")

    # Timestamps
    uploaded_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        title = self.title or "Untitled"
        return f"{self.media_type} for {self.tenure.character.name} ({title})"

    class Meta:
        ordering = ["sort_order", "-uploaded_date"]
        indexes = [
            models.Index(fields=["tenure", "media_type"]),
            models.Index(fields=["tenure", "is_primary"]),
        ]
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
        help_text="Mail targets the character, routes to current player",
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
            f"{self.recipient_tenure.character.name}"
        )

    class Meta:
        ordering = ["-sent_date"]
        indexes = [
            models.Index(fields=["recipient_tenure", "read_date"]),
            models.Index(fields=["sender_account", "sent_date"]),
        ]
