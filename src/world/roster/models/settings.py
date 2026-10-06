"""
Settings and media models for roster tenures.
"""

from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel

from .choices import PlotInvolvement

_ROSTER_TENURE_FK = "arxii.RosterTenure"


class TenureDisplaySettings(SharedMemoryModel):
    """
    Character-specific UI and display settings tied to a tenure.
    Each setting gets its own column for proper indexing and validation.
    """

    tenure = models.OneToOneField(
        _ROSTER_TENURE_FK,
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
    appear_offline = models.BooleanField(
        default=False,
        help_text=(
            "Quiet/hidden mode (#1463): hide from where/who and be unpageable, EXCEPT to people "
            "on this player's allowlist. Async (mail/mission/channels) and same-room presence are "
            "unaffected. Persists across logins."
        ),
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


class TenureMedia(SharedMemoryModel):
    """One picture in a character's gallery: a file, and this character's use of it.

    A picture belongs to exactly one of two owners (#4151). A player's own upload hangs
    off their ``tenure`` and leaves with them when the character changes hands. Character
    art hangs off the ``roster_entry`` itself: staff-commissioned art that every player of
    the character starts with, counts against nobody's quota (the quota counts the
    uploader's files, and staff are exempt) and that a player can hide but not delete.

    A picture with a crop is a **look**: the crop is the 4:5 frame the plate, the looks
    strip and every portrait chip show. Its height is not stored; it is always
    ``crop_width * 5 / 4``.
    """

    tenure = models.ForeignKey(
        _ROSTER_TENURE_FK,
        on_delete=models.CASCADE,
        related_name="media",
        null=True,
        blank=True,
        help_text="The player's tenure, for their own upload. Null for character art.",
    )
    roster_entry = models.ForeignKey(
        "arxii.RosterEntry",
        on_delete=models.CASCADE,
        related_name="character_art",
        null=True,
        blank=True,
        help_text="The character, for character art (#4151). Null for a player's upload.",
    )
    media = models.ForeignKey(
        "arxii.Media",
        on_delete=models.CASCADE,
        related_name="tenure_links",
    )
    # #4151: the look's frame, in the file's own pixels. All three or none.
    crop_x = models.PositiveIntegerField(null=True, blank=True)
    crop_y = models.PositiveIntegerField(null=True, blank=True)
    crop_width = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Width of the 4:5 crop; set only on a look. Height is width x 5/4.",
    )
    # #3898 — which face of the character this image shows, so the sheet's plate can
    # wear the look that matches the mood and offer the rest as a strip. The tag hangs
    # on the tenure link rather than on Media because it describes this character's use
    # of the image, not the file: the same commissioned piece may be one character's
    # "guarded" and appear untagged in another's gallery.
    #
    # Shares MoodOption with CharacterSheet.current_mood deliberately — one vocabulary
    # for "which mood", so a declared mood can name an image without a second enum to
    # keep in step. Tagging an image does NOT leak the character's declared mood
    # (#2994 keeps that internal): this says what the picture shows, not what they feel.
    look = models.ForeignKey(
        "arxii.MoodOption",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tagged_media",
        help_text="The mood this image shows (#3898); blank for an untagged image.",
    )

    # Organization
    sort_order = models.PositiveIntegerField(default=0)

    @property
    def is_look(self) -> bool:
        """A picture with a crop is a look."""
        return self.crop_width is not None

    @property
    def is_character_art(self) -> bool:
        """Belongs to the character rather than to one player's tenure."""
        return self.roster_entry_id is not None

    @property
    def crop_height(self) -> int | None:
        """The 4:5 crop's height, derived from its width."""
        if self.crop_width is None:
            return None
        return round(self.crop_width * 5 / 4)

    def owning_entry_id(self) -> int | None:
        """The roster entry this picture shows, whichever owner it hangs off."""
        if self.roster_entry_id is not None:
            return self.roster_entry_id
        return self.tenure.roster_entry_id if self.tenure_id is not None else None

    def __str__(self) -> str:
        title = self.media.title or "Untitled"
        owner = f"entry {self.roster_entry_id}" if self.is_character_art else str(self.tenure)
        return f"{self.media.media_type} for {owner} ({title})"

    class Meta:
        ordering: ClassVar[list[str]] = ["sort_order", "-media__uploaded_date"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["tenure", "sort_order"]),
            models.Index(fields=["roster_entry", "sort_order"]),
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.CheckConstraint(
                name="tenuremedia_one_owner",
                condition=(
                    models.Q(tenure__isnull=False, roster_entry__isnull=True)
                    | models.Q(tenure__isnull=True, roster_entry__isnull=False)
                ),
            ),
            models.CheckConstraint(
                name="tenuremedia_crop_all_or_none",
                condition=(
                    models.Q(crop_x__isnull=True, crop_y__isnull=True, crop_width__isnull=True)
                    | models.Q(
                        crop_x__isnull=False,
                        crop_y__isnull=False,
                        crop_width__gt=0,
                    )
                ),
            ),
        ]
        verbose_name = "Tenure Media"
        verbose_name_plural = "Tenure Media"


class HiddenCharacterArt(SharedMemoryModel):
    """One player's tenure has hidden one piece of character art (#4151).

    Hiding is the player's choice for their own time on the character, so it is keyed by
    the tenure, not stored on the picture: the next player starts with the art visible.
    The player still sees hidden art (dimmed, to show it again); nobody else does, and it
    cannot be worn.
    """

    tenure = models.ForeignKey(
        _ROSTER_TENURE_FK,
        on_delete=models.CASCADE,
        related_name="hidden_character_art",
    )
    picture = models.ForeignKey(
        TenureMedia,
        on_delete=models.CASCADE,
        related_name="hidden_by",
    )

    def clean(self) -> None:
        super().clean()
        if not self.picture.is_character_art:
            raise ValidationError({"picture": "Only character art can be hidden."})
        if self.picture.roster_entry_id != self.tenure.roster_entry_id:
            raise ValidationError({"picture": "This art belongs to another character."})

    def __str__(self) -> str:
        return f"{self.tenure} hides picture {self.picture_id}"

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["tenure", "picture"], name="hidden_art_once"),
        ]
        verbose_name = "Hidden Character Art"
        verbose_name_plural = "Hidden Character Art"
