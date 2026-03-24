"""ConsequencePool and ConsequencePoolEntry models."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class ConsequencePool(NaturalKeyMixin, SharedMemoryModel):
    """Named, reusable collection of consequences with single-depth inheritance."""

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Human-readable pool name (e.g., 'Wild Magic Surge').",
    )
    description = models.TextField(
        blank=True,
        help_text="GM authoring context for this pool.",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        help_text="Inherit consequences from this pool (single depth only).",
    )

    class Meta:
        verbose_name = "Consequence Pool"
        verbose_name_plural = "Consequence Pools"

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.parent_id == self.pk and self.pk is not None:
            raise ValidationError({"parent": "A pool cannot be its own parent."})
        if self.parent is not None and self.parent.parent_id is not None:
            raise ValidationError(
                {"parent": "Single-depth inheritance only — parent already has a parent."}
            )


class ConsequencePoolEntry(SharedMemoryModel):
    """Links a Consequence to a Pool with optional weight override or exclusion."""

    pool = models.ForeignKey(
        ConsequencePool,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    consequence = models.ForeignKey(
        "checks.Consequence",
        on_delete=models.CASCADE,
        related_name="pool_entries",
    )
    weight_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Overrides Consequence.weight for this pool. Null uses default.",
    )
    is_excluded = models.BooleanField(
        default=False,
        help_text="If True, suppresses this consequence when inherited from parent.",
    )

    class Meta:
        verbose_name = "Consequence Pool Entry"
        verbose_name_plural = "Consequence Pool Entries"
        constraints = [
            models.UniqueConstraint(
                fields=["pool", "consequence"],
                name="unique_pool_consequence",
            ),
        ]

    def __str__(self) -> str:
        action = "excludes" if self.is_excluded else "includes"
        return f"{self.pool.name} {action} {self.consequence.label}"

    def clean(self) -> None:
        super().clean()
        if self.is_excluded and self.pool_id and not self._pool_has_parent():
            raise ValidationError(
                {"is_excluded": "Exclusion only applies to child pools with a parent."}
            )

    def _pool_has_parent(self) -> bool:
        pool = self.pool
        return pool.parent_id is not None
