"""
Distinctions system models.

This module contains models for character advantages, disadvantages, and
defining characteristics (merits/flaws equivalent):
- DistinctionCategory: Categories for organizing distinctions
- DistinctionTag: Tags for filtering and search
- Distinction: Individual advantages/disadvantages
- DistinctionEffect: Mechanical effects of distinctions
- DistinctionEffectRankSize: The size a sized effect has from one rank up (#4660)
- Distinction.mutually_exclusive_with: symmetrical self-referential M2M for mutually
  exclusive distinction pairs (not a separate model)
- CharacterDistinction: A character's taken distinctions
- CharacterDistinctionOther: Freeform "Other" entries pending staff mapping
- SheetUpdateRequest: Player-initiated requests to add/remove distinctions
"""

from typing import ClassVar

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
from django.utils.functional import cached_property

from core.descriptors import ReverseOneToOneOrNone
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from evennia_extensions.cached_property import PrunedCachedProperty
from evennia_extensions.mixins import RelatedCacheClearingMixin
from world.character_creation.constants import FinalTouchesPrompt
from world.checks.constants import ModifierSize
from world.contributors.models import CreditedContent
from world.distinctions.types import (
    DistinctionOrigin,
    OtherStatus,
    SheetUpdateRequestStatus,
    SheetUpdateRequestType,
)
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME
from world.mechanics.derived_amount_models import DerivedAmountMixin
from world.secrets.constants import SecretLevel

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
DISTINCTION_MODEL = "arxii.Distinction"
CHARACTER_SHEET_MODEL = "arxii.CharacterSheet"


class DistinctionCategoryManager(NaturalKeyManager):
    """Manager for DistinctionCategory with natural key support."""


class DistinctionCategory(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    A category for organizing distinctions.

    Categories are database-defined so new ones can be added via admin.
    The initial set: Physical, Mental, Personality, Social, Background, Arcane.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Display name for this category.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for this category.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what distinctions belong in this category.",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order in which to display this category (lower = first).",
    )

    objects = DistinctionCategoryManager()

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "Distinction Category"
        verbose_name_plural = "Distinction Categories"

    class NaturalKeyConfig:
        fields = ["slug"]

    def __str__(self) -> str:
        return self.name


class DistinctionTagManager(NaturalKeyManager):
    """Manager for DistinctionTag with natural key support."""


class DistinctionTag(NaturalKeyMixin, SharedMemoryModel):
    """
    A tag for filtering and searching distinctions.

    Tags allow cross-cutting concerns (e.g., "combat-relevant" can tag
    distinctions from multiple categories).
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Display name for this tag.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for this tag.",
    )

    objects = DistinctionTagManager()

    class Meta:
        verbose_name = "Distinction Tag"
        verbose_name_plural = "Distinction Tags"

    class NaturalKeyConfig:
        fields = ["slug"]

    def __str__(self) -> str:
        return self.name


class DistinctionManager(NaturalKeyManager):
    """Manager for Distinction with natural key support."""


DERIVED_AMOUNT_SIZE_REFUSAL = (
    "An effect derives its amount or takes a size, not both; clear one of them."
)
MANEUVER_EFFECT_SIZE_REFUSAL = (
    "Only damage, to-hit and partial protection effects take a size; clear the size."
)


class Distinction(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    An individual advantage, disadvantage, or defining characteristic.

    Distinctions are the Arx II equivalent of merits/flaws. They can have
    positive costs (advantages that cost points) or negative costs
    (disadvantages that reimburse points).
    """

    name = models.CharField(
        max_length=100,
        help_text="Display name for this distinction.",
    )
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for this distinction.",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this distinction represents.",
    )
    category = models.ForeignKey(
        DistinctionCategory,
        on_delete=models.PROTECT,
        related_name="distinctions",
        help_text="Category this distinction belongs to.",
    )
    cost_per_rank = models.IntegerField(
        default=0,
        help_text="Cost per rank. Positive costs points, negative reimburses.",
    )
    max_rank = models.PositiveIntegerField(
        default=1,
        help_text="Maximum rank. 1 means binary (have it or don't).",
    )

    # Variant system - allows "Noble Blood" to have variants like "Noble Blood (Valardin)"
    parent_distinction = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="variants",
        help_text="Parent distinction if this is a variant.",
    )
    allow_other = models.BooleanField(
        default=False,
        help_text="True if players can specify a custom 'other' value.",
    )
    variants_are_mutually_exclusive = models.BooleanField(
        default=False,
        help_text="If True, only one variant of this parent can be selected per character.",
    )

    # Mutual exclusions - symmetrical M2M
    mutually_exclusive_with = models.ManyToManyField(
        "self",
        symmetrical=True,
        blank=True,
        help_text="Distinctions that are mutually exclusive with this one.",
    )

    # Automation flags
    is_automatic = models.BooleanField(
        default=False,
        help_text="True if this distinction is automatically granted.",
    )
    requires_slot_filled = models.BooleanField(
        default=False,
        help_text="True if this requires a slot selection to be valid.",
    )

    # Tags for filtering
    tags = models.ManyToManyField(
        DistinctionTag,
        blank=True,
        related_name="distinctions",
        help_text="Tags for filtering and searching.",
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this distinction is available for selection.",
    )
    # A distinctive physical feature (#3739). ``taken_per_feature`` rows are held once
    # per feature (a trait row or a marking) rather than once per character; the
    # ``opens_feature`` row is the one-point "Make it distinctive" pick that opens a
    # feature's description, every option of its trait and the axis rows; a
    # ``requires_feature_opened`` row (Alluring, Menacing, Majestic) may be held on a
    # feature only where an ``opens_feature`` row is held. ``cg_max_rank`` caps the
    # rank character creation allows below ``max_rank`` (3 in CG, higher in play).
    taken_per_feature = models.BooleanField(
        default=False,
        help_text=(
            "Held once per feature (a trait row or a marking), not once per character; "
            "offered on every feature row of the Appearance chapter (#3739)."
        ),
    )
    opens_feature = models.BooleanField(
        default=False,
        help_text=(
            "The one-point 'Make it distinctive' pick: holding it on a feature opens the "
            "feature's description, every option of its trait, and the axis rows (#3739)."
        ),
    )
    requires_feature_opened = models.BooleanField(
        default=False,
        help_text=(
            "May be held on a feature only where the opens_feature row is held on the "
            "same feature (the Alluring / Menacing / Regal axes, #3739)."
        ),
    )
    cg_max_rank = models.PositiveIntegerField(
        default=0,
        help_text=(
            "The highest rank character creation allows, when lower than max_rank; "
            "0 means max_rank applies in CG too (#3739: axes stop at 3 in CG)."
        ),
    )
    is_teachable = models.BooleanField(
        default=False,
        help_text="If True, a PC who holds this distinction can teach it to others "
        "or remove it for them, without a GM. (PC teaching flow is deferred.)",
    )

    # Privacy (#1334): instead of a public/private flag, a sensitive kind *relocates* into a
    # Secret. Most kinds are public; criminal / scandalous kinds set ``secret_by_default`` so
    # taking one auto-mints a Secret (at ``default_secret_level``) that drops off the public
    # distinctions list and is learned through the clue loop. A player may also gate a
    # normally-public distinction per character (mints a Secret on that CharacterDistinction).
    secret_by_default = models.BooleanField(
        default=False,
        help_text="Taking this kind auto-mints a Secret (criminal/scandalous kinds).",
    )
    default_secret_level = models.PositiveSmallIntegerField(
        choices=SecretLevel.choices,
        default=SecretLevel.UNCOMMON_KNOWLEDGE,
        help_text="Level for the auto-minted Secret when secret_by_default.",
    )

    # The Final Touches chapter (#4846, slice 5 of #4813): a card may ask one optional
    # question at Final Touches, answered or skipped there. Set by staff on the
    # Distinction Builder; read by ``character_creation.offers.final_touches_prompts``
    # for the cards a draft holds, and by finalize to decide what the answer writes.
    final_touches_prompt = models.CharField(
        max_length=20,
        choices=FinalTouchesPrompt.choices,
        blank=True,
        default="",
        help_text="The optional question this card asks at Final Touches, if any.",
    )

    objects = DistinctionManager()

    class Meta:
        verbose_name = "Distinction"
        verbose_name_plural = "Distinctions"

    class NaturalKeyConfig:
        fields = ["slug"]
        dependencies = ["arxii.DistinctionCategory"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_variant_parent(self) -> bool:
        """Check if this distinction has variants (computed from related objects)."""
        return self.variants.exists()

    # The ``currency.DistinctionStartingGrant`` sidecar (#4062), or ``None``: read
    # by the serializers' effects summary without importing ``world.currency``.
    starting_grant_or_none = ReverseOneToOneOrNone("starting_grant")
    # The finalize-time grants of #4852 (slice 6 of #4813), each ``None`` when the card
    # carries none: a starting prestige (``societies.DistinctionPrestigeGrant``), a
    # membership (``societies.DistinctionOrganizationGrant``), a bonus on the Path's
    # stronger Aspect (``classes.DistinctionPathAspectGrant``). Read by the effects summary
    # and by ``character_creation.offers`` without importing either app.
    prestige_grant_or_none = ReverseOneToOneOrNone("prestige_grant")
    organization_grant_or_none = ReverseOneToOneOrNone("organization_grant")
    path_aspect_grant_or_none = ReverseOneToOneOrNone("path_aspect_grant")
    # And #4856: a second face (``scenes.DistinctionPersonaGrant``) and a tie with an
    # organization of the realm (``societies.DistinctionOrganizationTie``).
    persona_grant_or_none = ReverseOneToOneOrNone("persona_grant")
    organization_tie_or_none = ReverseOneToOneOrNone("organization_tie")

    @PrunedCachedProperty
    def cached_item_grants(self) -> list:
        """This distinction's keepsake rows, with their templates (#4398, ADR-0298).

        The ``items.DistinctionItemGrant`` sidecar, read by the serializers' effects
        summary without importing ``world.items``. Fed cold by the list viewset's
        ``Prefetch`` into this attribute (templates joined), never one query per row
        there; this body is the fallback for a lone instance. Writes clear it through
        ``DistinctionItemGrant.related_cache_fields``.
        """
        return list(
            self.item_grants.filter(item_template__is_active=True).select_related("item_template")
        )

    @cached_property
    def cached_effects(self) -> list["DistinctionEffect"]:
        """Fallback for Prefetch(..., to_attr='cached_effects').

        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query with target and category select_related.
        """
        return list(self.effects.select_related("target__codex_entry", "target__category"))

    @cached_property
    def cached_tags(self) -> list["DistinctionTag"]:
        """Fallback for Prefetch(..., to_attr='cached_tags').

        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.
        """
        return list(self.tags.all())

    @cached_property
    def cached_variants(self) -> list["Distinction"]:
        """Fallback for Prefetch(..., to_attr='cached_variants').

        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.
        """
        return list(self.variants.filter(is_active=True))

    @cached_property
    def cached_mutually_exclusive_with(self) -> list["Distinction"]:
        """Fallback for Prefetch(..., to_attr='cached_mutually_exclusive_with').

        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.
        """
        return list(self.mutually_exclusive_with.all())

    @cached_property
    def cached_codex_grants(self) -> list:
        """Codex grants — the Prefetch/query shared interface (#2386).

        Authored content: negligible staleness on the identity-mapped row.
        """
        return list(self.codex_grants.all())

    @property
    def cg_ceiling(self) -> int:
        """The highest rank a draft may buy (#3739).

        ``cg_max_rank`` when it is set and lower than ``max_rank``, else
        ``max_rank``. The axes reach 5 in play and stop at 3 in CG, so the sync
        view and the Appearance leaf both read this rather than ``max_rank``;
        every distinction that never set ``cg_max_rank`` is unaffected.
        """
        if self.cg_max_rank and self.cg_max_rank < self.max_rank:
            return self.cg_max_rank
        return self.max_rank

    def calculate_total_cost(self, rank: int) -> int:
        """
        Calculate total cost for a given rank.

        Args:
            rank: The rank to calculate cost for.

        Returns:
            Total cost (cost_per_rank * rank).
        """
        return self.cost_per_rank * rank

    def get_mutually_exclusive(self) -> models.QuerySet["Distinction"]:
        """
        Get all distinctions that are mutually exclusive with this one.

        Returns:
            QuerySet of mutually exclusive distinctions.
        """
        return self.mutually_exclusive_with.all()


class DistinctionEffect(NaturalKeyMixin, CreditedContent, DerivedAmountMixin, SharedMemoryModel):
    """
    A mechanical effect granted by a distinction.

    Effects modify a specific ModifierTarget (stats, affinities, resonances, etc.).
    The effect type is now implicit from target.category. Effects can scale
    linearly with rank (value_per_rank) or use custom scaling (scaling_values).
    """

    distinction = models.ForeignKey(
        Distinction,
        on_delete=models.CASCADE,
        related_name="effects",
        help_text="The distinction this effect belongs to.",
    )
    target = models.ForeignKey(
        "arxii.ModifierTarget",
        on_delete=models.PROTECT,
        related_name="distinction_effects",
        help_text="The modifier type this effect targets.",
    )
    value_per_rank = models.IntegerField(
        null=True,
        blank=True,
        help_text="Value per rank for linear scaling.",
    )
    scaling_values = models.JSONField(
        null=True,
        blank=True,
        help_text="List of values for non-linear scaling [rank1, rank2, ...].",
    )
    amplifies_sources_by = models.IntegerField(
        null=True,
        blank=True,
        help_text="Bonus to OTHER sources of this modifier type (+2 = all other Allure +2).",
    )
    grants_immunity_to_negative = models.BooleanField(
        default=False,
        help_text="If true, character is immune to negative modifiers of this type.",
    )
    modifier_size = models.PositiveSmallIntegerField(
        choices=ModifierSize.choices,
        null=True,
        blank=True,
        help_text=(
            "How big this effect's bonus or penalty is at rank 1, for its holder's "
            "level (#4638). Read when the target is a check type (the check lane) or a "
            "stat (the stat lane, #4726): the holder's level and the size read that "
            "lane's modifier value table, and the authored "
            "rank-1 value's sign says bonus or penalty. Rank never multiplies a sized "
            "effect (#4660): a later rank takes its size from this effect's rank sizes "
            "(the highest authored rank at or below it), and with none authored every "
            "rank uses this size. Blank keeps the flat authored per-rank value. Paramount "
            "is reached only through a vow and cannot be authored here."
        ),
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this effect does.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["distinction", "target"]
        dependencies = [
            DISTINCTION_MODEL,
            "arxii.ModifierTarget",
            "arxii.CheckType",
            "arxii.Trait",
            "arxii.Facet",
        ]

    class Meta:
        unique_together = ["distinction", "target"]
        verbose_name = "Distinction Effect"
        verbose_name_plural = "Distinction Effects"

    def __str__(self) -> str:
        return f"{self.distinction.name}: {self.target.name}"

    def clean(self) -> None:
        """Refuse Paramount (only a vow's size step reaches it, #4551 section 5.3) and a
        size on a maneuver effect target whose kind has no value lane (#4783 decision 9;
        damage, to-hit and partial protection have one since #4876)."""
        super().clean()
        if self.modifier_size == ModifierSize.PARAMOUNT:
            raise ValidationError(
                {"modifier_size": "Paramount is reached only through a vow's size step."}
            )
        if self.modifier_size is not None and self.takes_flat_amount_only:
            raise ValidationError({"modifier_size": MANEUVER_EFFECT_SIZE_REFUSAL})
        errors = self.clean_derived_amount(self.target if self.target_id else None)
        if self.has_amount_input and self.modifier_size is not None:
            errors["modifier_size"] = DERIVED_AMOUNT_SIZE_REFUSAL
        if errors:
            raise ValidationError(errors)

    @property
    def targets_maneuver_effect(self) -> bool:
        """Whether this effect's target is in the maneuver effect category (#4783)."""
        return self.target_id is not None and (
            self.target.category.name == MANEUVER_EFFECT_CATEGORY_NAME
        )

    @property
    def takes_flat_amount_only(self) -> bool:
        """Whether a size is refused here: a maneuver effect target whose kind has no value
        lane (reach, escape, morale, surge, condition severity and duration; #4876)."""
        return self.targets_maneuver_effect and self.target.value_lane is None

    def get_value_at_rank(self, rank: int) -> int:
        """
        Get the effect value at a given rank.

        Args:
            rank: The rank to get the value for (1-indexed).

        Returns:
            The effect value at that rank.
        """
        if self.scaling_values and len(self.scaling_values) >= rank:
            return self.scaling_values[rank - 1]
        if self.value_per_rank is not None:
            return self.value_per_rank * rank
        return 0

    @PrunedCachedProperty
    def cached_rank_sizes(self) -> list["DistinctionEffectRankSize"]:
        """This effect's rank sizes (#4660, ADR-0298).

        Fed cold by ``get_modifier_breakdown``'s ``Prefetch`` into this attribute, never
        one query per effect there; this body is the fallback for a lone instance. Writes
        clear it through ``DistinctionEffectRankSize.related_cache_fields``.
        """
        return list(self.rank_sizes.all())

    def size_at_rank(self, rank: int) -> int | None:
        """The effect's size at ``rank`` on a check (#4660), or None when it is unsized.

        The highest authored ``DistinctionEffectRankSize`` at or below ``rank``, else
        ``modifier_size`` (the rank-1 size). Reads ``cached_rank_sizes``, so a caller that
        prefetched it runs no query here.
        """
        if self.modifier_size is None:
            return None
        size = self.modifier_size
        best_rank = 1
        for row in self.cached_rank_sizes:
            if best_rank < row.rank <= rank:
                best_rank = row.rank
                size = row.size
        return size


class DistinctionEffectRankSize(NaturalKeyMixin, RelatedCacheClearingMixin, SharedMemoryModel):
    """The size a sized distinction effect has from one rank up (#4660, slice 6 of #4551).

    Rank steps a sized effect up the size ladder, effect by effect; it never multiplies
    the table value (ADR-4660-A). Rank 1 is the effect's own ``modifier_size``; a row
    here names the size from its ``rank`` on, until a higher row takes over. A rank with
    no row keeps the size of the nearest lower rank that has one. Read only on the check
    lane, by ``DistinctionEffect.size_at_rank``.
    """

    effect = models.ForeignKey(
        DistinctionEffect,
        on_delete=models.CASCADE,
        related_name="rank_sizes",
        help_text="The sized distinction effect this rank's size belongs to.",
    )
    rank = models.PositiveSmallIntegerField(
        help_text=(
            "The rank this size starts at: 2 or more (rank 1 is the effect's own size), "
            "and no higher than the distinction's maximum rank."
        ),
    )
    size = models.PositiveSmallIntegerField(
        choices=ModifierSize.choices,
        help_text=(
            "The effect's size from this rank up, until a higher rank names another. "
            "Paramount is reached only through a vow and cannot be authored here."
        ),
    )

    objects = NaturalKeyManager()

    #: A write here clears the effect's ``cached_rank_sizes`` (ADR-0298 pairing), so the
    #: identity-mapped effect in a running server sees a size staff just authored.
    related_cache_fields: ClassVar[list[str]] = ["effect"]

    class NaturalKeyConfig:
        fields = ["effect", "rank"]
        dependencies = ["arxii.DistinctionEffect"]

    class Meta:
        ordering = ["effect_id", "rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["effect", "rank"],
                name="unique_distinction_effect_rank_size",
            ),
            models.CheckConstraint(
                condition=models.Q(rank__gte=2),
                name="distinction_effect_rank_size_rank_at_least_2",
            ),
            models.CheckConstraint(
                condition=~models.Q(size=ModifierSize.PARAMOUNT),
                name="distinction_effect_rank_size_not_paramount",
            ),
        ]
        verbose_name = "Distinction Effect Rank Size"
        verbose_name_plural = "Distinction Effect Rank Sizes"

    def __str__(self) -> str:
        return f"{self.effect} rank {self.rank}: {self.get_size_display()}"

    def clean(self) -> None:
        """Refuse rank 1, Paramount, a rank past the maximum, an unsized effect and a
        maneuver effect target whose kind has no value lane (#4783, #4876).

        Rank 1 and Paramount are also database constraints; refusing them here gives staff
        a sentence instead of the constraint's name.
        """
        super().clean()
        errors: dict[str, str] = {}
        if self.rank is not None and self.rank < 2:  # noqa: PLR2004 - rank 1 is modifier_size
            errors["rank"] = "Rank 1 is the effect's own size. Rank sizes start at rank 2."
        if self.size == ModifierSize.PARAMOUNT:
            errors["size"] = "Paramount is reached only through a vow's size step."
        if self.effect_id is not None:
            effect = self.effect
            if effect.modifier_size is None:
                # A form-wide error: the effect is a hidden field in the admin inline, and
                # an error on a hidden field is never shown to staff (#4660 live run).
                errors[NON_FIELD_ERRORS] = (
                    "This effect has no size, so it has no rank sizes. Give it a rank-1 size first."
                )
            elif effect.takes_flat_amount_only:
                errors[NON_FIELD_ERRORS] = MANEUVER_EFFECT_SIZE_REFUSAL
            elif effect.has_amount_input:
                errors[NON_FIELD_ERRORS] = DERIVED_AMOUNT_SIZE_REFUSAL
            max_rank = effect.distinction.max_rank
            if self.rank is not None and self.rank > max_rank:
                errors["rank"] = f"This distinction's maximum rank is {max_rank}."
        if errors:
            raise ValidationError(errors)


class CharacterDistinction(SharedMemoryModel):
    """
    A distinction granted to a character.

    This is character instance data, NOT a lookup table. It tracks which
    distinctions a character has, at what rank, and how they were acquired.
    """

    character = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="distinctions",
        help_text="The character sheet this distinction belongs to.",
    )
    distinction = models.ForeignKey(
        Distinction,
        on_delete=models.PROTECT,
        related_name="character_grants",
        help_text="The distinction granted to this character.",
    )
    rank = models.PositiveIntegerField(
        default=1,
        help_text="Current rank of this distinction (1 for binary distinctions).",
    )
    notes = models.TextField(
        max_length=280,
        blank=True,
        help_text="Player notes about this distinction.",
    )
    origin = models.CharField(
        max_length=30,
        choices=DistinctionOrigin.choices,
        default=DistinctionOrigin.CHARACTER_CREATION,
        help_text="How this character acquired the distinction.",
    )
    is_temporary = models.BooleanField(
        default=False,
        help_text="Whether this distinction is temporary (e.g., magical effect).",
    )
    # Privacy back-reference (#1334): when set, this distinction is *relocated* into the linked
    # Secret — it drops off the public distinctions list and is learned through the clue loop.
    # The FK's presence IS the secret-state (see ``is_secret``); there is no separate flag to
    # drift. SET_NULL so deleting the Secret simply makes the distinction public again.
    # A plain FK since #4528: one secret holds any number of the subject's distinctions
    # (staff tick them from the secret's side, ``set_secret_distinctions``); a distinction
    # sits in at most one.
    secret = models.ForeignKey(
        "arxii.Secret",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="distinctions",
        help_text="The Secret this distinction was relocated into; null = publicly visible.",
    )
    # Glimpse provenance (#2427): when set, this distinction was born in the
    # character's Glimpse (first magical awakening). The FK's presence IS the
    # linked state, mirroring ``secret`` above — no separate flag to drift.
    # SET_NULL so deleting the aura simply drops the provenance.
    from_glimpse = models.ForeignKey(
        "arxii.CharacterAura",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="glimpse_born_distinctions",
        help_text="The Glimpse (aura) this distinction was born in; null = no glimpse link.",
    )
    source_description = models.TextField(
        blank=True,
        help_text="Description of how the distinction was acquired (for gameplay).",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this distinction was granted.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this distinction was last modified.",
    )

    # The feature a per-feature distinction is aimed at (#3739): exactly one of these
    # when ``distinction.taken_per_feature``, neither otherwise. A trait row aims at
    # the FormTrait (the character's true form carries the value); a marking aims at
    # the FormMarking itself. FK direction per ADR-0010: this row is the specific side.
    feature_trait = models.ForeignKey(
        "arxii.FormTrait",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="feature_distinctions",
        help_text="The trait row this per-feature distinction is aimed at (#3739).",
    )
    feature_marking = models.ForeignKey(
        "arxii.FormMarking",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="feature_distinctions",
        help_text="The marking this per-feature distinction is aimed at (#3739).",
    )

    class Meta:
        constraints = [
            # A plain distinction is still held once per character; a per-feature one
            # once per feature (#3739). NULLs compare distinct in a unique constraint,
            # so each shape carries its own conditional constraint.
            models.UniqueConstraint(
                fields=["character", "distinction"],
                condition=models.Q(feature_trait__isnull=True, feature_marking__isnull=True),
                name="characterdistinction_unique_plain",
            ),
            models.UniqueConstraint(
                fields=["character", "distinction", "feature_trait"],
                condition=models.Q(feature_trait__isnull=False),
                name="characterdistinction_unique_per_trait",
            ),
            models.UniqueConstraint(
                fields=["character", "distinction", "feature_marking"],
                condition=models.Q(feature_marking__isnull=False),
                name="characterdistinction_unique_per_marking",
            ),
            models.CheckConstraint(
                check=~models.Q(feature_trait__isnull=False, feature_marking__isnull=False),
                name="characterdistinction_one_feature_at_most",
            ),
        ]
        verbose_name = "Character Distinction"
        verbose_name_plural = "Character Distinctions"

    @property
    def feature_label(self) -> str:
        """The feature this row is aimed at, for the sheet: a trait's name, a marking's, or ''."""
        if self.feature_trait_id is not None:
            return self.feature_trait.display_name
        if self.feature_marking_id is not None:
            return self.feature_marking.name
        return ""

    def __str__(self) -> str:
        rank_str = f" (Rank {self.rank})" if self.distinction.max_rank > 1 else ""
        return f"{self.distinction.name}{rank_str} on {self.character}"

    @property
    def is_secret(self) -> bool:
        """Whether this distinction has been relocated into a Secret (#1334).

        The presence of the ``secret`` FK is the source of truth — a secret distinction is
        hidden from the public distinctions list and surfaces on the secret tab once learned.
        """
        return self.secret_id is not None

    def calculate_total_cost(self) -> int:
        """
        Calculate total cost for this character's distinction at their rank.

        Returns:
            Total cost (cost_per_rank * rank).
        """
        return self.distinction.calculate_total_cost(self.rank)


class CharacterDistinctionOther(SharedMemoryModel):
    """
    A freeform 'Other' distinction entry pending staff mapping.

    When a player selects 'Other' for a variant distinction, they enter
    freeform text. Staff can then map it to an existing variant or
    create a new one.
    """

    character = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="distinction_other_entries",
        help_text="The character sheet that entered this 'Other' distinction.",
    )
    parent_distinction = models.ForeignKey(
        Distinction,
        on_delete=models.CASCADE,
        related_name="other_entries",
        help_text="The variant parent distinction this 'Other' belongs to.",
    )
    freeform_text = models.CharField(
        max_length=100,
        help_text="What the player entered as their 'Other' value.",
    )
    staff_mapped_distinction = models.ForeignKey(
        Distinction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mapped_from_other",
        help_text="The distinction this was mapped to by staff.",
    )
    status = models.CharField(
        max_length=20,
        choices=OtherStatus.choices,
        default=OtherStatus.PENDING_REVIEW,
        help_text="Current status of this 'Other' entry.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this entry was created.",
    )

    class Meta:
        verbose_name = "Character Distinction Other Entry"
        verbose_name_plural = "Character Distinction Other Entries"

    def __str__(self) -> str:
        return f"'{self.freeform_text}' for {self.parent_distinction.name}"


class SheetUpdateRequest(models.Model):  # noqa: SHARED_MEMORY
    """A player-submitted request to alter a character sheet (#2628).

    For DISTINCTION_ADD: ``target_distinction`` is set, ``target_character_distinction`` is null.
    For DISTINCTION_REMOVE: ``target_character_distinction`` is set (SET_NULL after
    the CharacterDistinction row is deleted — the request row survives as a receipt).

    The ``status`` field tracks the lifecycle: PENDING → APPROVED or DENIED.
    The ``origin`` field stores first-acquisition provenance for ``grant_distinction``.
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="sheet_update_requests",
        help_text="The character requesting the change.",
    )
    request_type = models.CharField(
        max_length=20,
        choices=SheetUpdateRequestType.choices,
        help_text="What kind of sheet update this request represents.",
    )
    rank = models.PositiveSmallIntegerField(
        default=1,
        help_text="Target rank for ADD (absolute, not a delta — a rank-up authorization "
        "for an existing holder sets this above the current rank). Ignored for REMOVE.",
    )
    target_distinction = models.ForeignKey(
        DISTINCTION_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="add_sheet_update_requests",
        help_text="The distinction to add (set for DISTINCTION_ADD only).",
    )
    target_character_distinction = models.ForeignKey(
        "arxii.CharacterDistinction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remove_sheet_update_requests",
        help_text="The CharacterDistinction to remove (set for DISTINCTION_REMOVE only). "
        "Null after the distinction is deleted — the request row survives as a receipt.",
    )
    justification = models.TextField(
        help_text="Player's narrative justification for this change.",
    )
    status = models.CharField(
        max_length=10,
        choices=SheetUpdateRequestStatus.choices,
        default=SheetUpdateRequestStatus.PENDING,
        help_text="Lifecycle state of this request.",
    )
    reviewed_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_sheet_update_requests",
        help_text="The GM who approved or denied this request.",
    )
    submitted_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_sheet_update_requests",
        help_text="The account that submitted this request. "
        "The player's own account for player-initiated; the GM's account for GM-direct.",
    )
    xp_cost = models.PositiveIntegerField(
        help_text="XP cost computed at submission time. 0 for free transactions.",
    )
    origin = models.CharField(
        max_length=30,
        choices=DistinctionOrigin.choices,
        default=DistinctionOrigin.UNLOCK_PURCHASE,
        help_text="First-acquisition provenance passed to grant_distinction at approval.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Sheet Update Request"
        verbose_name_plural = "Sheet Update Requests"

    def __str__(self) -> str:
        type_label = self.get_request_type_display()
        return f"{type_label} for {self.character_sheet} ({self.xp_cost} XP)"

    def clean(self) -> None:
        """Validate exactly one target is set based on request_type."""
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        if self.request_type == SheetUpdateRequestType.DISTINCTION_ADD:
            if not self.target_distinction_id:
                msg = "DISTINCTION_ADD requires target_distinction."
                raise ValidationError(msg)
            if self.target_character_distinction_id:
                msg = "DISTINCTION_ADD must not set target_character_distinction."
                raise ValidationError(msg)
        elif self.request_type == SheetUpdateRequestType.DISTINCTION_REMOVE:
            if not self.target_character_distinction_id:
                msg = "DISTINCTION_REMOVE requires target_character_distinction."
                raise ValidationError(msg)
            if self.target_distinction_id:
                msg = "DISTINCTION_REMOVE must not set target_distinction."
                raise ValidationError(msg)
