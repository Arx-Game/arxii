"""Recorded acts: what a player character did, kept so her player can point a mark at it (#5327).

``award_kindled_deeds`` writes one ``RecordedAct`` for each act a player character takes that
earns an award row and pays no chosen deed. Situations that held at that moment are kept beside
it as ``RecordedActSuggestion`` rows: they suggest a resonance and set its strength, and never
pay by themselves. A player marks a pose or journal entry with a resonance and points it at an
act; the act then carries the grant it paid and the writing that carried the mark.
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q

from actions.constants import ActionCategory
from core.models import ArxSharedMemoryModel as SharedMemoryModel


class RecordedAct(SharedMemoryModel):
    """One act a player character took, waiting to be marked or already marked (#5327).

    Unmarked means ``marked_grant`` is null. The result tier and check type are references,
    not copied numbers, so a retune of the kindled deed award table reaches acts that wait.
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="recorded_acts",
        help_text="The character who took the act.",
    )
    label = models.CharField(
        max_length=200,
        help_text=(
            "What she did, as the game words it from the action and its target. A deed "
            "grant records the same label."
        ),
    )
    outcome = models.ForeignKey(
        "arxii.CheckOutcome",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=(
            "The result tier of the act's roll; its worth is read from the kindled deed "
            "award when she marks it."
        ),
    )
    check_type = models.ForeignKey(
        "arxii.CheckType",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "The check the act rolled; its heaviest stat is the one the bonus check "
            "borrows. Blank when it rolled none."
        ),
    )
    target_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Who the act was aimed at, when a person. An Abyssal gain from it tires this character."
        ),
    )
    fatigue_category = models.CharField(
        max_length=10,
        choices=ActionCategory.choices,
        help_text="The fatigue pool a gain from this act charges.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    marked_grant = models.OneToOneField(
        "arxii.ResonanceGrant",
        null=True,
        blank=True,
        # RESTRICT, not CASCADE: deleting a grant must never free an act to pay twice. Not
        # PROTECT either, so deleting a character (whose grants and acts go together) works,
        # as for ``ResonanceGrant.source_settling_rite``.
        on_delete=models.RESTRICT,
        related_name="marked_act",
        help_text="The gain this act paid when she marked it. None means unmarked.",
    )
    # Interaction is partitioned with a composite primary key, so the database holds no
    # constraint on this link and there is no timestamp column (as for PoseResonanceReach).
    marked_interaction = models.ForeignKey(
        "arxii.Interaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_constraint=False,
        related_name="marked_acts",
        help_text="The pose that carried the mark.",
    )
    marked_journal_entry = models.ForeignKey(
        "arxii.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="marked_acts",
        help_text="The journal entry that carried the mark.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["character_sheet", "created_at"], name="recorded_act_sheet_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                name="recorded_act_marked_one_way",
                check=(
                    (Q(marked_interaction__isnull=True) | Q(marked_journal_entry__isnull=True))
                    & (
                        Q(marked_grant__isnull=False)
                        | (
                            Q(marked_interaction__isnull=True)
                            & Q(marked_journal_entry__isnull=True)
                        )
                    )
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"RecordedAct(sheet={self.character_sheet_id}, {self.label})"


class RecordedActSuggestion(SharedMemoryModel):
    """A resonance a situation suggested for one recorded act, at the strength it reached."""

    act = models.ForeignKey(
        RecordedAct,
        on_delete=models.CASCADE,
        related_name="suggestions",
    )
    resonance = models.ForeignKey(
        "arxii.Resonance",
        # CASCADE: a suggestion naming a deleted row is none, and the act then pays at the
        # lowest strength.
        on_delete=models.CASCADE,
        related_name="+",
    )
    strength = models.ForeignKey(
        "arxii.KindledStrengthTier",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The strength the situation reached for this act.",
    )
    reason = models.CharField(
        max_length=300,
        blank=True,
        help_text="The line the player reads beside the act, from the situation's reason text.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["act", "resonance"],
                name="recorded_act_suggestion_one_per_resonance",
            ),
        ]

    def __str__(self) -> str:
        return f"RecordedActSuggestion(act={self.act_id}, resonance={self.resonance_id})"
