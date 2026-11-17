"""Reflections and the rite of settling (#5124).

A ``Reflection`` links a piece of the player's own writing (a pose or a journal entry) to what
it reflects on: a deed already earned (``grant``), the resonance that is unsettling them
(``resonance``), or the Mire a Sineater carries for one Sinner (``tether``, #5177). A deed or
the unsettling resonance is Embraced or Disowned; a burden is Absolved, Condemned or Succumbed
to. It waits (``rite`` null) until a ``SettlingRite`` takes it. The rite is one roll; its share
applies to every waiting reflection.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.magic.constants import (
    BURDEN_REFLECTION_CHOICES,
    DEED_REFLECTION_CHOICES,
    ReflectionChoice,
)


class SettlingRite(SharedMemoryModel):
    """One performed rite of settling: when, where, the roll's outcome and its share (#5124).

    Kept as history.
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="settling_rites",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The scene the rite was performed in, if any.",
    )
    outcome = models.ForeignKey(
        "arxii.CheckOutcome",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The outcome of the rite's roll.",
    )
    share = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        help_text="The fraction of each reflection the rite applied, from 0.00 to 1.00.",
    )
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-performed_at"]

    def __str__(self) -> str:
        return f"SettlingRite(sheet={self.character_sheet_id}, share={self.share})"


class Reflection(SharedMemoryModel):
    """What a piece of writing reflects on, and what the writer does with it (#5124, #5177).

    Reflects on exactly one of a deed (``grant``), an unsettling resonance (``resonance``) or
    the Mire a Sineater carries for one Sinner (``tether``), through exactly one of a pose
    (``interaction``) or a journal entry (``journal_entry``) at creation. A ``tether``
    reflection takes Absolve, Condemn or Succumb; the others take Embrace or Disown. Deleting
    the writing leaves the reflection, so both writing links are SET_NULL and the database only
    refuses a reflection that names both. A reflection with no ``rite`` is waiting.
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="reflections",
    )
    choice = models.CharField(max_length=8, choices=ReflectionChoice.choices)
    grant = models.ForeignKey(
        "arxii.ResonanceGrant",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reflections",
        help_text="The deed reflected on. Set one of grant, resonance, tether.",
    )
    resonance = models.ForeignKey(
        "arxii.Resonance",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reflections",
        help_text="The unsettling resonance reflected on. Set one of grant, resonance, tether.",
    )
    tether = models.ForeignKey(
        "arxii.CharacterRelationship",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="burden_reflections",
        help_text=(
            "The Sineater's own side of the tether whose Mire is reflected on. "
            "Set one of grant, resonance, tether."
        ),
    )
    # Interaction is partitioned with a composite primary key, so the database holds no
    # constraint on this link (as for the other Interaction links).
    interaction = models.ForeignKey(
        "arxii.Interaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_constraint=False,
        related_name="reflections",
        help_text="The pose that carries the reflection.",
    )
    journal_entry = models.ForeignKey(
        "arxii.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reflections",
        help_text="The journal entry that carries the reflection.",
    )
    rite = models.ForeignKey(
        SettlingRite,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="reflections",
        help_text="The rite that took this reflection. Blank means it is waiting.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                name="reflection_exactly_one_target",
                check=(
                    (Q(grant__isnull=False) & Q(resonance__isnull=True) & Q(tether__isnull=True))
                    | (Q(grant__isnull=True) & Q(resonance__isnull=False) & Q(tether__isnull=True))
                    | (Q(grant__isnull=True) & Q(resonance__isnull=True) & Q(tether__isnull=False))
                ),
            ),
            models.CheckConstraint(
                name="reflection_choice_fits_target",
                check=(
                    (Q(tether__isnull=False) & Q(choice__in=BURDEN_REFLECTION_CHOICES))
                    | (Q(tether__isnull=True) & Q(choice__in=DEED_REFLECTION_CHOICES))
                ),
            ),
            models.CheckConstraint(
                name="reflection_not_both_writings",
                check=Q(interaction__isnull=True) | Q(journal_entry__isnull=True),
            ),
            models.UniqueConstraint(
                fields=["grant"],
                condition=Q(grant__isnull=False),
                name="reflection_one_per_grant",
            ),
        ]

    def clean(self) -> None:
        """Say in words what the two constraints say: one target, and a choice that fits it."""
        super().clean()
        named = [
            name
            for name, value in (
                ("grant", self.grant_id),
                ("resonance", self.resonance_id),
                ("tether", self.tether_id),
            )
            if value is not None
        ]
        if len(named) != 1:
            msg = "A reflection names exactly one of a deed, a resonance or a burden."
            raise ValidationError(msg)
        if self.tether_id is not None:
            allowed, on = BURDEN_REFLECTION_CHOICES, "a burden"
        else:
            allowed, on = DEED_REFLECTION_CHOICES, "a deed or a resonance"
        if self.choice not in allowed:
            wanted = " or ".join(ReflectionChoice(c).label for c in allowed)
            msg = f"A reflection on {on} takes {wanted}."
            raise ValidationError(msg)

    def __str__(self) -> str:
        return f"Reflection(sheet={self.character_sheet_id}, {self.choice})"
