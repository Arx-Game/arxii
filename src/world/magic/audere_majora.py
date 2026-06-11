"""Audere Majora — Crossing the Threshold (#543). Models + services."""

from __future__ import annotations

from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.classes.models import PathStage
from world.magic.audere import (
    AUDERE_CONDITION_NAME,
    SOULFRAY_CONDITION_NAME,
    AbstractPendingOffer,
    _check_intensity_gate,
    _check_soulfray_gate,
)


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
        help_text="PathStage the character crosses into.",
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
    requires_active_audere = models.BooleanField(
        default=True,
        help_text="When False, an active Audere condition is not required for the gate to open.",
    )
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
        verbose_name = "Pending Audere Majora Offer"
        verbose_name_plural = "Pending Audere Majora Offers"
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
    level_before = models.PositiveSmallIntegerField(
        help_text="Character level immediately before the crossing.",
    )
    level_after = models.PositiveSmallIntegerField(
        help_text="Character level granted by the crossing.",
    )
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


# =============================================================================
# Services
# =============================================================================


def _has_crossed(sheet, threshold: AudereMajoraThreshold) -> bool:
    """Return True if the character already has a completed crossing for this threshold."""
    return AudereMajoraCrossing.objects.filter(character_sheet=sheet, threshold=threshold).exists()


def _has_active_condition(character: ObjectDB, condition_name: str) -> bool:
    """Return True if the character has an active ConditionInstance for the named condition."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    return ConditionInstance.objects.filter(
        target=character,
        condition__name=condition_name,
    ).exists()


def current_path_for_character(character: ObjectDB):
    """Return the Path from the latest CharacterPathHistory row, or None."""
    from world.progression.models import CharacterPathHistory  # noqa: PLC0415

    history = (
        CharacterPathHistory.objects.filter(character=character)
        .select_related("path")
        .order_by("-selected_at")
        .first()
    )
    if history is None:
        return None
    return history.path


def eligible_paths_for_threshold(character: ObjectDB, threshold: AudereMajoraThreshold) -> list:
    """Return active child paths at the threshold's target stage reachable from the current path.

    Returns an empty list when the character has no path history or no valid child paths.
    """
    path = current_path_for_character(character)
    if path is None:
        return []
    return list(path.child_paths.filter(stage=threshold.target_stage, is_active=True))


def check_audere_majora_eligibility(  # noqa: PLR0911
    character: ObjectDB, runtime_intensity: int
) -> AudereMajoraThreshold | None:
    """Check all gates for the Audere Majora offer.

    Gates in order:
    1. Character has a CharacterSheet.
    2. A threshold exists at boundary_level == sheet.current_level.
    3. Character has NOT already crossed this threshold.
    4. Runtime intensity resolves to a tier at or above threshold.minimum_intensity_tier.
    5. Character has Soulfray at or above threshold.minimum_warp_stage.
    6. Character has an active CharacterEngagement.
    7. If threshold.requires_active_audere, character has the Audere condition.
    8. At least one eligible child path exists.

    Returns the threshold on success, None if any gate fails.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415

    sheet = CharacterSheet.objects.filter(character=character).first()
    if sheet is None:
        return None

    threshold = AudereMajoraThreshold.objects.filter(boundary_level=sheet.current_level).first()
    if threshold is None:
        return None

    if _has_crossed(sheet, threshold):
        return None

    if not _check_intensity_gate(runtime_intensity, threshold.minimum_intensity_tier.threshold):
        return None

    if not _check_soulfray_gate(character, threshold.minimum_warp_stage.stage_order):
        return None

    if not CharacterEngagement.objects.filter(character=character).exists():
        return None

    if threshold.requires_active_audere and not _has_active_condition(
        character, AUDERE_CONDITION_NAME
    ):
        return None

    if not eligible_paths_for_threshold(character, threshold):
        return None

    return threshold


def _broadcast_manifestation(character: ObjectDB, text: str) -> None:
    """Broadcast the threshold manifestation text as an EMIT to the active scene.

    No-ops silently when: no active scene at location, or character has no primary persona.
    """
    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        create_interaction,
        push_interaction,
    )
    from world.scenes.models import Persona, Scene  # noqa: PLC0415

    scene = Scene.objects.filter(location=character.location, is_active=True).first()
    if scene is None:
        return

    try:
        # sheet_data is CharacterSheet's OneToOne reverse accessor (models.py:98).
        persona = character.sheet_data.primary_persona
    except (AttributeError, Persona.DoesNotExist):
        # AttributeError covers a missing sheet (plain ObjectDB); DoesNotExist
        # a sheet with no PRIMARY persona (intentionally loud).
        return

    interaction = create_interaction(
        persona=persona,
        content=text,
        mode=InteractionMode.EMIT,
        scene=scene,
    )
    push_interaction(
        interaction,
        receiver_persona_ids=[],
        target_persona_ids=[],
        receiver_characters=[],
    )


def maybe_create_audere_majora_offer(
    character: ObjectDB, runtime_intensity: int
) -> PendingAudereMajoraOffer | None:
    """Persist a poll-able Audere Majora offer when the crossing gate opens for this cast.

    Returns None for NPCs without a CharacterSheet or when any eligibility gate fails.
    Idempotent: repeated qualifying casts update the single row (update_or_create).
    Broadcast fires only on first creation; re-fires after decline broadcast again;
    refreshes from a still-open gate stay silent.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    threshold = check_audere_majora_eligibility(character, runtime_intensity)
    if threshold is None:
        return None

    # Sheet/Soulfray re-fetches duplicate eligibility's reads, mirroring
    # maybe_create_audere_offer's shape. This path runs only at boundary
    # levels with every gate open; the identity map serves the sheet.
    sheet = CharacterSheet.objects.filter(character=character).first()
    if sheet is None:
        return None

    soulfray_instance = (
        ConditionInstance.objects.filter(
            target=character,
            condition__name=SOULFRAY_CONDITION_NAME,
        )
        .select_related("current_stage")
        .first()
    )
    stage_order = 0
    if soulfray_instance is not None and soulfray_instance.current_stage is not None:
        stage_order = soulfray_instance.current_stage.stage_order

    offer, created = PendingAudereMajoraOffer.objects.update_or_create(
        character_sheet=sheet,
        defaults={
            "threshold": threshold,
            "fired_intensity": runtime_intensity,
            "soulfray_stage_order": stage_order,
        },
    )

    if created:
        _broadcast_manifestation(character, threshold.manifestation_text)

    return offer
