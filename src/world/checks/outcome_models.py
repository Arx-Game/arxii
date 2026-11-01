"""ConsequenceOutcome and ConsequenceOutcomeModifier models.

ConsequenceOutcome is the unified anchor record written once per check
resolution — combat, challenge, and action-template resolution write one.
A ViewSet exposes it with the roulette recomputed on read.

The `combat_interaction` FK is declared db_constraint=False because
arxii_interaction is range-partitioned by timestamp.  No composite FK
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

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.checks.constants import CombatRollKind, ModifierSourceKind


class ConsequenceOutcome(SharedMemoryModel):
    """Unified record of one consequence-resolution event.

    Exactly one source kind (combat interaction, challenge_record, action
    interaction) is recorded, enforced by the CheckConstraint below. An
    interaction source is recorded by its timestamp companion, because the
    writer may delete the pose itself and the FK then goes NULL (#4464).

    The modifier_total stores the pre-computed sum of all modifiers that were
    in effect at resolution time; individual rows are in
    ConsequenceOutcomeModifier (the ``modifiers``
    reverse relation).

    The roulette result is NOT stored — it is recomputed from pool +
    selected_consequence at read time.  The modifiers child rows persist the
    ModifierBreakdown snapshot so the recompute is accurate.
    """

    character = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="consequence_outcomes",
    )
    check_type = models.ForeignKey(
        "arxii.CheckType",
        on_delete=models.PROTECT,
        related_name="consequence_outcomes",
    )
    pool = models.ForeignKey(
        "arxii.ConsequencePool",
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
        "arxii.Consequence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consequence_outcomes",
    )
    modifier_total = models.IntegerField(default=0)
    summary = models.CharField(max_length=255, blank=True)
    skill_rating = models.IntegerField(
        null=True,
        blank=True,
        help_text=(
            "The character's rating in the skill the check weighted, as it was when the "
            "roll was made (#4858), so a breakdown shows what was rolled. Null when the "
            "writer records none or the check weights no skill."
        ),
    )
    # What a Strike roll was made with, as its breakdown names it, kept at roll time so a
    # weapon renamed, re-qualified or destroyed later does not rewrite the record (#4858).
    weapon_label = models.CharField(
        max_length=120,
        null=True,
        blank=True,
        help_text="The weapon and its quality as the roll's breakdown names it, at roll time.",
    )
    weapon_kind = models.CharField(
        max_length=60,
        null=True,
        blank=True,
        help_text="The weapon's kind as the breakdown names it ('one-handed melee'), at roll time.",
    )
    stat_label = models.CharField(
        max_length=60,
        null=True,
        blank=True,
        help_text="The stat or stats the roll used, as the breakdown names them, at roll time.",
    )
    # The attacker's combat style on the roll, kept at roll time so renaming or retuning
    # the style later does not rewrite the record (#4884).
    style_name = models.CharField(
        max_length=80,
        null=True,
        blank=True,
        help_text="The combat style's name as it was when the roll was made. Null: no style.",
    )
    style_skill_rating = models.IntegerField(
        null=True,
        blank=True,
        help_text="The style skill rating the roll added. Null when it lapsed or had none.",
    )
    style_lapse_note = models.CharField(
        max_length=120,
        null=True,
        blank=True,
        help_text=(
            "Why the style skill did not count, as the breakdown says it ('two-handed "
            "weapons are not this style's'). Null when it counted."
        ),
    )
    stat_from_style = models.BooleanField(
        default=False,
        help_text="Whether the roll's stat was the style's hit stat.",
    )
    # A PC's defense roll against an NPC blow (#4884), kept at roll time. As long as the
    # opponent's name can be (``CombatOpponent.name``).
    combat_roll_kind = models.CharField(
        max_length=10,
        choices=CombatRollKind.choices,
        null=True,
        blank=True,
        help_text="Which combat roll this records, for its breakdown. Null for any other roll.",
    )
    against_label = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text="Who a defense roll was against, as its breakdown names them, at roll time.",
    )
    combat_round = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The encounter round a combat roll was made in, so the turn panel can show every "
            "roll of the last round. Null outside combat."
        ),
    )
    armor_share_tenths = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "How much of the defender's armor counted, in tenths, from their combat style at "
            "roll time. Null when the defender had no style."
        ),
    )

    # combat_interaction: FK to the partitioned arxii_interaction table.
    # db_constraint=False because Django cannot express the required composite
    # FK (interaction_id, interaction_timestamp) against a range-partitioned
    # table.  No raw-SQL migration adds a DB-level composite FK constraint here;
    # integrity is maintained by the writer setting both columns atomically.
    combat_interaction = models.ForeignKey(
        "arxii.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="consequence_outcomes",
        help_text=(
            "The Interaction created when this outcome was resolved via combat. "
            "Null for challenge-based resolutions, and nulled if the writer deletes "
            "the pose; combat_interaction_timestamp still records the source."
        ),
    )
    combat_interaction_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Denormalized from combat_interaction.timestamp. Required because "
            "arxii_interaction is range-partitioned by timestamp. "
            "No DB-level composite FK constraint is enforced — integrity is "
            "maintained by the writer setting both columns atomically."
        ),
    )

    challenge_record = models.ForeignKey(
        "arxii.CharacterChallengeRecord",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="consequence_outcomes",
        help_text=(
            "The CharacterChallengeRecord this outcome was resolved for. "
            "Null for combat-based resolutions."
        ),
    )

    # action_interaction: FK to the partitioned Interaction table for
    # action-template resolutions outside combat. Kept separate from
    # combat_interaction so the source is explicit in readers and constraints.
    action_interaction = models.ForeignKey(
        "arxii.Interaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_constraint=False,
        related_name="action_consequence_outcomes",
        help_text=(
            "The Interaction created for a template-driven scene action. "
            "Null for combat and challenge-based resolutions, and nulled if the "
            "writer deletes the pose; action_interaction_timestamp still records "
            "the source."
        ),
    )
    action_interaction_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Denormalized from action_interaction.timestamp for the partition key. "
            "Integrity is maintained by the writer setting both columns atomically."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # The style snapshot (#4884): a lapse names its reason and records no rating; a
            # counted style skill records its rating and no lapse; either needs the name.
            models.CheckConstraint(
                check=(
                    Q(style_lapse_note__isnull=True)
                    | (Q(style_name__isnull=False) & Q(style_skill_rating__isnull=True))
                )
                & (
                    Q(style_skill_rating__isnull=True)
                    | (Q(style_name__isnull=False) & Q(style_lapse_note__isnull=True))
                ),
                name="consequence_outcome_style_snapshot_shape",
            ),
            # The source KIND is keyed on the timestamp companions, not the
            # Interaction FKs (#4464). A writer may delete their own pose within
            # DELETION_WINDOW_DAYS (scenes.interaction_services.delete_interaction);
            # the FK then goes NULL, like every other mechanical record that points
            # at an Interaction (CombatRoundAction, DramaticMoment, ...). The
            # timestamp stays, so the outcome still says it came from combat or a
            # scene action and when; the check history survives the deleted text.
            models.CheckConstraint(
                check=(
                    Q(combat_interaction_timestamp__isnull=False)
                    & Q(challenge_record__isnull=True)
                    & Q(action_interaction_timestamp__isnull=True)
                )
                | (
                    Q(combat_interaction_timestamp__isnull=True)
                    & Q(challenge_record__isnull=False)
                    & Q(action_interaction_timestamp__isnull=True)
                )
                | (
                    Q(combat_interaction_timestamp__isnull=True)
                    & Q(challenge_record__isnull=True)
                    & Q(action_interaction_timestamp__isnull=False)
                ),
                name="consequence_outcome_exactly_one_source",
            ),
            # A linked Interaction always carries its partition timestamp.
            models.CheckConstraint(
                check=(
                    Q(combat_interaction__isnull=True)
                    | Q(combat_interaction_timestamp__isnull=False)
                )
                & (
                    Q(action_interaction__isnull=True)
                    | Q(action_interaction_timestamp__isnull=False)
                ),
                name="consequence_outcome_interaction_has_timestamp",
            ),
        ]

    def __str__(self) -> str:
        if self.combat_interaction_timestamp is not None:
            source = f"interaction={self.combat_interaction_id}"
        elif self.challenge_record_id:
            source = f"challenge_record={self.challenge_record_id}"
        else:
            source = f"action_interaction={self.action_interaction_id}"
        return f"ConsequenceOutcome({source} character={self.character_id})"


class ConsequenceOutcomeModifier(SharedMemoryModel):
    """One modifier contribution snapshotted at consequence-resolution time.

    Together these rows reconstruct the full ModifierBreakdown that was in
    effect when the outcome was created. ``value`` is what the contribution counted
    for after the light taper (#4594), so the rows sum exactly to the outcome's
    ``modifier_total``; an untapered contribution is recorded at its full value.
    The roulette recompute (Task 4.4)
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
