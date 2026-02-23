"""
Settings and media models for roster tenures.
"""

from typing import ClassVar

from django.db import models

from .choices import PlotInvolvement


class TenureDisplaySettings(models.Model):
    """
    Character-specific UI and display settings tied to a tenure.
    Each setting gets its own column for proper indexing and validation.
    """

    tenure = models.OneToOneField(
        "roster.RosterTenure",
        on_delete=models.CASCADE,
        related_name="display_settings",
    )

    # Display preferences
    public_character_info = models.BooleanField(
        default=True,
        help_text="Show character in public roster listings",
    )
    show_online_status = models.BooleanField(
        default=True,
        help_text="Show when this character is online",
    )
    allow_pages = models.BooleanField(
        default=True,
        help_text="Allow other players to page this character",
    )
    allow_tells = models.BooleanField(
        default=True,
        help_text="Allow other players to send tells to this character",
    )

    # Roleplay preferences
    rp_preferences = models.CharField(
        max_length=500,
        blank=True,
        help_text="Freeform RP preferences and notes",
    )
    plot_involvement = models.CharField(
        max_length=20,
        choices=PlotInvolvement.choices,
        default=PlotInvolvement.MEDIUM,
    )

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Display settings for {self.tenure.character.name}"

    class Meta:
        verbose_name = "Tenure Display Settings"
        verbose_name_plural = "Tenure Display Settings"


class TenureGallery(models.Model):
    """Collection of media for a roster tenure."""

    tenure = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.CASCADE,
        related_name="galleries",
    )
    name = models.CharField(max_length=100)
    is_public = models.BooleanField(default=True, help_text="Visible to other players")
    allowed_viewers = models.ManyToManyField(
        "roster.RosterTenure",
        blank=True,
        related_name="shared_galleries",
        help_text="Tenures allowed to view this private gallery",
    )
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.tenure.character.name} - {self.name}"

    class Meta:
        verbose_name = "Tenure Gallery"
        verbose_name_plural = "Tenure Galleries"


class TenureMedia(models.Model):
    """Bridge between player media and character tenures."""

    tenure = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.CASCADE,
        related_name="media",
    )
    media = models.ForeignKey(
        "evennia_extensions.PlayerMedia",
        on_delete=models.CASCADE,
        related_name="tenure_links",
    )
    gallery = models.ForeignKey(
        "roster.TenureGallery",
        on_delete=models.CASCADE,
        related_name="media",
        null=True,
        blank=True,
    )

    # Organization
    sort_order = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        title = self.media.title or "Untitled"
        return f"{self.media.media_type} for {self.tenure.character.name} ({title})"

    class Meta:
        ordering: ClassVar[list[str]] = ["sort_order", "-media__uploaded_date"]
        indexes: ClassVar[list[models.Index]] = [models.Index(fields=["tenure", "sort_order"])]
        verbose_name = "Tenure Media"
        verbose_name_plural = "Tenure Media"
