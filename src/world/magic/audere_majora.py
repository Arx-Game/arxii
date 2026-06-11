"""Audere Majora — Crossing the Threshold (#543). Models + services."""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.classes.models import PathStage
from world.magic.audere import AbstractPendingOffer


class AudereMajoraThreshold(SharedMemoryModel):
    """Configuration for a tier-crossing boundary level.

    One row per boundary level (5, 10, 15, 20). Authored by staff in the DB.
    Ceremony text is spoiler-private and never appears in code.
    """

    boundary_level = models.PositiveSmallIntegerField(
        unique=True,
        help_text="Character level the gate opens at (5, 10, 15, 20).",
    )
    target_stage = models.PositiveSmallIntegerField(
        choices=PathStage.choices,
    )
    minimum_intensity_tier = models.ForeignKey(
        "magic.IntensityTier",
        on_delete=models.PROTECT,
        related_name="+",
    )
    minimum_warp_stage = models.ForeignKey(
        "conditions.ConditionStage",
        on_delete=models.PROTECT,
        related_name="+",
    )
    requires_active_audere = models.BooleanField(default=True)
    vision_text = models.TextField(
        help_text="Shown ONLY to the crossing player. Authored in DB; spoiler-private.",
    )
    manifestation_text = models.TextField(
        help_text="Broadcast to the room when the offer fires. Authored in DB.",
    )

    class Meta:
        ordering = ["boundary_level"]
        verbose_name = "Audere Majora Threshold"
        verbose_name_plural = "Audere Majora Thresholds"

    def __str__(self) -> str:
        return f"Crossing at level {self.boundary_level} → {self.get_target_stage_display()}"


class PendingAudereMajoraOffer(AbstractPendingOffer):
    """A poll-able Audere Majora offer awaiting the player's response (#543).

    Created when the crossing gate opens during a qualifying cast.
    One offer per character at a time (unique constraint).
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="audere_majora_offers",
    )
    threshold = models.ForeignKey(
        AudereMajoraThreshold,
        on_delete=models.PROTECT,
        related_name="pending_offers",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet"],
                name="one_pending_audere_majora_per_character",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"PendingAudereMajoraOffer(sheet={self.character_sheet_id}, "
            f"threshold={self.threshold_id})"
        )


class AudereMajoraCrossing(SharedMemoryModel):
    """Irreversible receipt: this character crossed this threshold. Survives death."""

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="audere_majora_crossings",
    )
    threshold = models.ForeignKey(
        AudereMajoraThreshold,
        on_delete=models.PROTECT,
        related_name="crossings",
    )
    # NOT named "path": Evennia's idmapper metaclass shadows a `path` attribute.
    chosen_path = models.ForeignKey(
        "classes.Path",
        on_delete=models.PROTECT,
        related_name="audere_majora_crossings",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    declaration_interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_constraint=False,
        # db_constraint=False: scenes_interaction is partitioned by timestamp.
        help_text="The declaration pose. Soft FK — partitioned table.",
    )
    level_before = models.PositiveSmallIntegerField()
    level_after = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "threshold"],
                name="one_crossing_per_character_per_threshold",
            ),
        ]
        verbose_name = "Audere Majora Crossing"
        verbose_name_plural = "Audere Majora Crossings"

    def __str__(self) -> str:
        return (
            f"AudereMajoraCrossing(sheet={self.character_sheet_id}, "
            f"threshold={self.threshold_id}, "
            f"level {self.level_before}→{self.level_after})"
        )
