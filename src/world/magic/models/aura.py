"""Character aura and affinity totals.

CharacterAura tracks a character's soul-state percentages across the three
affinities. CharacterResonance is the per-character per-resonance row that
doubles as identity anchor and spendable resonance currency.
"""

from decimal import Decimal
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from evennia_extensions.cached_property import PrunedCachedProperty
from evennia_extensions.mixins import CachedPropertiesMixin, RelatedCacheClearingMixin
from world.magic.constants import GlimpseState
from world.magic.models.affinity import Affinity, Resonance
from world.magic.types import AffinityType


class CharacterAura(CachedPropertiesMixin, SharedMemoryModel):
    """
    Tracks a character's soul-state across the three affinities.

    Aura is stored as percentages (0-100) that should sum to 100.
    Player-facing display uses narrative descriptions, not raw numbers.
    """

    character = models.OneToOneField(
        "arxii.CharacterSheet",
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
    glimpse_state = models.CharField(
        max_length=20,
        choices=GlimpseState.choices,
        default=GlimpseState.NOT_STARTED,
        help_text=(
            "Deferral/progress state of the Glimpse (#2427). Cache of "
            "prose+tag truth — maintained by world.magic.services.glimpse, "
            "never written directly."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Character Aura"
        verbose_name_plural = "Character Auras"

    def __str__(self) -> str:
        return f"Aura of {self.character}"

    def clean(self) -> None:
        """Validate that the held shares sum to 100 (an aura with no shares yet is fine)."""
        if self.pk is None:
            return
        shares = self.cached_shares
        if not shares:
            return
        total = sum((share.percent for share in shares), Decimal(0))
        if total != Decimal("100.00"):
            msg = f"Aura percentages must sum to 100, got {total}."
            raise ValidationError(msg)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    @PrunedCachedProperty
    def cached_shares(self) -> list["CharacterAuraShare"]:
        """This aura's share rows (one per affinity held), cleared by set_aura_shares.

        Fed cold by a ``Prefetch`` landing on this name in the character sheet
        serializer's magic and theming sections.
        """
        return list(self.shares.select_related("affinity"))

    def percent_for(self, affinity: Affinity) -> Decimal:
        """This affinity's percent of the aura; 0 when there is no row."""
        for share in self.cached_shares:
            if share.affinity_id == affinity.pk:
                return share.percent
        return Decimal(0)

    @property
    def dominant_affinity(self) -> Affinity:
        """The affinity with the highest percent; ties go to the lowest Affinity pk.

        Raises ValueError for an aura with no shares (not yet formed).
        """
        if not self.cached_shares:
            msg = "This aura holds no affinity shares."
            raise ValueError(msg)
        best = min(self.cached_shares, key=lambda share: (-share.percent, share.affinity_id))
        return best.affinity


class CharacterAuraShare(RelatedCacheClearingMixin, SharedMemoryModel):
    """One affinity's percentage of a character's aura (one row per affinity held)."""

    related_cache_fields: ClassVar[list[str]] = ["aura"]

    aura = models.ForeignKey(
        CharacterAura,
        on_delete=models.CASCADE,
        related_name="shares",
    )
    affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="aura_shares",
    )
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(100))],
        help_text="This affinity's share of the aura, 0-100.",
    )

    class Meta:
        ordering = ["aura", "affinity"]
        constraints = [
            models.UniqueConstraint(
                fields=["aura", "affinity"],
                name="unique_aura_share_per_affinity",
            )
        ]
        verbose_name = "Character Aura Share"
        verbose_name_plural = "Character Aura Shares"

    def __str__(self) -> str:
        return f"{self.affinity} {self.percent}% of {self.aura}"


class CharacterResonance(RelatedCacheClearingMixin, SharedMemoryModel):
    """Per-character per-resonance row.

    Identity (the row exists = "this character is associated with this
    resonance") and currency bucket (`balance` is spendable, `lifetime_earned`
    is monotonic). See Resonance Pivot Spec A §2.2.
    """

    related_cache_fields: ClassVar[list[str]] = ["character_sheet"]
    #: character_sheet is required (no null=True) and never reassigned after
    #: creation, and CharacterSheet.cached_resonances filters solely on
    #: character_sheet -- safe to skip the clear on a field-only balance
    #: update (#3816 final review; see the flag's docstring on the mixin).
    skip_related_cache_clear_when_fk_unchanged: ClassVar[bool] = True

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
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
    lifetime_helped = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Sineater per-resonance counter (Spec B §10.1). Increments on "
            "every accepted Sineating unit and rescue ritual for this resonance. "
            "Monotonic — never decreases. Drives the Sineater's CORRUPTION_RESISTANCE "
            "magnitude when they have a Sineater Thread in this resonance."
        ),
    )
    corruption_current = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Current corruption load on this resonance for this character. "
            "Mutable — increments via accrue_corruption, decrements via "
            "reduce_corruption / Scope 6 decay. Drives stage progression "
            "on the per-resonance Corruption ConditionInstance."
        ),
    )
    corruption_lifetime = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Monotonic audit of total corruption ever ticked to this "
            "resonance. Achievement-tracking surface. Never decremented."
        ),
    )

    class Meta:
        unique_together = (("character_sheet", "resonance"),)
        verbose_name = "Character Resonance"
        verbose_name_plural = "Character Resonances"

    def __str__(self) -> str:
        return f"{self.resonance.name} on {self.character_sheet}"


class AuraAffinityThreshold(SharedMemoryModel):
    """Authored affinity-percentage threshold that grants an achievement on crossing.

    Checked by fire_aura_threshold_crossings after every recompute_aura() call
    (#1737). Mirrors the fire_variant_discoveries pattern (direct before/after
    check, not a Flows event) — see world/covenants/discovery.py.
    """

    affinity = models.CharField(max_length=16, choices=AffinityType.choices)
    affinity_ref = models.ForeignKey(
        "arxii.Affinity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Row-keyed replacement for affinity (#4681); the CharField is removed later.",
    )
    threshold_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal(0)), MaxValueValidator(Decimal(100))],
        help_text="Percentage (0-100) this affinity must cross to fire.",
    )
    discovery_achievement = models.ForeignKey(
        "arxii.Achievement",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="aura_affinity_thresholds",
    )

    class Meta:
        unique_together = (("affinity", "threshold_percent"),)
        verbose_name = "Aura Affinity Threshold"
        verbose_name_plural = "Aura Affinity Thresholds"

    def __str__(self) -> str:
        return f"{self.affinity} >= {self.threshold_percent}%"
