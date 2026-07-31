"""EphemeralPullCapabilityGrant sidecar for non-combat CAPABILITY_GRANT pulls (#2840).

Carries the frozen per-pull curved magnitude for a non-combat thread pull's
CAPABILITY_GRANT effect. FK'd to a ConditionInstance (the lifecycle tracker);
CASCADE-deleted when the condition is removed.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.conditions.models import CapabilityType, ConditionInstance
from world.magic.models.threads import Thread


class EphemeralPullCapabilityGrant(SharedMemoryModel):
    """Frozen snapshot of one non-combat pull's CAPABILITY_GRANT (#2840).

    One row per (ConditionInstance, CapabilityType) pair. Multiple pulls in
    one scene share one ConditionInstance (the condition system's
    UniqueConstraint on (target, condition) enforces this); each pull's
    CAPABILITY_GRANT effects get their own sidecar row, or update an existing
    row to the MAX value (upsert-with-MAX, ADR-0034).
    """

    condition_instance = models.ForeignKey(
        ConditionInstance,
        on_delete=models.CASCADE,
        related_name="ephemeral_pull_grants",
        help_text="The Thread Surge condition this grant rides on.",
    )
    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.PROTECT,
        related_name="ephemeral_pull_grants",
        help_text="The character who pulled (denormalized for query efficiency).",
    )
    capability = models.ForeignKey(
        CapabilityType,
        on_delete=models.PROTECT,
        related_name="ephemeral_pull_grants",
    )
    grant_value = models.PositiveIntegerField(
        help_text=(
            "Frozen curved magnitude from apply_capability_curve, computed "
            "at pull resolution time (ADR-0173)."
        ),
    )
    source_thread = models.ForeignKey(
        Thread,
        on_delete=models.PROTECT,
        related_name="ephemeral_pull_grants",
        help_text="The thread that was pulled.",
    )
    source_thread_level = models.PositiveSmallIntegerField(
        help_text="Snapshot of thread level at pull time.",
    )
    source_tier = models.PositiveSmallIntegerField(
        help_text="Pull tier 0..3.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["condition_instance", "capability"],
                name="ephemeral_pull_grant_unique_per_capability",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"EphemeralPullGrant(cap={self.capability_id} "
            f"value={self.grant_value} tier={self.source_tier})"
        )
