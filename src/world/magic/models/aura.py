"""Character aura and affinity totals.

CharacterAura tracks a character's soul-state percentages across the three
affinities. CharacterResonance is the per-character per-resonance row that
doubles as identity anchor and spendable resonance currency.
CharacterAffinityTotal is the aggregate total, updated when affinity sources
change.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.models.affinity import Affinity, Resonance
from world.magic.types import AffinityType


class CharacterAura(SharedMemoryModel):
    """
    Tracks a character's soul-state across the three affinities.

    Aura is stored as percentages (0-100) that should sum to 100.
    Player-facing display uses narrative descriptions, not raw numbers.
    """

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="aura",
        help_text="The character this aura belongs to.",
    )
    celestial = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(100))],
        help_text="Percentage of Celestial affinity (0-100).",
    )
    primal = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("80.00"),
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(100))],
        help_text="Percentage of Primal affinity (0-100).",
    )
    abyssal = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(100))],
        help_text="Percentage of Abyssal affinity (0-100).",
    )
    glimpse_story = models.TextField(
        blank=True,
        help_text="Narrative of the character's first magical awakening (The Glimpse).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Character Aura"
        verbose_name_plural = "Character Auras"

    def __str__(self) -> str:
        return f"Aura of {self.character}"

    def clean(self) -> None:
        """Validate that percentages sum to 100."""
        total = self.celestial + self.primal + self.abyssal
        if total != Decimal("100.00"):
            msg = f"Aura percentages must sum to 100, got {total}."
            raise ValidationError(msg)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def dominant_affinity(self) -> AffinityType:
        """Return the affinity type with the highest percentage."""
        values = [
            (self.celestial, AffinityType.CELESTIAL),
            (self.primal, AffinityType.PRIMAL),
            (self.abyssal, AffinityType.ABYSSAL),
        ]
        return max(values, key=lambda x: x[0])[1]


class CharacterResonance(SharedMemoryModel):
    """Per-character per-resonance row.

    Identity (the row exists = "this character is associated with this
    resonance") and currency bucket (`balance` is spendable, `lifetime_earned`
    is monotonic). See Resonance Pivot Spec A §2.2.
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="resonances",
        help_text="The character sheet this resonance is attached to.",
    )
    resonance = models.ForeignKey(
        Resonance,
        on_delete=models.PROTECT,
        related_name="character_resonances",
        help_text="The resonance type.",
    )
    balance = models.PositiveIntegerField(
        default=0,
        help_text="Spendable resonance currency.",
    )
    lifetime_earned = models.PositiveIntegerField(
        default=0,
        help_text="Monotonic total of resonance earned (never decremented).",
    )
    claimed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this resonance row was created (claimed by the character).",
    )
    flavor_text = models.TextField(
        blank=True,
        help_text="Optional player-defined description of how this resonance manifests.",
    )

    class Meta:
        unique_together = (("character_sheet", "resonance"),)
        verbose_name = "Character Resonance"
        verbose_name_plural = "Character Resonances"

    def __str__(self) -> str:
        return f"{self.resonance.name} on {self.character_sheet}"


class CharacterAffinityTotal(SharedMemoryModel):
    """
    Aggregate affinity total for a character.

    Updated when affinity sources change (distinctions, conditions, etc.).
    Used to calculate aura percentages dynamically.
    """

    character = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="affinity_totals",
    )
    affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="character_totals",
    )
    total = models.IntegerField(default=0)

    class Meta:
        unique_together = [("character", "affinity")]
        verbose_name = "Character Affinity Total"
        verbose_name_plural = "Character Affinity Totals"

    def __str__(self) -> str:
        return f"{self.character}: {self.affinity.name} = {self.total}"
