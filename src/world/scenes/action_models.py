"""SceneActionRequest model for social action checks within scenes."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.scenes.action_constants import ActionRequestStatus, DifficultyChoice


class SceneActionRequest(SharedMemoryModel):
    """A request to perform a social action against another character in a scene.

    Represents the full lifecycle of a contested social action: request,
    consent, resolution, and result recording.
    """

    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.CASCADE,
        related_name="action_requests",
        help_text="The scene where this action takes place",
    )
    initiator_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="initiated_action_requests",
        help_text="The persona performing the action",
    )
    target_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="received_action_requests",
        help_text="The persona being targeted",
    )
    action_template = models.ForeignKey(
        "actions.ActionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scene_action_requests",
        help_text="Data-driven action template if applicable",
    )
    action_key = models.CharField(
        max_length=100,
        blank=True,
        help_text="Key identifying the action type (e.g., 'intimidate', 'persuade')",
    )
    technique = models.ForeignKey(
        "magic.Technique",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scene_action_requests",
        help_text="Technique used for this action, if any",
    )
    status = models.CharField(
        max_length=20,
        choices=ActionRequestStatus.choices,
        default=ActionRequestStatus.PENDING,
        db_index=True,
    )
    difficulty_choice = models.CharField(
        max_length=20,
        choices=DifficultyChoice.choices,
        default=DifficultyChoice.NORMAL,
        help_text="Difficulty level chosen or determined for this action",
    )
    resolved_difficulty = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="The numeric difficulty used for resolution",
    )
    result_interaction = models.OneToOneField(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="action_request_result",
        help_text="The interaction recording the result of this action",
    )
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this action was resolved",
    )

    class Meta:
        indexes = [
            models.Index(fields=["scene", "status"]),
            models.Index(fields=["initiator_persona", "created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.initiator_persona.name} -> {self.target_persona.name}: "
            f"{self.action_key or 'template'} ({self.get_status_display()})"
        )

    def clean(self) -> None:
        super().clean()
        if not self.action_key and not self.action_template_id:
            msg = "Either action_key or action_template must be set."
            raise ValidationError(msg)
