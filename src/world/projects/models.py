"""Project framework models.

Project is the runtime model for delayed multi-tick endeavors with outcome rolls.
Per-kind details live in separate models keyed by the kind discriminator (see
e.g. BuildingConstructionDetails in Plan 3).

See: docs/superpowers/specs/2026-05-30-projects-buildings-sanctum-design.md
(subsystem A — Project Framework).
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.projects.constants import (
    CompletionMode,
    ContributionKind,
    ContributionPrivacy,
    ProjectKind,
    ProjectStatus,
)


class Project(SharedMemoryModel):
    """A delayed multi-tick endeavor with contributions and an outcome roll.

    Each Project belongs to one ProjectKind. Per-kind details (e.g.,
    BuildingConstructionDetails) live in a separate model with a OneToOne FK
    back to this Project — see Plan 3.

    Lifecycle (cron-driven, see services.scan_active_projects):
      PLANNING -> ACTIVE -> RESOLVING -> (COMPLETED | FAILED | CANCELLED)
    """

    kind = models.CharField(
        max_length=40,
        choices=ProjectKind.choices,
        help_text="Discriminator selecting which per-kind details model applies.",
    )
    completion_mode = models.CharField(
        max_length=20,
        choices=CompletionMode.choices,
        help_text=(
            "SINGLE_THRESHOLD: completes on progress>=threshold OR now>=time_limit. "
            "TIERED_PERIOD: completes only at time_limit; tier by progress."
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.PLANNING,
    )

    owner_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="projects_owned",
        help_text=(
            "The persona who initiated the project (weighted-check source at "
            "resolution). Resolved from account.active_persona at creation if "
            "triggered from an account-level action like permit activation."
        ),
    )

    started_at = models.DateTimeField()
    time_limit = models.DateTimeField()
    threshold_target = models.PositiveIntegerField(null=True, blank=True)
    current_progress = models.PositiveIntegerField(default=0)

    outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_outcomes",
        help_text=("Set at resolution. CheckOutcome row indicating tier via success_level."),
    )

    resonance = models.ForeignKey(
        "magic.Resonance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects",
    )

    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "time_limit"]),
            models.Index(fields=["kind"]),
        ]

    def __str__(self) -> str:
        return f"Project<{self.kind}>(#{self.pk}, {self.status})"

    def clean(self) -> None:
        super().clean()
        if (
            self.completion_mode == CompletionMode.SINGLE_THRESHOLD
            and self.threshold_target is None
        ):
            msg = "SINGLE_THRESHOLD projects require threshold_target."
            raise ValidationError({"threshold_target": msg})
        if self.time_limit is None:
            msg = "All projects require time_limit."
            raise ValidationError({"time_limit": msg})


class Contribution(SharedMemoryModel):
    """A single contribution to a Project.

    Discriminator pattern: `kind` selects which kind-specific column is populated
    per row (ap_amount, money_amount, item_instance, check_outcome).
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="contributions")
    contributor_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.PROTECT,
        related_name="project_contributions",
    )
    kind = models.CharField(max_length=10, choices=ContributionKind.choices)

    # Kind-specific columns. Exactly one populated per row, per discriminator.
    ap_amount = models.PositiveIntegerField(null=True, blank=True)
    money_amount = models.PositiveIntegerField(null=True, blank=True)
    item_instance = models.ForeignKey(
        "items.ItemInstance",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_contributions",
    )
    check_outcome = models.ForeignKey(
        "traits.CheckOutcome",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project_contributions",
        help_text="Populated when kind=CHECK. References perform_check's CheckOutcome.",
    )

    # The authored check-based method used (CHECK contributions only); records which
    # method's check/AP/progress applied (#1574).
    contribution_method = models.ForeignKey(
        "projects.ContributionMethod",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contributions",
    )

    intent_text = models.TextField(blank=True)
    privacy_setting = models.CharField(
        max_length=10,
        choices=ContributionPrivacy.choices,
        default=ContributionPrivacy.PRIVATE,
    )
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["project", "contributor_persona"]),
        ]

    def __str__(self) -> str:
        return f"Contribution<{self.kind}>(#{self.pk}, project #{self.project_id})"

    def clean(self) -> None:
        super().clean()
        required_field_for_kind = {
            ContributionKind.AP: "ap_amount",
            ContributionKind.MONEY: "money_amount",
            ContributionKind.ITEM: "item_instance",
            ContributionKind.CHECK: "check_outcome",
        }
        required = required_field_for_kind.get(self.kind)
        if required is not None and getattr(self, required) is None:
            msg = f"Contribution kind={self.kind} requires {required} to be set."
            raise ValidationError({required: msg})


class ContributionMethod(SharedMemoryModel):
    """An authored, check-based way to contribute to projects of a given ProjectKind (#1574).

    Keyed by ``kind`` — every project of that kind offers the same methods (RANSOM has
    none, so its only contribution path is money). A contributor rolls ``check_type``,
    spending ``ap_cost`` AP; a successful check (``success_level >= 0``) advances the
    project by ``progress_on_success``. Money / item contributions need no method.
    """

    kind = models.CharField(
        max_length=40,
        choices=ProjectKind.choices,
        help_text="The ProjectKind whose projects offer this contribution method.",
    )
    name = models.CharField(
        max_length=80,
        help_text="Player-facing method name, picked in `project/check <id>=<name>`.",
    )
    description = models.TextField(blank=True)
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="project_contribution_methods",
        help_text="The check rolled to make this contribution.",
    )
    ap_cost = models.PositiveIntegerField(
        default=0,
        help_text="Action points spent to attempt this contribution.",
    )
    progress_on_success = models.PositiveIntegerField(
        help_text="Progress added to the project when the check succeeds (success_level >= 0).",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "name"], name="uniq_contribution_method_kind_name"
            ),
        ]

    def __str__(self) -> str:
        return f"ContributionMethod<{self.kind}>({self.name})"
