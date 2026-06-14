"""Pose + scene-entry endorsement models (Spec C §2.2, §2.3)."""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel


class EndorsementBase(SharedMemoryModel):
    """Shared identity fields for peer-endorsement records (#514).

    Abstract base for the endorsement siblings (``PoseEndorsement``,
    ``SceneEntryEndorsement``, and the fashion ``PresentationEndorsement``).
    Concrete subclasses keep their own kind-specific fields, ``Meta``
    constraints/indexes, and ``__str__``. Reverse accessors resolve to
    ``<classname>_given`` / ``<classname>_received`` via ``%(class)s``.
    """

    endorser_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="%(class)s_given",
    )
    endorsee_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="%(class)s_received",
    )
    persona_snapshot = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Endorsee's persona at endorsement time — masquerade audit.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        abstract = True


class PoseEndorsement(EndorsementBase):
    """Unsettled endorsement of a pose. Settled at weekly tick (Spec C §4).

    The ``interaction`` FK uses ``db_constraint=False`` because ``Interaction``
    is partitioned by timestamp — partitioned tables don't support plain
    incoming FK constraints. The denormalized ``timestamp`` field is required
    for composite-FK use and matches the pattern used by InteractionReceiver.
    """

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


class SceneEntryEndorsement(EndorsementBase):
    """Scene-entry endorsement — immediate flat grant (Spec C §2.3).

    Fired at creation time — no weekly settlement. One per (endorser,
    endorsee, scene) pair. ``entry_interaction`` FK is nullable (SET_NULL)
    for resilience against interaction cleanup, and uses
    ``db_constraint=False`` because Interaction is partitioned by timestamp.
    """

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
    granted_amount = models.PositiveIntegerField(
        help_text="Captured from config at creation.",
    )

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


class PresentationEndorsement(EndorsementBase):
    """A peer judging a fashion presentation (#514).

    Carries no resonance grant; it feeds the presentation's acclaim
    (heavily weighted) via the fashion-presentation service.
    """

    presentation = models.ForeignKey(
        "items.FashionPresentation",
        on_delete=models.CASCADE,
        related_name="endorsements",
    )
    weight = models.PositiveSmallIntegerField(
        default=1,
        help_text="Per-judge weight (reserved for taste-authority scaling).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["endorser_sheet", "presentation"],
                name="unique_presentation_endorsement_per_judge",
            ),
        ]

    def __str__(self) -> str:
        return f"PresentationEndorsement({self.endorser_sheet_id}->{self.presentation_id})"
