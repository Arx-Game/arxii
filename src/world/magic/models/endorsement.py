"""Pose + scene-entry endorsement models (Spec C §2.2, §2.3)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class PoseEndorsement(SharedMemoryModel):
    """Unsettled endorsement of a pose. Settled at weekly tick (Spec C §4).

    The ``interaction`` FK uses ``db_constraint=False`` because ``Interaction``
    is partitioned by timestamp — partitioned tables don't support plain
    incoming FK constraints. The denormalized ``timestamp`` field is required
    for composite-FK use and matches the pattern used by InteractionReceiver.
    """

    endorser_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="pose_endorsements_given",
    )
    endorsee_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="pose_endorsements_received",
    )
    interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.CASCADE,
        related_name="endorsements",
        db_constraint=False,
        help_text="The interaction being endorsed.",
    )
    timestamp = models.DateTimeField(
        help_text="Denormalized from interaction -- required for composite FK "
        "with partitioned table",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
    )
    persona_snapshot = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Endorsee's persona at endorsement time — captures masquerade for audit.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    settled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    granted_amount = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Set at weekly settlement.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["endorser_sheet", "interaction"],
                name="unique_pose_endorsement_per_endorser_per_interaction",
            ),
        ]
        indexes = [
            models.Index(
                fields=["endorser_sheet", "settled_at"],
                name="pose_end_unsettled_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"PoseEndorsement({self.endorser_sheet_id}->{self.endorsee_sheet_id})"


class SceneEntryEndorsement(SharedMemoryModel):
    """Scene-entry endorsement — immediate flat grant (Spec C §2.3).

    Fired at creation time — no weekly settlement. One per (endorser,
    endorsee, scene) pair. ``entry_interaction`` FK is nullable (SET_NULL)
    for resilience against interaction cleanup, and uses
    ``db_constraint=False`` because Interaction is partitioned by timestamp.
    """

    endorser_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="scene_entry_endorsements_given",
    )
    endorsee_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="scene_entry_endorsements_received",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.CASCADE,
        related_name="entry_endorsements",
    )
    entry_interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        help_text=(
            "The ENTRY pose being endorsed; nullable for resilience to interaction cleanup."
        ),
    )
    entry_interaction_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Denormalized from entry_interaction -- required for composite "
        "FK with partitioned table",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
    )
    persona_snapshot = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    granted_amount = models.PositiveIntegerField(
        help_text="Captured from config at creation.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["endorser_sheet", "endorsee_sheet", "scene"],
                name="unique_scene_entry_endorsement_per_pair_per_scene",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"SceneEntryEndorsement("
            f"{self.endorser_sheet_id}->{self.endorsee_sheet_id}"
            f"@{self.scene_id})"
        )
