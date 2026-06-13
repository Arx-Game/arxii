"""ConsequenceOutcome and ConsequenceOutcomeModifier models.

ConsequenceOutcome is the unified anchor record written once per check
resolution — both combat damage resolution and challenge resolution write one.
A ViewSet exposes it with the roulette recomputed on read.

The `combat_interaction` FK is declared db_constraint=False because
scenes_interaction is range-partitioned by timestamp.  No composite FK
constraint (interaction_id, interaction_timestamp) is created at the DB level
for this table — unlike CombatRoundAction/ClashContribution, the raw-SQL
migration for that constraint has deliberately been omitted here because the
partitioned table has no DB-level referential integrity requirement.  Integrity
is maintained by the writer setting both columns atomically.

`combat_interaction_timestamp` is a denormalized companion field required for
the composite partition key.  It must be populated atomically with
`combat_interaction_id` by the caller.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q
from evennia.utils.idmapper.models import SharedMemoryModel

from world.checks.constants import ModifierSourceKind


class ConsequenceOutcome(SharedMemoryModel):
    """Unified record of one consequence-resolution event.

    Exactly one of (combat_interaction, challenge_record) must be set —
    enforced by the CheckConstraint below.  The modifier_total stores the
    pre-computed sum of all modifiers that were in effect at resolution time;
    individual rows are in ConsequenceOutcomeModifier (the ``modifiers``
    reverse relation).

    The roulette result is NOT stored — it is recomputed from pool +
    selected_consequence at read time.  The modifiers child rows persist the
    ModifierBreakdown snapshot so the recompute is accurate.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="consequence_outcomes",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.PROTECT,
        related_name="consequence_outcomes",
    )
    pool = models.ForeignKey(
        "actions.ConsequencePool",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="consequence_outcomes",
        help_text=(
            "The ConsequencePool used for roulette selection. "
            "Null for plain (non-template) challenge resolutions whose roulette "
            "is reconstructed on read from the authored consequence links rather "
            "than persisted as a derived pool."
        ),
    )
    selected_consequence = models.ForeignKey(
        "checks.Consequence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consequence_outcomes",
    )
    modifier_total = models.IntegerField(default=0)
    summary = models.CharField(max_length=255, blank=True)

    # combat_interaction: FK to the partitioned scenes_interaction table.
    # db_constraint=False because Django cannot express the required composite
    # FK (interaction_id, interaction_timestamp) against a range-partitioned
    # table.  No raw-SQL migration adds a DB-level composite FK constraint here;
    # integrity is maintained by the writer setting both columns atomically.
    combat_interaction = models.ForeignKey(
        "scenes.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="consequence_outcomes",
        help_text=(
            "The Interaction created when this outcome was resolved via combat. "
            "Null for challenge-based resolutions."
        ),
    )
    combat_interaction_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Denormalized from combat_interaction.timestamp. Required because "
            "scenes_interaction is range-partitioned by timestamp. "
            "No DB-level composite FK constraint is enforced — integrity is "
            "maintained by the writer setting both columns atomically."
        ),
    )

    challenge_record = models.ForeignKey(
        "mechanics.CharacterChallengeRecord",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="consequence_outcomes",
        help_text=(
            "The CharacterChallengeRecord this outcome was resolved for. "
            "Null for combat-based resolutions."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(Q(combat_interaction__isnull=False) & Q(challenge_record__isnull=True))
                | (Q(combat_interaction__isnull=True) & Q(challenge_record__isnull=False)),
                name="consequence_outcome_exactly_one_source",
            )
        ]

    def __str__(self) -> str:
        source = (
            f"interaction={self.combat_interaction_id}"
            if self.combat_interaction_id
            else f"challenge_record={self.challenge_record_id}"
        )
        return f"ConsequenceOutcome({source} character={self.character_id})"


class ConsequenceOutcomeModifier(SharedMemoryModel):
    """One modifier contribution snapshotted at consequence-resolution time.

    Together these rows reconstruct the full ModifierBreakdown that was in
    effect when the outcome was created.  The roulette recompute (Task 4.4)
    reads these rows rather than re-fetching live modifiers.
    """

    outcome = models.ForeignKey(
        ConsequenceOutcome,
        on_delete=models.CASCADE,
        related_name="modifiers",
    )
    source_kind = models.CharField(
        max_length=20,
        choices=ModifierSourceKind.choices,
    )
    source_label = models.CharField(max_length=120)
    value = models.IntegerField()

    def __str__(self) -> str:
        sign = "+" if self.value >= 0 else ""
        return f"{self.source_label} ({self.source_kind}): {sign}{self.value}"
