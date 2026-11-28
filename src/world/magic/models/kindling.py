"""Kindled resonances (#5124): the situations that stir a resonance, and what a strength gives.

A resonance is *kindled* while a situation authored on it (or on its affinity) holds for the
character. Kindling is worked out on demand from the scene, the fight and the character, the
way vow perk situations are, so nothing is stored for it except the two cases the scene cannot
supply: a Rally's naming of an ally's resonance, and a GM's hand (``Kindling``).

Strength is a rank (1, 2, 3). Code knows only the rank; ``KindledStrengthTier`` carries the word
players read and what each rank gives (a higher thread level on a pull, how deep Fury may go,
a larger Dig deep surge, a larger earn). Players never see these numbers.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.checks.models import OutcomeTierAward
from world.covenants.models import SituationRequirementMixin
from world.covenants.perks.constants import Situation
from world.magic.constants import KindlingSource

#: The situations that can supply a strength themselves: a thread anchor through its bond tier,
#: a feeling through its condition's severity. Any other situation needs the row's ``strength``.
STRENGTH_FROM_SOURCE_SITUATIONS = frozenset(
    {
        Situation.THREAD_ANCHOR_PRESENT,
        Situation.OWN_FEELING,
        Situation.SHARED_FEELING,
        Situation.TARGET_IN_STATE_THEY_CAUSED,
    }
)


class KindlingSituation(SituationRequirementMixin, SharedMemoryModel):
    """One situation that kindles a resonance, or every resonance of an affinity (#5124).

    Inherits the vow perk situation parameter columns, so the row is checked through the same
    ``SituationCheck``. ``strength`` null means "from the source": the bond tier or the
    condition severity the situation reads.
    """

    resonance = models.ForeignKey(
        "arxii.Resonance",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="kindling_situations",
        help_text="The resonance this situation kindles. Set this or an affinity, not both.",
    )
    for_affinity = models.ForeignKey(
        "arxii.Affinity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="kindling_situations",
        help_text="Kindles every resonance of this affinity. Set this or a resonance, not both.",
    )
    situation = models.CharField(max_length=48, choices=Situation.choices)
    strength = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text=(
            "The strength rank this situation kindles at. Blank takes it from the source: "
            "the bond tier or the condition severity."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Retire a row that has paid out by clearing this; a used row cannot be deleted.",
    )
    display_order = models.PositiveSmallIntegerField(default=0)
    reason_text = models.CharField(
        max_length=300,
        blank=True,
        help_text=(
            "The reason a player reads. Blank builds it from the row: the anchor's name, "
            "the condition's name, or the theme's player text."
        ),
    )

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [
            models.CheckConstraint(
                name="kindling_situation_resonance_xor_affinity",
                check=(
                    (Q(resonance__isnull=False) & Q(for_affinity__isnull=True))
                    | (Q(resonance__isnull=True) & Q(for_affinity__isnull=False))
                ),
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if (self.resonance_id is None) == (self.for_affinity_id is None):
            msg = "Set exactly one of resonance and for_affinity."
            raise ValidationError({"resonance": msg, "for_affinity": msg})
        if self.strength is None and self.situation not in STRENGTH_FROM_SOURCE_SITUATIONS:
            raise ValidationError(
                {"strength": "This situation has no bond or severity to read: set a strength."}
            )

    def __str__(self) -> str:
        return self.get_situation_display()


class KindledStrengthTierManager(NaturalKeyManager):
    """Manager for KindledStrengthTier with natural key support."""


class KindledStrengthTier(NaturalKeyMixin, SharedMemoryModel):
    """What one strength rank is called, what reaches it and what it gives (#5124).

    Three rows (rank 1, 2, 3). Code compares only ``rank``; ``name`` is the word players read
    and staff can rename it. A missing row means that strength gives nothing. A reach column
    of 0 means the strength is not reached that way.
    """

    rank = models.PositiveSmallIntegerField(
        unique=True,
        validators=[MinValueValidator(1)],
        help_text="The order of the strength (1, 2, 3). Code knows only this.",
    )
    name = models.CharField(
        max_length=50, unique=True, help_text="The word players read for this strength."
    )
    min_bond_tier = models.PositiveSmallIntegerField(
        default=0,
        help_text="A thread-anchor bond at or above this tier reaches the strength; 0 = never.",
    )
    min_severity = models.PositiveSmallIntegerField(
        default=0,
        help_text="A feeling condition at or above this severity reaches the strength; 0 = never.",
    )
    pull_levels = models.PositiveSmallIntegerField(
        default=0, help_text="Levels a kindled payer's thread reads higher when it pays a pull."
    )
    give_in_max_depth = models.PositiveSmallIntegerField(
        default=0, help_text="The deepest Fury tier depth this strength lets a character give in."
    )
    give_in_bonus_percent = models.PositiveSmallIntegerField(
        default=0, help_text="Percent the intensity Fury buys grows at this strength."
    )
    give_in_ease_tenths = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Check difficulty reduction on the control roll at this strength, in tenths of "
            "one level's width at the Fury tier's base check level."
        ),
    )
    dig_deep_scale_percent = models.PositiveSmallIntegerField(
        default=0, help_text="Percent a Dig deep surge grows when the named resonance is kindled."
    )
    earn_percent = models.PositiveSmallIntegerField(
        default=0, help_text="Percent of a kindled deed's award this strength earns."
    )
    cast_power = models.PositiveSmallIntegerField(
        default=0,
        help_text="Power a cast gains when it is worked in a resonance kindled this strongly.",
    )

    objects = KindledStrengthTierManager()

    class NaturalKeyConfig:
        fields = ["rank"]

    class Meta:
        ordering = ["rank"]

    def __str__(self) -> str:
        return self.name


class KindlingConfig(SharedMemoryModel):
    """Singleton (pk=1) tuning for kindling (#5124): the harm property."""

    objects = ArxSharedMemoryManager()

    harm_property = models.ForeignKey(
        "arxii.Property",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "A condition carrying this property harms whoever bears it. A feeling the "
            "character spread that harms others is Abyssal, not a shared Primal feeling."
        ),
    )

    recorded_act_days = models.PositiveSmallIntegerField(
        default=90,
        db_default=90,
        help_text=(
            "How many days an act she took stays on her list to point at. After that it is "
            "removed, and a journal entry can no longer point at it."
        ),
    )

    class Meta:
        verbose_name = "Kindling config"
        verbose_name_plural = "Kindling config"

    def __str__(self) -> str:
        return "Kindling config"


class KindledDeedAward(OutcomeTierAward):
    """How much a kindled deed earns at one roll result, before the strength's earn_percent.

    A tier with no row earns nothing.
    """

    amount = models.PositiveIntegerField(
        help_text="Resonance a kindled deed earns at this roll result."
    )

    class Meta(OutcomeTierAward.Meta):
        verbose_name = "Kindled deed award"

    def __str__(self) -> str:
        return f"{self.outcome_tier.name}: {self.amount}"


class AnimaRitualResonanceAward(OutcomeTierAward):
    """How much resonance an Anima ritual with a partner earns at one roll result (#5181).

    A tier with no row earns nothing. The kindled strength's earn_percent adds to it when the
    ritual's resonance is kindled at that moment.
    """

    amount = models.PositiveIntegerField(
        help_text="Resonance an Anima ritual with a partner earns at this roll result."
    )

    class Meta(OutcomeTierAward.Meta):
        verbose_name = "Anima ritual resonance award"

    def __str__(self) -> str:
        return f"{self.outcome_tier.name}: {self.amount}"


class RallyKindlingStrength(OutcomeTierAward):
    """How strongly a Rally kindles an ally's resonance at one roll result.

    A tier with no row kindles nothing.
    """

    strength = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text="The strength rank a Rally kindles at this roll result.",
    )

    class Meta(OutcomeTierAward.Meta):
        verbose_name = "Rally kindling strength"
        verbose_name_plural = "Rally kindling strengths"

    def __str__(self) -> str:
        return f"{self.outcome_tier.name}: kindles at strength {self.strength}"


class Kindling(SharedMemoryModel):
    """A kindling the scene cannot supply: a Rally or a GM named a resonance (#5124).

    Ends with its fight or scene (CASCADE).
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="kindlings",
    )
    resonance = models.ForeignKey(
        "arxii.Resonance",
        on_delete=models.CASCADE,
        related_name="kindlings",
    )
    strength = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)], help_text="The strength rank."
    )
    source = models.CharField(max_length=8, choices=KindlingSource.choices)
    encounter = models.ForeignKey(
        "arxii.CombatEncounter",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="kindlings",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="kindlings",
    )
    kindled_by = models.ForeignKey(
        "arxii.CharacterSheet",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The ally whose Rally kindled it, or the GM's character.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                name="kindling_encounter_xor_scene",
                check=(
                    (Q(encounter__isnull=False) & Q(scene__isnull=True))
                    | (Q(encounter__isnull=True) & Q(scene__isnull=False))
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"Kindling(sheet={self.character_sheet_id}, resonance={self.resonance_id})"
