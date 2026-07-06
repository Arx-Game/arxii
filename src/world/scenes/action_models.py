"""SceneActionRequest model for social action checks within scenes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from evennia.utils.idmapper.models import SharedMemoryModel

from world.fatigue.constants import EffortLevel
from world.magic.models.commitments import CommittingDeclaration
from world.scenes.action_constants import (
    ActionDelivery,
    ActionRequestStatus,
    CastPullTier,
    DifficultyChoice,
)

if TYPE_CHECKING:
    from world.scenes.models import Persona

_PERSONA_MODEL = "scenes.Persona"
_INTERACTION_MODEL = "scenes.Interaction"


class DefenderConsentFields(models.Model):
    """Per-defender consent fields shared by the primary-target request and
    each additional-target row. Difficulty is authored by the DEFENDER at
    consent (not the initiator at dispatch)."""

    difficulty_choice = models.CharField(
        max_length=20,
        choices=DifficultyChoice.choices,
        default=DifficultyChoice.NORMAL,
        help_text="Plausibility band chosen by the defender at consent.",
    )
    resolved_difficulty = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Numeric difficulty used for resolution.",
    )
    resist_effort_level = models.CharField(
        max_length=20,
        choices=EffortLevel.choices,
        blank=True,
        default="",
        help_text="Optional active-resistance effort spent by the defender.",
    )

    class Meta:
        abstract = True


class SceneActionRequest(CommittingDeclaration, DefenderConsentFields, SharedMemoryModel):
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
        _PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="initiated_action_requests",
        help_text="The persona performing the action",
    )
    target_persona = models.ForeignKey(
        _PERSONA_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="received_action_requests",
        help_text=(
            "The persona being targeted. Null for area actions (to the room) "
            "or standalone technique casts."
        ),
    )
    pose_text = models.TextField(
        blank=True,
        help_text="Freeform telling/pose echoed with the outcome (area/social actions).",
    )
    delivery = models.CharField(
        max_length=20,
        choices=ActionDelivery.choices,
        blank=True,
        default="",
        help_text=(
            "Resolved audience routing for the result echo (#903). Blank = "
            "resolve from the template's default_delivery at resolution time."
        ),
    )
    delivery_receivers = models.ManyToManyField(
        _PERSONA_MODEL,
        blank=True,
        related_name="delivery_scoped_action_requests",
        help_text="Explicit WHISPER audience (#903). Empty = the action target alone.",
    )
    target_personas = models.ManyToManyField(
        _PERSONA_MODEL,
        through="SceneActionTarget",
        related_name="+",
        blank=True,
    )
    effort_level = models.CharField(
        max_length=20,
        blank=True,
        default="medium",
        help_text="EffortLevel value — modifies the check and scales social fatigue.",
    )
    spread_deed_target = models.ForeignKey(
        "societies.LegendEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="spread_action_requests",
        help_text="For spread_a_tale: the deed being spread.",
    )
    action_template = models.ForeignKey(
        "actions.ActionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scene_action_requests",
        help_text="Data-driven action template if applicable",
    )
    treatment = models.ForeignKey(
        "conditions.TreatmentTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="action_requests",
        help_text="Treatment being attempted, when the action_key is treat_condition.",
    )
    target_condition_instance = models.ForeignKey(
        "conditions.ConditionInstance",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="treatment_action_requests",
        help_text="Condition instance being treated, when applicable.",
    )
    target_pending_alteration = models.ForeignKey(
        "magic.PendingAlteration",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="treatment_action_requests",
        help_text="Pending alteration being treated, when applicable.",
    )
    thread_used = models.ForeignKey(
        "magic.Thread",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="treatment_action_requests",
        help_text="Bond thread used to pay the cost of a treatment, when required.",
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
    result_interaction = models.OneToOneField(
        _INTERACTION_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="action_request_result",
        help_text="The interaction recording the result of this action",
    )
    action_interaction = models.OneToOneField(
        _INTERACTION_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="action_request_action",
        help_text="ACTION-mode Interaction for this cast (carries the power ledger).",
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
        target = self.target_persona.name if self.target_persona_id else "room"
        action = self.action_key or "template"
        return f"{self.initiator_persona.name} -> {target}: {action} ({self.get_status_display()})"

    def clean(self) -> None:
        super().clean()
        if not self.action_key and not self.action_template_id and not self.technique_id:
            msg = "A request needs one of: action_key, action_template, or technique."
            raise ValidationError(msg)
        if self.treatment_id is not None:
            if (
                self.target_condition_instance_id is None
                and self.target_pending_alteration_id is None
            ):
                raise ValidationError(
                    {
                        "treatment": (
                            "A treatment request must target a condition "
                            "instance or pending alteration."
                        ),
                    }
                )
            if (
                self.target_condition_instance_id is not None
                and self.target_pending_alteration_id is not None
            ):
                raise ValidationError(
                    {
                        "treatment": (
                            "A treatment request may target only one of "
                            "condition instance or pending alteration."
                        ),
                    }
                )

    @property
    def is_standalone_cast(self) -> bool:
        """A technique cast with no enhanced base action (derived, not stored)."""
        return bool(self.technique_id) and not self.action_template_id and not self.action_key

    @property
    def single_target(self) -> Persona | None:
        """The primary target persona (sugar over the denormalized FK)."""
        return self.target_persona


class SceneActionTarget(DefenderConsentFields, SharedMemoryModel):
    """One additional (non-primary) target of a multi-target action request.

    The primary target stays on ``SceneActionRequest.target_persona``; these rows
    carry the additional targets, each with its own consent + result so they
    resolve independently and never block one another.
    """

    action_request = models.ForeignKey(
        "scenes.SceneActionRequest",
        on_delete=models.CASCADE,
        related_name="additional_targets",
    )
    target_persona = models.ForeignKey(
        _PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="action_target_rows",
    )
    status = models.CharField(
        max_length=20,
        choices=ActionRequestStatus.choices,
        default=ActionRequestStatus.PENDING,
        db_index=True,
    )
    result_interaction = models.OneToOneField(
        _INTERACTION_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        # Interaction is partitioned; a FK referencing it cannot use the plain
        # PK on PostgreSQL. Mirror SceneActionRequest's interaction FKs and skip
        # the DB-level constraint (the ORM relation still works).
        db_constraint=False,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["action_request_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["action_request", "target_persona"],
                name="uniq_action_target",
            ),
        ]


class SceneActionPullDeclaration(SharedMemoryModel):
    """A paid thread pull declared alongside a scene action request (#854, #1919).

    Persisted for PENDING benign casts AND social consent actions so the
    declaration survives until consent-resolution. Immediate casts charge
    in-line and need no row; combat pulls live on ``CombatPull`` in the combat
    app.

    For social actions (#1919), the declaration is charged exactly once at
    accept-time via ``_charge_social_pull``; the ``charged_at`` /
    ``charged_flat_bonus`` fields guard against double-charging across
    multi-target resolutions.
    """

    request = models.OneToOneField(
        "scenes.SceneActionRequest",
        on_delete=models.CASCADE,
        related_name="pull_declaration",
        help_text="The action request this pull was declared with.",
    )
    resonance = models.ForeignKey(
        "magic.Resonance",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Resonance committed by the pull (all threads must share it).",
    )
    tier = models.PositiveSmallIntegerField(
        choices=CastPullTier.choices,
        help_text="Paid pull tier (1-3).",
    )
    threads = models.ManyToManyField(
        "magic.Thread",
        related_name="action_pull_declarations",
        help_text="Threads pulled; owned by the actor, sharing ``resonance``.",
    )
    charged_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        help_text="When the pull was first charged at resolution time; guards "
        "against double-charging across multi-target resolutions (#1919).",
    )
    charged_flat_bonus = models.IntegerField(
        null=True,
        blank=True,
        default=None,
        help_text="Cached FLAT_BONUS total from the first charge, returned on "
        "idempotent subsequent calls without re-charging (#1919).",
    )

    def __str__(self) -> str:
        return f"Action pull (tier {self.tier}) for request {self.request_id}"
