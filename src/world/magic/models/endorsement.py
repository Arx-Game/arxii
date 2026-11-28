"""Pose + scene-entry endorsement models (Spec C §2.2, §2.3)."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from evennia_extensions.mixins import RelatedCacheClearingMixin

CHARACTER_SHEET_FK = "arxii.CharacterSheet"
RESONANCE_FK = "arxii.Resonance"
SCENE_FK = "arxii.Scene"


class EndorsementBase(SharedMemoryModel):
    """Shared identity fields for peer-endorsement records (#514).

    Abstract base for the endorsement siblings (``PoseEndorsement``,
    ``SceneEntryEndorsement``, and the fashion ``PresentationEndorsement``).
    Concrete subclasses keep their own kind-specific fields, ``Meta``
    constraints/indexes, and ``__str__``. Reverse accessors resolve to
    ``<classname>_given`` / ``<classname>_received`` via ``%(class)s``.
    """

    endorser_sheet = models.ForeignKey(
        CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="%(class)s_given",
    )
    endorsee_sheet = models.ForeignKey(
        CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="%(class)s_received",
    )
    persona_snapshot = models.ForeignKey(
        "arxii.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Endorsee's persona at endorsement time — masquerade audit.",
    )
    endorser_persona = models.ForeignKey(
        "arxii.Persona",
        # RESTRICT, not SET_NULL: a null here reads as "made before it was recorded" and the
        # badge falls back to the endorser's real face, so deleting a mask must be refused
        # like it is once the mask has posted (Interaction.persona is PROTECT). RESTRICT, not
        # PROTECT, so deleting the endorser's character still cascades through.
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="%(class)s_endorsed_as",
        help_text=(
            "The face the endorser presented when they endorsed (a mask stays a mask once "
            "they unmask). Null only for rows made before it was recorded. A worn look "
            "changes the picture, which is read live as on poses, not the face."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        abstract = True


class PoseEndorsement(RelatedCacheClearingMixin, EndorsementBase):
    """Unsettled endorsement of a pose. Settled at weekly tick (Spec C §4).

    The ``interaction`` FK uses ``db_constraint=False`` because ``Interaction``
    is partitioned by timestamp — partitioned tables don't support plain
    incoming FK constraints. The denormalized ``timestamp`` field is required
    for composite-FK use and matches the pattern used by InteractionReceiver.
    """

    related_cache_fields: ClassVar[list[str]] = ["interaction"]
    #: interaction is required (no null=True) and never reassigned after
    #: creation, and Interaction.cached_endorsements filters solely via the
    #: interaction FK (self.endorsements) -- safe to skip the clear on a
    #: field-only settled_at/granted_amount/awaiting_acceptance/resonance update:
    #: the cached list holds these same idmapper instances, so a changed field
    #: reads through, and only a row joining or leaving the list needs the clear
    #: (#3816 final review, #5327; see the flag's docstring on the mixin).
    skip_related_cache_clear_when_fk_unchanged: ClassVar[bool] = True

    interaction = models.ForeignKey(
        "arxii.Interaction",
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
        RESONANCE_FK,
        on_delete=models.PROTECT,
    )
    settled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    granted_amount = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Set at weekly settlement.",
    )
    awaiting_acceptance = models.BooleanField(
        default=False,
        db_default=False,
        help_text=(
            "True while a witness's proposed resonance waits for the poser or a GM to accept "
            "it. Settlement skips these rows."
        ),
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


class PoseResonanceReach(RelatedCacheClearingMixin, SharedMemoryModel):
    """The resonance a pose reached for, named by its author when they posed (#5308).

    A pose carries at most one. An endorsement of a reached pose gives that resonance, so
    the endorser no longer picks one, and the endorsee need not have claimed it. Written
    once with the pose, never changed.

    The ``interaction`` FK uses ``db_constraint=False`` for the same reason as
    ``PoseEndorsement``: ``Interaction`` is partitioned by timestamp.
    """

    related_cache_fields: ClassVar[list[str]] = ["interaction"]

    interaction = models.ForeignKey(
        "arxii.Interaction",
        on_delete=models.CASCADE,
        related_name="resonance_reaches",
        db_constraint=False,
        help_text="The pose that reached for this resonance.",
    )
    resonance = models.ForeignKey(
        RESONANCE_FK,
        on_delete=models.PROTECT,
        related_name="pose_reaches",
        help_text="The resonance the pose reached for.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction"],
                name="unique_pose_resonance_reach_per_pose",
            ),
        ]

    def __str__(self) -> str:
        return f"PoseResonanceReach({self.interaction_id}->{self.resonance_id})"


class SceneEntryEndorsement(EndorsementBase):
    """Scene-entry endorsement — immediate flat grant (Spec C §2.3).

    Fired at creation time — no weekly settlement. One per (endorser,
    endorsee, scene) pair. ``entry_interaction`` FK is nullable (SET_NULL)
    for resilience against interaction cleanup, and uses
    ``db_constraint=False`` because Interaction is partitioned by timestamp.
    """

    scene = models.ForeignKey(
        SCENE_FK,
        on_delete=models.CASCADE,
        related_name="entry_endorsements",
    )
    entry_interaction = models.ForeignKey(
        "arxii.Interaction",
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
        RESONANCE_FK,
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
        "arxii.FashionPresentation",
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


class StylePresentationEndorsement(EndorsementBase):
    """Scene-level endorsement of a character's style presentation (#1152).

    Grants resonance immediately at creation, one per (endorser, endorsee, scene)
    pair. Mirrors ``SceneEntryEndorsement`` but fires on style evaluation rather
    than scene entry.
    """

    scene = models.ForeignKey(
        SCENE_FK,
        on_delete=models.CASCADE,
        related_name="style_presentation_endorsements",
    )
    resonance = models.ForeignKey(
        RESONANCE_FK,
        on_delete=models.PROTECT,
    )
    granted_amount = models.PositiveIntegerField(
        help_text="Captured from config at creation.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["endorser_sheet", "endorsee_sheet", "scene"],
                name="unique_style_presentation_per_pair_per_scene",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"StylePresentationEndorsement("
            f"{self.endorser_sheet_id}->{self.endorsee_sheet_id}"
            f"@{self.scene_id})"
        )


class EntryFlourishRecord(SharedMemoryModel):
    """Actor-side record of a successful entry flourish (Entrance action).

    Written when a character successfully performs the Entrance social action
    with a declared resonance. No peer endorser — the resonance grant is
    actor-initiated and immediately applied (unlike PoseEndorsement which
    requires a peer and settles weekly).
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="entry_flourish_records",
    )
    resonance = models.ForeignKey(
        RESONANCE_FK,
        on_delete=models.PROTECT,
        related_name="entry_flourish_records",
    )
    scene = models.ForeignKey(
        SCENE_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entry_flourish_records",
        help_text="Scene context for the flourish; nullable if performed outside a scene.",
    )
    granted_amount = models.PositiveIntegerField(
        help_text="Resonance granted; captured from ResonanceGainConfig at creation time.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["character_sheet", "created_at"],
                name="entry_flourish_sheet_time_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "scene"],
                condition=models.Q(scene__isnull=False),
                name="one_entry_flourish_per_sheet_scene",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"EntryFlourishRecord("
            f"{self.character_sheet_id} +{self.granted_amount} {self.resonance_id})"
        )
