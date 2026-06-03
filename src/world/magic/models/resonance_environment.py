"""AffinityInteraction directed-pair table and ResonanceEnvironmentConfig singleton
for the resonance-environment primitive.

Staff-authored AffinityInteraction rows tell the system what happens when a
caster's magic affinity meets a place's affinity.

ResonanceEnvironmentConfig is the staff-tunable scalar singleton (pk=1) that
controls the numeric shape of severity calculations and backfire difficulty.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property
from evennia.utils.idmapper.manager import SharedMemoryManager
from evennia.utils.idmapper.models import SharedMemoryModel

from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceValence,
)

if TYPE_CHECKING:
    from world.conditions.models import ConditionTemplate
    from world.magic.models.affinity import Affinity

# Sentinel used by AffinityInteractionManager.interaction_for to distinguish
# "key absent from cache" from "key present with None value".
_MISSING: object = object()


class AffinityInteractionManager(SharedMemoryManager):
    """Manager for AffinityInteraction with a cached lookup over the fixed 9-row table.

    Test-isolation: the cross-process cache is stored as a class-level dict
    ``_interaction_cache`` (``None`` until first loaded). Call
    ``clear_cache()`` in test ``setUp`` to discard stale state so each test
    begins with a cold cache.
    """

    _interaction_cache: dict[tuple[int, int], AffinityInteraction | None] | None = None

    @classmethod
    def clear_cache(cls) -> None:
        """Discard the cached interaction table. Must be called in test setUp."""
        cls._interaction_cache = None

    def _load_cache(self) -> dict[tuple[int, int], AffinityInteraction | None]:
        """Load all AffinityInteraction rows into the class-level cache dict.

        Subsequent calls return the already-populated dict without issuing
        any SQL.
        """
        if AffinityInteractionManager._interaction_cache is None:
            rows = list(self.select_related("source_affinity", "environment_affinity").all())
            AffinityInteractionManager._interaction_cache = {
                (row.source_affinity_id, row.environment_affinity_id): row for row in rows
            }
        return AffinityInteractionManager._interaction_cache

    def interaction_for(
        self,
        source_affinity: Affinity,
        environment_affinity: Affinity,
    ) -> AffinityInteraction | None:
        """Return the AffinityInteraction row for (source, environment), or None.

        All 9 (or fewer) rows are loaded on the first call and cached for
        the process lifetime. Subsequent calls are O(1) dict lookups with
        zero SQL queries.

        Call ``AffinityInteraction.objects.clear_cache()`` in test setUp to
        reset between tests.
        """
        cache = self._load_cache()
        key = (source_affinity.pk, environment_affinity.pk)
        # Use a module-level sentinel so None can be cached for unknown pairs.
        result = cache.get(key, _MISSING)
        if result is _MISSING:
            # Pair not in the table at all — cache a None sentinel.
            cache[key] = None
            return None
        return result  # type: ignore[return-value]


class AffinityInteraction(SharedMemoryModel):
    """An authored directed-pair row read by the resonance-environment primitive.

    source_affinity      — the caster's dominant magic affinity.
    environment_affinity — the place's affinity tag.
    valence              — ALIGNED (amplifies) or OPPOSED.
    kind                 — AMPLIFY / REJECT / REPEL / CORRUPT.
    aggressor            — who acts on whom (ENVIRONMENT or CASTER).
    severity_multiplier  — scales the effect magnitude; default 1.00.

    Unique per ordered (source_affinity, environment_affinity) pair.
    """

    source_affinity = models.ForeignKey(
        "magic.Affinity",
        on_delete=models.PROTECT,
        related_name="interactions_as_source",
        help_text="The caster's magic affinity.",
    )
    environment_affinity = models.ForeignKey(
        "magic.Affinity",
        on_delete=models.PROTECT,
        related_name="interactions_as_environment",
        help_text="The place's affinity.",
    )
    valence = models.CharField(
        max_length=16,
        choices=ResonanceValence.choices,
        help_text="Whether the pair is aligned or opposed.",
    )
    kind = models.CharField(
        max_length=16,
        choices=AffinityInteractionKind.choices,
        help_text="The nature of the interaction (amplify, reject, repel, corrupt).",
    )
    aggressor = models.CharField(
        max_length=16,
        choices=AffinityInteractionAggressor.choices,
        help_text="Whether the environment acts on the caster, or vice versa.",
    )
    severity_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Scales the interaction's effect magnitude.",
    )
    consequence_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resonance_interactions",
        help_text=(
            "OPPOSED backfire pool for this pairing. Null = inert "
            "(CORRUPT-deferred pairs, or pairings with no authored content yet)."
        ),
    )
    caster_dominance_defiles = models.BooleanField(
        default=False,
        help_text=(
            "When True, a CASTER_DOMINANT caster overpowers the place and DEFILES it "
            "(degrade place cascade + spread caster resonance + accrue corruption) instead "
            "of the environment acting. Authored True only for the Abyssal-caster OPPOSED "
            "pairs (#4 Abyssal->Celestial, #6 Abyssal->Primal). Default False keeps "
            "non-Abyssal casters from ever overpowering a place."
        ),
    )

    objects = AffinityInteractionManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_affinity", "environment_affinity"],
                name="unique_affinity_interaction_pair",
            )
        ]

    @cached_property
    def cached_alignment_boon_tiers(self) -> list[ResonanceAlignmentBoonTier]:
        """Cached list of all ResonanceAlignmentBoonTier rows for this interaction.

        Per-instance cache via ``cached_property`` — naturally isolated between
        instances and between test cases (each test creates fresh instances).
        Repeated access on the same instance issues zero SQL after the first call.
        """
        return list(self.alignment_boon_tiers.order_by("min_magnitude").all())

    def __str__(self) -> str:
        return (
            f"{self.source_affinity.name}->{self.environment_affinity.name}: "
            f"{self.valence}/{self.kind}"
        )


class ResonanceEnvironmentConfig(SharedMemoryModel):
    """Staff-tunable singleton (pk=1) for the resonance-environment primitive.

    Scalar coefficients that convert place_magnitude, caster alignment, and
    severity_multiplier into raw severity and backfire check difficulty. All
    values have sane defaults so the low/high room tiers in the story-slice
    seed produce DISTINCT difficulties without any staff configuration.

    Default rationale
    -----------------
    base_coefficient = 1.000
        Neutral pass-through. ``raw_severity = place_magnitude
        * caster_alignment * severity_multiplier * base_coefficient``.
        Staff may scale up (more lethal) or down (forgiving) globally.

    caster_power_scalar = 0.500
        A caster at 100% relevant aura counts as strength 50 on a 0-100
        magnitude scale. This keeps the default balanced_band (10) meaningful:
        a mid-tier caster (strength ~50) vs a low room (magnitude ~10) is
        CASTER_DOMINANT; vs a high room (magnitude ~80) is PLACE_DOMINANT.

    balanced_band = 10
        |caster_strength - place_magnitude| ≤ 10 → BALANCED direction.
        Low rooms (~10) and high rooms (~80) are 70 apart — far outside the
        band — so they always resolve to different directions, guaranteeing
        distinct difficulty paths in the story slice.

    backfire_base_difficulty = 30
        OPPOSED checks start at 30 (moderate challenge, below the typical
        trained-skill ceiling of ~60). Staff can raise for a harsher baseline.

    backfire_difficulty_per_magnitude = 0.500
        Added linearly: ``difficulty = base + round(magnitude * this)``.
        Low room (magnitude 10): +5 → total 35.
        High room (magnitude 80): +40 → total 70.
        The high-room backfire is dramatically harder, producing visibly
        distinct outcomes in the story-slice test matrix.

    Access via ``get_resonance_environment_config()`` in
    ``world.magic.services.resonance_environment``.
    """

    base_coefficient = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("1.000"),
        help_text=(
            "Scales place_magnitude * caster_alignment * severity_multiplier "
            "into raw severity. 1.000 is a neutral pass-through."
        ),
    )
    caster_power_scalar = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.500"),
        help_text=(
            "Multiplies caster aura% into the caster-strength proxy used for "
            "the defilement (CASTER_DOMINANT) magnitude comparison. "
            "Default 0.500: 100% aura → strength 50."
        ),
    )
    balanced_band = models.PositiveIntegerField(
        default=10,
        help_text=(
            "|caster_strength - place_magnitude| within this threshold → "
            "BALANCED direction. Default 10."
        ),
    )
    backfire_base_difficulty = models.PositiveIntegerField(
        default=30,
        help_text=(
            "Base target_difficulty for OPPOSED perform_check backfire rolls. "
            "Default 30 (moderate challenge)."
        ),
    )
    backfire_difficulty_per_magnitude = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.500"),
        help_text=(
            "Added to backfire_base_difficulty: "
            "difficulty = base + round(magnitude * this). "
            "Default 0.500: magnitude 10 → +5 (total 35); magnitude 80 → +40 (total 70)."
        ),
    )
    defile_degrade_per_cast = models.PositiveIntegerField(
        default=6,
        help_text=(
            "Points removed from the place's opposed resonance per defiling cast "
            "(effective value floors at 0)."
        ),
    )
    defile_spread_per_cast = models.PositiveIntegerField(
        default=6,
        help_text="Points added to the caster's Abyssal resonance on the room per defiling cast.",
    )
    defile_corruption_per_cast = models.PositiveIntegerField(
        default=2,
        help_text=(
            "Extra corruption accrued to the caster per defiling cast (atop the baseline "
            "abyssal-cast accrual), routed through CORRUPTION_ACCRUING."
        ),
    )

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resonance_environment_config_edits",
    )

    def __str__(self) -> str:
        return f"ResonanceEnvironmentConfig(pk={self.pk})"


class ResonanceAlignmentBoonTierManager(SharedMemoryManager):
    """Manager for ResonanceAlignmentBoonTier with a cached distinct-template set.

    Test-isolation: the cross-process cache is stored as a class-level
    ``_templates_cache`` attribute (``None`` until first loaded). Call
    ``clear_cache()`` in test ``setUp`` to discard stale state so each test
    begins with a cold cache.
    """

    _templates_cache: frozenset[ConditionTemplate] | None = None

    @classmethod
    def clear_cache(cls) -> None:
        """Discard the cached template set. Must be called in test setUp."""
        cls._templates_cache = None

    def boon_condition_templates(self) -> frozenset[ConditionTemplate]:
        """Return the distinct set of ConditionTemplate instances referenced by all boon tiers.

        Loaded on the first call and cached for the process lifetime. Subsequent
        calls are zero SQL queries. Call ``clear_cache()`` in test setUp to reset.
        """
        if ResonanceAlignmentBoonTierManager._templates_cache is None:
            rows = list(self.select_related("condition_template").all())
            ResonanceAlignmentBoonTierManager._templates_cache = frozenset(
                row.condition_template for row in rows
            )
        return ResonanceAlignmentBoonTierManager._templates_cache


class ResonanceAlignmentBoonTier(SharedMemoryModel):
    """Authored: which named buff ConditionTemplate an ALIGNED pairing grants
    at or above a magnitude threshold. Few rows, staff-tunable.

    affinity_interaction — must reference an ALIGNED (diagonal) interaction row.
    min_magnitude        — applies when evaluated magnitude >= this value.
                           Highest matching tier wins (selection done in Python).
    condition_template   — the named, player-visible buff applied while present.

    Unique per (affinity_interaction, min_magnitude) pair.
    """

    objects = ResonanceAlignmentBoonTierManager()

    affinity_interaction = models.ForeignKey(
        "magic.AffinityInteraction",
        on_delete=models.CASCADE,
        related_name="alignment_boon_tiers",
        help_text="Must reference an ALIGNED (diagonal) interaction row.",
    )
    min_magnitude = models.PositiveIntegerField(
        help_text=(
            "Applies when evaluated magnitude >= this value. "
            "Highest matching tier wins (selection done in Python)."
        ),
    )
    condition_template = models.ForeignKey(
        "conditions.ConditionTemplate",
        on_delete=models.PROTECT,
        related_name="resonance_alignment_tiers",
        help_text="The named, player-visible buff applied while present.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["affinity_interaction", "min_magnitude"],
                name="unique_alignment_boon_tier_threshold",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if (
            self.affinity_interaction_id is not None
            and self.affinity_interaction.valence != ResonanceValence.ALIGNED
        ):
            raise ValidationError(
                {
                    "affinity_interaction": (
                        "ResonanceAlignmentBoonTier requires an ALIGNED interaction row; "
                        f"got valence='{self.affinity_interaction.valence}'."
                    )
                }
            )

    def __str__(self) -> str:
        return (
            f"BoonTier({self.affinity_interaction_id}, "
            f"min={self.min_magnitude}, "
            f"condition={self.condition_template_id})"
        )
