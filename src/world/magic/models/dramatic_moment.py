"""DramaticMomentType and DramaticMomentTag — staff-tagged dramatic scene moments (#545).

Also DramaticMomentSuggestion — a GM-facing recognition bridge (#2183): a high-success
technique-entrance cast surfaces a PENDING suggestion for a flagged DramaticMomentType
instead of auto-tagging, so a GM still confirms/dismisses before resonance + renown fire.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import SuggestionStatus
from world.societies.renown_config import RenownAwardConfig


class DramaticMomentType(RenownAwardConfig):
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
    per_scene_cap = models.PositiveIntegerField(
        default=1,
        help_text=(
            "Maximum number of times this moment type may be awarded to a given "
            "character within a single scene."
        ),
    )
    # magnitude / risk / reach / archetypes now inherited from RenownAwardConfig.
    suggest_on_technique_entrance = models.BooleanField(
        default=False,
        help_text=(
            "When set, a high-success technique-entrance cast surfaces a PENDING "
            "DramaticMomentSuggestion for this type instead of nothing (#2183)."
        ),
    )
    suggestion_min_success_level = models.PositiveSmallIntegerField(
        default=3,
        help_text="Minimum cast success level required to surface a suggestion of this type.",
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
    interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dramatic_moment_tags",
        db_constraint=False,  # scenes_interaction is partitioned (composite PK)
        help_text="The pose that earned this moment; nullable for non-pose tags.",
    )
    interaction_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Denormalized from interaction.timestamp for the partitioned-table composite FK.",
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


class DramaticMomentSuggestion(SharedMemoryModel):
    """GM-facing PENDING suggestion surfaced by a high-success technique entrance (#2183).

    Bridges the technique-entrance deferral markers (originated_as_entrance /
    from_entrance, built in Tasks 1-2) to the existing DramaticMomentTag machinery:
    rather than auto-tagging, a qualifying cast creates a suggestion here that a GM
    later confirms (minting a real DramaticMomentTag via ``create_dramatic_moment_tag``)
    or dismisses. Nothing calls the surfacing/resolution services yet — see
    ``services/gain.py``'s ``maybe_suggest_dramatic_moments`` /
    ``resolve_dramatic_moment_suggestion``.
    """

    moment_type = models.ForeignKey(
        DramaticMomentType,
        on_delete=models.PROTECT,
        related_name="suggestions",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="dramatic_moment_suggestions",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dramatic_moment_suggestions",
        help_text="Scene context; nullable for resilience to scene cleanup.",
    )
    interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dramatic_moment_suggestions",
        db_constraint=False,  # scenes_interaction is partitioned (composite PK)
        help_text="The entrance pose that triggered this suggestion; nullable.",
    )
    interaction_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Denormalized from interaction.timestamp for the partitioned-table composite FK.",
    )
    success_level = models.PositiveSmallIntegerField(
        help_text="Cast success level that triggered this suggestion.",
    )
    status = models.CharField(
        max_length=20,
        choices=SuggestionStatus.choices,
        default=SuggestionStatus.PENDING,
        db_index=True,
    )
    resolved_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dramatic_moment_suggestions_resolved",
        help_text="GM account that confirmed or dismissed this suggestion.",
    )
    confirmed_tag = models.OneToOneField(
        DramaticMomentTag,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_suggestion",
        help_text="The DramaticMomentTag minted on confirmation, if any.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["moment_type", "character_sheet", "scene"],
                condition=Q(status="pending"),
                name="one_pending_suggestion_per_type_sheet_scene",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"DramaticMomentSuggestion({self.character_sheet_id} ← "
            f"{self.moment_type_id}, {self.status})"
        )
