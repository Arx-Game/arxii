"""SceneActionRequest model for social action checks within scenes."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.models.commitments import CommittingDeclaration
from world.scenes.action_constants import ActionRequestStatus, DifficultyChoice


class SceneActionRequest(CommittingDeclaration, SharedMemoryModel):
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
        null=True,
        blank=True,
        related_name="received_action_requests",
        help_text="The persona being targeted (null for standalone technique casts)",
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
    # Snapshot fields for ritual check specs (nullable, fired-action audit only)
    snapshot_ritual = models.ForeignKey(
        "magic.Ritual",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Ritual that fired this action (snapshot audit field)",
    )
    snapshot_stat = models.ForeignKey(
        "traits.Trait",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Primary stat from ritual check spec at fire time",
    )
    snapshot_skill = models.ForeignKey(
        "skills.Skill",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Skill from ritual check spec at fire time",
    )
    snapshot_specialization = models.ForeignKey(
        "skills.Specialization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional specialization from ritual check spec at fire time",
    )
    snapshot_resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional resonance filter from ritual check spec at fire time",
    )
    snapshot_check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="CheckType from ritual check spec at fire time",
    )
    snapshot_target_difficulty = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Target difficulty from ritual check spec at fire time",
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
        target = self.target_persona.name if self.target_persona_id else "(no target)"
        action = self.action_key or "template"
        return f"{self.initiator_persona.name} -> {target}: {action} ({self.get_status_display()})"

    def clean(self) -> None:
        super().clean()
        if not self.action_key and not self.action_template_id and not self.technique_id:
            msg = "A request needs one of: action_key, action_template, or technique."
            raise ValidationError(msg)

    @property
    def is_standalone_cast(self) -> bool:
        """A technique cast with no enhanced base action (derived, not stored)."""
        return bool(self.technique_id) and not self.action_template_id and not self.action_key
