from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.boundaries.constants import BoundaryKind, TreasuredSubjectKind
from world.consent.models import VisibilityMixin


class ContentTheme(NaturalKeyMixin, SharedMemoryModel):
    """A coarse, staff-authored content category used for automatic hard-line
    matching (mirror of SocialConsentCategory). Tagged onto sensitive
    StakeTemplates; players pick hard lines from the same catalog."""

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["key"]

    key = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Content Theme"
        verbose_name_plural = "Content Themes"

    def __str__(self) -> str:
        return self.name


class PlayerBoundary(VisibilityMixin, SharedMemoryModel):
    """An OOC-player content boundary. Owned by PlayerData so it persists
    across every character the person plays."""

    owner = models.ForeignKey(
        "evennia_extensions.PlayerData",
        on_delete=models.CASCADE,
        related_name="content_boundaries",
    )
    kind = models.CharField(max_length=20, choices=BoundaryKind.choices)
    theme = models.ForeignKey(
        ContentTheme,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="player_boundaries",
        help_text="Required for HARD_LINE (the machine-matched category); optional for ADVISORY.",
    )
    detail = models.TextField(
        blank=True,
        help_text="Free-text nuance. For HARD_LINE this is staff/audit-only and never surfaced.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "theme"],
                condition=models.Q(kind="hard_line"),
                name="uniq_hard_line_per_owner_theme",
            )
        ]
        ordering = ["owner", "kind", "theme"]
        verbose_name = "Player Boundary"
        verbose_name_plural = "Player boundaries"

    def clean(self) -> None:
        super().clean()
        if self.kind == BoundaryKind.HARD_LINE:
            if self.theme_id is None:
                raise ValidationError({"theme": "A hard line must name a content theme."})
            if self.visibility_mode != self.VisibilityMode.PRIVATE:
                raise ValidationError(
                    {"visibility_mode": "Hard lines are always private and cannot be shared."}
                )

    def __str__(self) -> str:
        return f"{self.owner}: {self.get_kind_display()} ({self.theme or 'advisory'})"


class TreasuredSubject(VisibilityMixin, SharedMemoryModel):
    """A specific entity a player flags as devastating-if-lost. Owned by the
    RosterTenure (the character-instance whose attachment it is). Typed subject
    pointers mirror Stake exactly (world/stories/models.py Stake); SET_NULL so a
    consumed subject doesn't erase the flag. subject_kind uses local
    TreasuredSubjectKind values matching StakeSubjectKind verbatim (no stories
    import — ADR-0010 FK direction specific->general)."""

    owner = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.CASCADE,
        related_name="treasured_subjects",
    )
    subject_kind = models.CharField(max_length=20, choices=TreasuredSubjectKind.choices)
    subject_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="treasured_by",
        help_text="For NPC_FATE / PERSONAL_JEOPARDY subjects. Nulls if the sheet is deleted.",
    )
    subject_item = models.ForeignKey(
        "items.ItemInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="For ITEM subjects. Nulls if the item instance is deleted/consumed.",
    )
    subject_society = models.ForeignKey(
        "societies.Society",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="For FACTION subjects (society-level). Nulls if the society is deleted.",
    )
    subject_organization = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="For FACTION subjects (organization-level). Nulls if the org is deleted.",
    )
    subject_label = models.CharField(
        max_length=200,
        blank=True,
        help_text="Freeform subject name (CUSTOM / CAMPAIGN_TRACK / LOCATION, or flavor).",
    )
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["owner", "subject_kind"]
        verbose_name = "Treasured Subject"
        verbose_name_plural = "Treasured Subjects"

    def __str__(self) -> str:
        return f"Treasured({self.get_subject_kind_display()}: {self.subject_label or self.pk})"
