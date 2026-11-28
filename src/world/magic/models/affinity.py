"""Affinity and Resonance domain models.

Affinities are the three magical sources (Celestial, Primal, Abyssal).
Resonances are style tags that contribute to affinities and have opposing pairs.
Both are proper domain models replacing the old ModifierTarget-based pattern.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils.functional import cached_property

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from core.testing import register_test_cache_flusher
from world.contributors.models import CreditedContent
from world.magic.constants import AFFINITY_ABYSSAL, AFFINITY_CELESTIAL, AFFINITY_PRIMAL
from world.magic.exceptions import AffinityNotConfigured
from world.magic.skill_choices import (
    MAGIC_SKILL_CHOICES,
    MAGIC_SKILL_ERROR_MESSAGES,
    MAGIC_SKILL_HELP,
)


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
    unsettled_tolerance_percent = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(100)],
        verbose_name="Range before Unsettled (percentage points)",
        help_text=(
            "How far another affinity may grow past its settled share before a character "
            "whose main affinity is this one is Unsettled. Blank uses the general value "
            "from the drift configuration."
        ),
    )
    unsettled_step_percent = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        verbose_name="Each further step (percentage points)",
        help_text=(
            "Percentage points past the range that add one step of severity, for a "
            "character whose main affinity is this one. Blank uses the general value "
            "from the drift configuration."
        ),
    )
    claim_verb = models.CharField(
        max_length=30,
        blank=True,
        db_default="",
        # No angle brackets: the admin renders help text as HTML, so a placeholder in angle
        # brackets would vanish from the page.
        help_text='The verb a player reads when a mark in this affinity pays, as in "You gloat."',
    )
    earn_rate_percent = models.PositiveSmallIntegerField(
        default=100,
        db_default=100,
        help_text=(
            "How much of a resonance of this affinity a character actually gets when she earns "
            "it, as a percentage, whatever her own main affinity. 100 is as authored, 150 is "
            "half as much again. Staff grants, character creation and resonance that is only "
            "being moved or converted are never scaled."
        ),
    )
    kindled_boost_percent = models.PositiveSmallIntegerField(
        default=100,
        db_default=100,
        verbose_name="Kindled boost",
        help_text=(
            "A percentage. 100 leaves a kindled resonance of this affinity as strong as any other."
        ),
    )
    learn_rate_percent = models.PositiveSmallIntegerField(
        default=100,
        db_default=100,
        help_text=(
            "How much technique training progress a character whose main affinity is this "
            "one gets from the same training, as a percentage. 100 is as authored. The weekly "
            "training limit and the action point cost still count the unscaled points."
        ),
    )
    ritual_partner_fatigue = models.SmallIntegerField(
        default=0,
        db_default=0,
        help_text=(
            "What an Anima ritual of this affinity's resonance does to the partner who joins "
            "in. A positive number adds that much fatigue to the partner, a negative number "
            "eases that much, and zero does nothing."
        ),
    )
    gain_fatigue = models.PositiveSmallIntegerField(
        default=0,
        db_default=0,
        help_text=(
            "What one gain in this affinity's resonance costs whoever pays for it, in "
            "fatigue. 0 charges nothing. A positive number is the base cost, before any "
            "fatigue reduction the payer has."
        ),
    )
    skill = models.OneToOneField(
        "arxii.Skill",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="affinity",
        limit_choices_to=MAGIC_SKILL_CHOICES,
        error_messages=MAGIC_SKILL_ERROR_MESSAGES,
        help_text=(
            "The affinity's own skill, such as Villainy, Heroism or Reflection. Every "
            "resonance a character earns or spends in this affinity adds it to its bonus "
            "check. One affinity per skill. "
            f"{MAGIC_SKILL_HELP}"
        ),
    )
    spend_worth_floor_percent = models.PositiveSmallIntegerField(
        default=0,
        db_default=0,
        help_text=(
            "The least a pull or a kindled cast of this resonance is worth, as a percentage, "
            "whatever the bonus check rolls. 0 sets no floor. An Abyssal floor keeps its "
            "magic strong even on a poor roll."
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

    def clean(self) -> None:
        """An affinity's skill is no other magical roll's skill (#5308).

        The four magic skill pickers refuse an affinity's skill; this refuses the other way
        round, so a skill a magical roll already adds never becomes an affinity's too. The
        bonus check would otherwise count one skill twice.
        """
        # Deferred: these models import this module.
        from world.covenants.models import CombatStyle  # noqa: PLC0415
        from world.magic.models.magic_activity import MagicActivitySkill  # noqa: PLC0415
        from world.magic.models.resonance_environment import (  # noqa: PLC0415
            ResonanceEnvironmentConfig,
        )
        from world.magic.models.ritual_check_config import RitualCheckConfig  # noqa: PLC0415
        from world.magic.models.techniques import Technique, TechniqueStyle  # noqa: PLC0415

        super().clean()
        if self.skill_id is None:
            return
        skill_id = self.skill_id
        if (
            TechniqueStyle.objects.filter(skill_id=skill_id).exists()
            or Technique.objects.filter(skill_id=skill_id).exists()
            or MagicActivitySkill.objects.filter(skill_id=skill_id).exists()
            or ResonanceEnvironmentConfig.objects.filter(harvest_skill_id=skill_id).exists()
            or RitualCheckConfig.objects.filter(skill_id=skill_id).exists()
            or CombatStyle.objects.filter(skill_id=skill_id).exists()
        ):
            raise ValidationError(
                {
                    "skill": (
                        "A casting style, technique, magical activity, ritual, combat style or "
                        "the harvest roll already adds this skill. Give the affinity a skill "
                        "of its own."
                    )
                }
            )


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
        help_text=(
            "Players read this under the picker when they choose this resonance. Write good "
            "and bad examples of acts."
        ),
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
    feeling = models.ForeignKey(
        "arxii.Property",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feeling_of_resonances",
        help_text=("Conditions carrying this property count as this resonance's feeling."),
    )
    impulse_text = models.TextField(
        blank=True,
        help_text=(
            "The words a character carrying corruption in this resonance is sent, once per "
            "scene, when something this resonance cares about is present. Written in second "
            "person. Blank uses a plain default line."
        ),
    )
    color_hex = models.CharField(
        max_length=7,
        default="#8C8C8C",
        db_default="#8C8C8C",
        validators=[
            RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Must be a hex color (#RRGGBB)."),
        ],
        verbose_name="Colour",
        help_text="Picked with a colour picker. The aura is drawn in it.",
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
