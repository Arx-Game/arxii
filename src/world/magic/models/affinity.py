"""Affinity and Resonance domain models.

Affinities are the three magical sources (Celestial, Primal, Abyssal).
Resonances are style tags that contribute to affinities and have opposing pairs.
Both are proper domain models replacing the old ModifierTarget-based pattern.
"""

from decimal import Decimal

from django.db import models
from django.utils.functional import cached_property

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from core.testing import register_test_cache_flusher
from world.contributors.models import CreditedContent
from world.magic.constants import AFFINITY_ABYSSAL, AFFINITY_CELESTIAL, AFFINITY_PRIMAL
from world.magic.exceptions import AffinityNotConfigured


class AffinityManager(NaturalKeyManager):
    """Manager for Affinity with natural key support and the three canonical getters.

    The getters share one class-level cache loaded with a single query. Call
    ``clear_cache()`` in test ``setUp``, as for ``AffinityInteractionManager``.
    """

    _canonical_cache: dict[str, "Affinity"] | None = None

    @classmethod
    def clear_cache(cls) -> None:
        """Discard the cached canonical rows. Must be called in test setUp."""
        cls._canonical_cache = None

    def _canonical(self, name: str) -> "Affinity":
        if AffinityManager._canonical_cache is None:
            AffinityManager._canonical_cache = {
                row.name: row
                for row in self.filter(
                    name__in=[AFFINITY_CELESTIAL, AFFINITY_PRIMAL, AFFINITY_ABYSSAL]
                )
            }
        row = AffinityManager._canonical_cache.get(name)
        if row is None:
            # Do not cache the miss: the row may be authored later.
            AffinityManager._canonical_cache = None
            msg = f"No Affinity row named {name!r} is configured."
            raise AffinityNotConfigured(msg)
        return row

    def get_celestial_affinity(self) -> "Affinity":
        return self._canonical(AFFINITY_CELESTIAL)

    def get_primal_affinity(self) -> "Affinity":
        return self._canonical(AFFINITY_PRIMAL)

    def get_abyssal_affinity(self) -> "Affinity":
        return self._canonical(AFFINITY_ABYSSAL)


# A rolled-back test leaves the canonical rows cached with primary keys the database no
# longer holds; the test runner drops them after every test, as a restart would.
register_test_cache_flusher(AffinityManager.clear_cache)


class Affinity(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    A magical affinity (Celestial, Abyssal, Primal).

    Proper domain model replacing the old pattern of storing affinities
    as ModifierTarget rows with category='affinity'.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Affinity name (e.g., 'Celestial', 'Abyssal', 'Primal').",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this affinity.",
    )
    corruption_coefficient = models.PositiveSmallIntegerField(
        default=0,
        help_text="Integer tenths of corruption per cast tick for this affinity's resonances.",
    )
    burn_value = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text=(
            "Strain units one burned point of this affinity's resonance is worth. "
            "Higher makes burning this affinity's resonance push harder."
        ),
    )
    objects = AffinityManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name_plural = "Affinities"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ResonanceManager(NaturalKeyManager):
    """Manager for Resonance with natural key support."""


class Resonance(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    A magical resonance — a style tag that defines magical identity.

    Resonances contribute to affinities and have opposing pairs.
    Proper domain model replacing the old pattern of storing resonances
    as ModifierTarget rows with category='resonance'.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=(
            "Resonance name. The canonical set is authored in the content repo — "
            "do not invent one here."
        ),
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this resonance.",
    )
    affinity = models.ForeignKey(
        Affinity,
        on_delete=models.PROTECT,
        related_name="resonances",
        help_text="Which affinity this resonance contributes to.",
    )
    opposite = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opposite_of",
        help_text="The opposing resonance in the pair.",
    )
    properties = models.ManyToManyField(
        "arxii.Property",
        blank=True,
        related_name="resonances",
        help_text="Properties associated with this resonance (e.g., Flame → flame property).",
    )
    codex_entry = models.ForeignKey(
        "arxii.CodexEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resonances",
        help_text="Lore entry this resonance is bound to, if any.",
    )
    objects = ResonanceManager()

    @cached_property
    def cached_properties(self) -> list:
        """Fallback for when prefetch is not used. Prefer prefetch_related with to_attr."""
        return list(self.properties.all())

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["affinity", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.affinity.name})"


class ResonanceTier(SharedMemoryModel):
    """Ordered potency tier for resonance-tied items and touchstones.

    Independent of ``items.QualityTier`` (crafting/craftsmanship quality) —
    resonance potency and crafting quality are orthogonal axes. A Tier-1
    Praedari paw can be Masterwork-crafted; a Tier-3 Copperi reliquary can
    be Common-quality.
    """

    name = models.CharField(max_length=50, unique=True)
    tier_level = models.PositiveSmallIntegerField(
        unique=True,
        help_text="Ordering + threshold-comparison value (1=lowest).",
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["tier_level"]

    def __str__(self) -> str:
        return self.name
