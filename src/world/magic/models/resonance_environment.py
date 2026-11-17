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
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils.functional import cached_property

from core.managers import ArxSharedMemoryManager, GuardedSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.testing import register_test_cache_flusher
from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceValence,
)
from world.magic.models.fall_redemption import ConversionType
from world.magic.skill_choices import (
    MAGIC_PICKER_SKILL_CHOICES,
    MAGIC_PICKER_SKILL_ERROR_MESSAGES,
    MAGIC_PICKER_SKILL_HELP,
)

if TYPE_CHECKING:
    from world.conditions.models import ConditionTemplate
    from world.magic.models.affinity import Affinity

# Sentinel used by AffinityInteractionManager.interaction_for to distinguish
# "key absent from cache" from "key present with None value".
_MISSING: object = object()


class AffinityInteractionManager(GuardedSharedMemoryManager):
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


register_test_cache_flusher(AffinityInteractionManager.clear_cache)


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
        "arxii.Affinity",
        on_delete=models.PROTECT,
        related_name="interactions_as_source",
        help_text="The caster's magic affinity.",
    )
    environment_affinity = models.ForeignKey(
        "arxii.Affinity",
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
    conversion_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fall/Redemption conversion multiplier along this pair. Null = no conversion.",
    )
    conversion_type = models.CharField(
        max_length=16,
        choices=ConversionType.choices,
        blank=True,
        help_text="Whether converting along this pair is a Fall or a Redemption. Blank = none.",
    )
    consequence_pool = models.ForeignKey(
        "arxii.ConsequencePool",
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
            ),
            models.CheckConstraint(
                check=(
                    models.Q(conversion_multiplier__isnull=False) & ~models.Q(conversion_type="")
                    | models.Q(conversion_multiplier__isnull=True, conversion_type="")
                ),
                name="affinity_interaction_conversion_pair_complete",
            ),
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

    objects = ArxSharedMemoryManager()

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
    backfire_base_difficulty_level = models.PositiveSmallIntegerField(
        default=2,
        help_text=(
            "The level an OPPOSED perform_check backfire roll is made against (0 = no "
            "difficulty): the roll meets that level's baseline, plus the per-magnitude "
            "increment below. Default level 2."
        ),
    )
    backfire_difficulty_per_magnitude_tenths = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("1.000"),
        help_text=(
            "Tenths of one level's width added to the backfire base level's difficulty for "
            "each point of magnitude: difficulty = base level's baseline + magnitude x this "
            "tenths of the base level's width. Default 1.000: magnitude 10 adds 10 tenths, "
            "one whole level's width; magnitude 80 adds 80 tenths, eight."
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

    # --- Gift substance (#5018, #5125): place discount and unmet surroundings ---
    substance_place_cap_pct = models.PositiveSmallIntegerField(
        verbose_name="Largest place discount or surcharge (%)",
        default=50,
        validators=[MaxValueValidator(100)],
        help_text=(
            "Largest discount (a place of matching magic) or surcharge (a hostile place) on "
            "calling up, as a percent. The place's magnitude sets it, up to this. 0 to 100."
        ),
    )
    unmet_surroundings_penalty_pct = models.PositiveSmallIntegerField(
        verbose_name="Unmet surroundings penalty (% of a typical roll)",
        default=100,
        help_text=(
            "A technique's unmet surroundings restriction costs this percent of a typical "
            "roll at the caster's level."
        ),
    )

    # --- Substances and Primum (#5125) ---
    substance_related_share_pct = models.PositiveSmallIntegerField(
        verbose_name="Related substance gives (% of full benefit)",
        default=50,
        validators=[MaxValueValidator(100)],
        help_text=(
            "How much of a Primum source's benefit a caster gets from a substance related to "
            "her gift's own, as a percent. A matching substance gives full benefit. 0 to 100."
        ),
    )
    substance_power_cap = models.PositiveSmallIntegerField(
        verbose_name="Most power Primum can add",
        default=12,
        help_text=(
            "The most power all of a caster's Primum sources add together, before her gift "
            "thread scales it."
        ),
    )
    substance_call_up_anima = models.PositiveSmallIntegerField(
        verbose_name="Anima to call up Primum",
        default=3,
        help_text=(
            "Anima one call-up costs, raising the place's Primum by one step. Shared by every "
            "caster who calls it up together; never refused for lack of anima."
        ),
    )
    harvest_check_type = models.ForeignKey(
        "arxii.CheckType",
        verbose_name="Check rolled to harvest Primum",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The check a harvester rolls to take Primum. Unset: nothing can be harvested.",
    )
    harvest_skill = models.ForeignKey(
        "arxii.Skill",
        verbose_name="Skill added to the harvest roll",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        limit_choices_to=MAGIC_PICKER_SKILL_CHOICES,
        error_messages=MAGIC_PICKER_SKILL_ERROR_MESSAGES,
        help_text=(
            "The magical skill a harvester adds to the harvest roll. "
            f"{MAGIC_PICKER_SKILL_HELP} Unset: nothing can be harvested."
        ),
    )
    harvest_thread_bonus = models.PositiveSmallIntegerField(
        verbose_name="Harvest bonus from the gift thread",
        default=5,
        help_text=(
            "Bonus a harvester gets on the roll for a gift thread of the substance, scaled by "
            "her thread level."
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


class ResonanceAlignmentBoonTierManager(GuardedSharedMemoryManager):
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


register_test_cache_flusher(ResonanceAlignmentBoonTierManager.clear_cache)


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
        "arxii.AffinityInteraction",
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
        "arxii.ConditionTemplate",
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
