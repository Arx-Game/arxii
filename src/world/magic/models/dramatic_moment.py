"""DramaticMomentType and DramaticMomentTag — staff-tagged dramatic scene moments (#545)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.societies.constants import RenownMagnitude, RenownReach, RenownRisk


class DramaticMomentType(SharedMemoryModel):
    """Staff-authored lookup describing a type of dramatic moment.

    Staff tags a character in a scene with a DramaticMomentType to fire both
    a resonance grant and a renown award in one atomic service call.
    """

    label = models.CharField(
        max_length=100,
        unique=True,
        help_text="Display name used as the renown deed title (e.g. 'Grand Entrance').",
    )
    description = models.TextField(blank=True)
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="dramatic_moment_types",
        help_text="Resonance granted when this moment type is tagged.",
    )
    resonance_amount = models.PositiveIntegerField(
        default=15,
        help_text="Flat resonance units granted to the tagged character.",
    )
    magnitude = models.CharField(
        max_length=20,
        choices=RenownMagnitude.choices,
        default=RenownMagnitude.SMALL,
        help_text="Renown magnitude passed to fire_renown_award.",
    )
    risk = models.CharField(
        max_length=20,
        choices=RenownRisk.choices,
        default=RenownRisk.NONE,
        help_text="Risk level for legend award; NONE means no legend granted.",
    )
    reach = models.CharField(
        max_length=20,
        choices=RenownReach.choices,
        null=True,
        blank=True,
        help_text="Override reach; if null, derived from magnitude default.",
    )

    class Meta:
        ordering = ["label"]
        verbose_name = "Dramatic Moment Type"
        verbose_name_plural = "Dramatic Moment Types"

    def __str__(self) -> str:
        return self.label


class DramaticMomentTag(SharedMemoryModel):
    """Record of a staff member tagging a character's dramatic moment in a scene."""

    moment_type = models.ForeignKey(
        DramaticMomentType,
        on_delete=models.PROTECT,
        related_name="tags",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="dramatic_moment_tags",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dramatic_moment_tags",
        help_text="Scene context; nullable for resilience to scene cleanup.",
    )
    tagged_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="dramatic_moment_tags_issued",
        help_text="Account that tagged this moment. PROTECT because provenance must be kept.",
    )
    tagged_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["character_sheet", "tagged_at"],
                name="dramatic_tag_sheet_time_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"DramaticMomentTag({self.character_sheet_id} ← {self.moment_type_id}@{self.tagged_at})"
        )
