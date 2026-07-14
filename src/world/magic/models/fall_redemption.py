"""Fall / Redemption system models (#1583).

Models for the asymmetric resonance conversion system:
- ``CompromiseActType`` — authored act categories that grant non-native
  resonance when performed (combat kills, cruelty, pragmatism).
- ``ResonanceConversion`` — authored mapping from a source resonance to a
  target resonance for a given destination affinity path.
- ``FallRedemptionConfig`` — singleton tuning surface for conversion
  multipliers per Fall/Redemption path.
- ``FallRedemptionRecord`` — immutable audit of a full (irreversible) Fall
  or Redemption conversion ceremony.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from world.magic.types.aura import AffinityType

_RESONANCE_FK = "magic.Resonance"
_CONFIG_VERBOSE = "Fall / Redemption Config"


class CompromiseActType(SharedMemoryModel):
    """Authored act category that grants non-native resonance when performed.

    Staff author rows like "Combat Kill" → a Primal predation resonance,
    "Torture" → an Abyssal cruelty resonance. Mission options, combat
    outcomes, and social scene actions reference these to call
    ``grant_compromise_resonance``.
    """

    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    target_resonance = models.ForeignKey(
        _RESONANCE_FK,
        on_delete=models.PROTECT,
        related_name="compromise_act_types",
        help_text="The resonance granted by this compromising act.",
    )
    amount = models.PositiveIntegerField(
        default=10,
        help_text="Resonance amount granted by this act.",
    )
    is_cruelty = models.BooleanField(
        default=False,
        help_text=(
            "Convenience flag: True when target_resonance.affinity is Abyssal. "
            "Derivable from the FK but surfaced for admin filtering and future "
            "content-authoring tooling."
        ),
    )

    class Meta:
        verbose_name = "Compromise Act Type"
        verbose_name_plural = "Compromise Act Types"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} → {self.target_resonance.name} ({self.amount})"


class ResonanceConversion(SharedMemoryModel):
    """Authored mapping: which target resonance a source resonance converts to
    for a given destination affinity.

    Staff author one row per (source_resonance, target_affinity). E.g., if
    "Bene" (Celestial) converts to Primal, the row maps (Bene, PRIMAL) →
    some Primal resonance. A different row maps (Bene, ABYSSAL) → some
    Abyssal resonance. This allows different target resonances per Fall path.
    """

    source_resonance = models.ForeignKey(
        _RESONANCE_FK,
        on_delete=models.PROTECT,
        related_name="conversion_sources",
        help_text="The resonance being converted away from.",
    )
    target_affinity = models.CharField(
        max_length=16,
        choices=AffinityType.choices,
        help_text="The destination affinity for this conversion path.",
    )
    target_resonance = models.ForeignKey(
        _RESONANCE_FK,
        on_delete=models.PROTECT,
        related_name="conversion_targets",
        help_text="The resonance the source converts into for this path.",
    )

    class Meta:
        unique_together = (("source_resonance", "target_affinity"),)
        verbose_name = "Resonance Conversion"
        verbose_name_plural = "Resonance Conversions"

    def __str__(self) -> str:
        return (
            f"{self.source_resonance.name} → {self.target_affinity} → {self.target_resonance.name}"
        )


class FallRedemptionConfig(SharedMemoryModel):
    """Singleton (pk=1) of conversion multipliers per Fall/Redemption path.

    Fall multipliers are >1.0 (gain); Redemption multipliers are <1.0 (loss).
    Celestial→Abyssal is the largest gain; Abyssal→Celestial is the largest loss.
    The penance_exchange_rate controls the lossy partial conversion during
    the Rite of Atonement.
    """

    objects = ArxSharedMemoryManager()

    # Fall multipliers (>1.0 = gain)
    celestial_to_primal_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.20"),
        help_text="Multiplier on balance+lifetime_earned when a Celestial Falls to Primal.",
    )
    celestial_to_abyssal_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.50"),
        help_text="Multiplier when a Celestial Falls to Abyssal (the dramatic Fall).",
    )
    primal_to_abyssal_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.20"),
        help_text="Multiplier when a Primal Falls to Abyssal.",
    )
    # Redemption multipliers (<1.0 = loss)
    abyssal_to_primal_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("0.70"),
        help_text="Multiplier when an Abyssal character Redeems to Primal.",
    )
    primal_to_celestial_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("0.70"),
        help_text="Multiplier when a Primal character Redeems to Celestial.",
    )
    abyssal_to_celestial_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("0.50"),
        help_text="Multiplier when an Abyssal character Redeems to Celestial (the costly path).",
    )
    # Atonement resonance conversion (partial, lossy)
    penance_exchange_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("0.50"),
        help_text=(
            "Multiplier applied to the converted amount. 0.5 = for every 2 non-native "
            "balance converted, 1 Celestial balance is granted. The player specifies "
            "how much non-native balance to convert; this rate determines the lossy "
            "Celestial output."
        ),
    )
    # Fall eligibility
    fall_threshold_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("40.00"),
        help_text="Target affinity aura % that must be reached for the Fall to be available.",
    )

    class Meta:
        verbose_name = _CONFIG_VERBOSE
        verbose_name_plural = _CONFIG_VERBOSE

    def __str__(self) -> str:
        return _CONFIG_VERBOSE


class ConversionType(models.TextChoices):
    """Type of Fall/Redemption conversion."""

    FALL = "FALL", "Fall"
    REDEMPTION = "REDEMPTION", "Redemption"


class FallRedemptionRecord(SharedMemoryModel):
    """Immutable audit of a full (irreversible) Fall or Redemption conversion.

    Created when a character undergoes the full conversion ceremony. One row
    per conversion — a character who has Fallen to Primal and later Redeems
    to Celestial would have two rows. The existence of a row for a given
    from_affinity prevents re-conversion.
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="fall_redemption_records",
    )
    conversion_type = models.CharField(
        max_length=16,
        choices=ConversionType.choices,
    )
    from_affinity = models.CharField(max_length=16, choices=AffinityType.choices)
    to_affinity = models.CharField(max_length=16, choices=AffinityType.choices)
    multiplier = models.DecimalField(max_digits=4, decimal_places=2)
    performed_at = models.DateTimeField(auto_now_add=True)
    scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fall_redemption_records",
    )

    class Meta:
        verbose_name = "Fall / Redemption Record"
        verbose_name_plural = "Fall / Redemption Records"
        ordering = ["-performed_at"]

    def __str__(self) -> str:
        return f"{self.conversion_type}: {self.from_affinity} → {self.to_affinity}"
