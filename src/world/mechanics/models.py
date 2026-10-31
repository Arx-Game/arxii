"""
Mechanics System Models

Game engine mechanics for the modifier system, roll resolution, and other
mechanical calculations. This app provides the core infrastructure for
how modifiers from various sources (distinctions, magic, equipment, conditions)
are collected, stacked, and applied to checks and other game mechanics.
"""

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property

from core.managers import ArxSharedMemoryManager, ArxSharedMemoryQuerySet
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.mechanics.types import PrerequisiteEvaluation
    from world.traits.models import Trait
from world.contributors.models import CreditedContent
from world.magic.constants import TechniqueFunction
from world.mechanics.constants import (
    FAVOR_CATEGORY_NAMES,
    MANEUVER_EFFECT_CATEGORY_NAME,
    MANEUVER_EFFECT_KIND,
    SOURCE_TYPE_ACHIEVEMENT_REWARD,
    SOURCE_TYPE_DISTINCTION,
    SOURCE_TYPE_FORM,
    SOURCE_TYPE_RESIDENCE_COMFORT,
    SOURCE_TYPE_UNKNOWN,
    TECHNIQUE_SCOPE_KINDS,
    ChallengeType,
    DiscoveryType,
    EffectKind,
    ManeuverEffectKey,
    PropertyHolder,
    ResolutionType,
)
from world.scenes.action_constants import (
    DIFFICULTY_BAND_STEP,
    DIFFICULTY_VALUES,
    DifficultyChoice,
)

_DAMAGE_TYPE_MODEL_PATH = "arxii.DamageType"
_CONSEQUENCE_POOL_MODEL = "arxii.ConsequencePool"
_CHALLENGE_TEMPLATE_MODEL = "arxii.ChallengeTemplate"
OBJECTDB_MODEL = "objects.ObjectDB"

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
TRAIT_MODEL = "arxii.Trait"
CAPABILITY_TYPE_MODEL = "arxii.CapabilityType"
CHECK_TYPE_MODEL = "arxii.CheckType"
ASPECT_MODEL = "arxii.Aspect"
CONSEQUENCE_MODEL = "arxii.Consequence"


class ModifierCategoryManager(NaturalKeyManager):
    """Manager for ModifierCategory with natural key support."""


class ModifierCategory(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    Categories for organizing modifier targets.

    Examples: stat, magic, affinity, resonance, goal, roll
    These are broad groupings that help organize the unified modifier target registry.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Category name (e.g., 'stat', 'magic', 'affinity')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this category represents",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display purposes (lower values appear first)",
    )

    objects = ModifierCategoryManager()

    class Meta:
        verbose_name_plural = "Modifier categories"
        ordering = ["display_order", "name"]

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self):
        return self.name


class ModifierTargetManager(NaturalKeyManager):
    """Manager for ModifierTarget with natural key support, plus cached_all() (#1846)."""


class ModifierTarget(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    Unified registry of all things that can be modified.

    This replaces the separate Affinity, Resonance, and GoalDomain models
    with a single unified system. Each modifier target belongs to a category
    and can be referenced by the modifier system.
    """

    name = models.CharField(
        max_length=100,
        help_text="Modifier target name",
    )
    category = models.ForeignKey(
        ModifierCategory,
        on_delete=models.CASCADE,
        related_name="targets",
        help_text="Category this modifier target belongs to",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this modifier target represents",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display purposes within category (lower values appear first)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this modifier target is currently active in the game",
    )
    is_styleable = models.BooleanField(
        default=False,
        help_text=(
            "Crafters may work this axis into a piece as an Accent at craft "
            "time (#2878) — e.g. allure, menace. Data designation, never an "
            "enum: adding a styleable axis is a row flip, not a migration."
        ),
    )
    styleable_adjective = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text=(
            "Adjective form used in item display grammar (#2878): menace → "
            "'menacing', allure → 'alluring' ('a quite menacing breastplate'). "
            "Blank falls back to the target name."
        ),
    )
    # F12 (#4090): the help_text below is stale — this FK is also populated for the
    # LANGUAGE category (comprehension traits), not only "stat category". Left as a
    # code comment instead of a help_text edit because any help_text change here
    # generates an AlterField migration (verified via `makemigrations --dry-run`);
    # fix the wording for real the next time this field's migration churns anyway.
    target_trait = models.ForeignKey(
        TRAIT_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_targets",
        help_text="The trait this target modifies. Populated for stat category; "
        "null for categories whose target systems aren't built yet. "
        "See TECH_DEBT.md for tracking.",
    )
    target_affinity = models.OneToOneField(
        "arxii.Affinity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The affinity this target represents (affinity category only).",
    )
    target_resonance = models.OneToOneField(
        "arxii.Resonance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The resonance this target represents (resonance category only).",
    )
    target_capability = models.OneToOneField(
        CAPABILITY_TYPE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The capability this target represents (capability category only).",
    )
    target_check_type = models.OneToOneField(
        CHECK_TYPE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The check type this target represents (check category only).",
    )
    # #4827: a distinction's +N on an Aspect is a modifier on every check that weights
    # that Aspect, scaled by the check's aspect weight (the modifier seam's ASPECT block).
    # An FK, not a name match, so a renamed Aspect keeps its lever (#3676's lesson).
    target_aspect = models.OneToOneField(
        ASPECT_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The Aspect this target represents (aspect category only).",
    )
    target_damage_type = models.OneToOneField(
        _DAMAGE_TYPE_MODEL_PATH,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifier_target",
        help_text="The damage type this target represents (resistance category only).",
    )
    target_being = models.ForeignKey(
        "arxii.WorshippedBeing",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier_targets",
        help_text=(
            "The being this favor target belongs to (favor_invocation and favor_earning "
            "categories only, #4333). Null in those categories means any being. A plain "
            "FK, not one-to-one: a being has one target in each favor category. CASCADE, "
            "not SET_NULL: clearing it would widen a being's target to every being."
        ),
    )
    # CASCADE, not SET_NULL, on scope_maneuver_effect: clearing it would widen the
    # target to every effect. Maneuver effect category only (#4783); set this or the
    # kind, not both (modifier_target_one_scope).
    scope_maneuver_effect = models.ForeignKey(
        "arxii.ManeuverEffect",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="modifier_targets",
        verbose_name="Scope - one effect",
        help_text="This effect only.",
    )
    scope_effect_kind = models.CharField(
        max_length=32,
        choices=EffectKind.choices,
        blank=True,
        default="",
        verbose_name="Scope - kind of effect",
        help_text=(
            "This kind of effect on every maneuver; damage and the two condition kinds also "
            "reach techniques. Set this or the effect above, not both."
        ),
    )
    # #4822: the technique-side scopes narrow a kind of effect to one technique, one gift,
    # one technique function, one damage type or one resonance. They combine (all that are
    # set must hold) and they need the kind (modifier_target_technique_scope_needs_kind).
    # CASCADE on each FK: clearing one would widen the target to every technique.
    scope_technique = models.ForeignKey(
        "arxii.Technique",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="effect_modifier_targets",
        verbose_name="Scope - technique",
        help_text="This technique only.",
    )
    scope_gift = models.ForeignKey(
        "arxii.Gift",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="effect_modifier_targets",
        verbose_name="Scope - gift",
        help_text="Techniques of this gift and of its child gifts.",
    )
    scope_technique_function = models.CharField(
        max_length=32,
        choices=TechniqueFunction.choices,
        blank=True,
        default="",
        verbose_name="Scope - technique function",
        help_text="Every technique that carries this function.",
    )
    scope_damage_type = models.ForeignKey(
        _DAMAGE_TYPE_MODEL_PATH,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="effect_modifier_targets",
        verbose_name="Scope - damage type",
        help_text="Damage of this type only (damage effects only).",
    )
    scope_resonance = models.ForeignKey(
        "arxii.Resonance",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="effect_modifier_targets",
        verbose_name="Scope - resonance",
        help_text="Techniques whose gift manifests as this resonance for the caster.",
    )
    # Future target FKs — added when their systems are built:
    # target_condition: FK to conditions.ConditionTemplate — condition modifier system
    # See TECH_DEBT.md §"Future Target FKs" for full tracking list.
    objects = ModifierTargetManager()

    # Class-level cache mapping target_trait_id -> ModifierTarget, the same
    # whole-table-once idea Trait's natural-key lookup_table uses (#2687). The
    # stat-modifier hot path (TraitHandler._get_stat_modifier) resolves a
    # ModifierTarget by its target_trait FK per stat read; that lookup is keyed
    # by a non-PK field, so it misses the SharedMemoryModel identity map and
    # re-queries each call. This cache serves it from memory after the first
    # build (#552).
    # The target_aspect map (#4827) is built by the same query: the check seam asks
    # for the target of every Aspect a check weights, on every roll, and a roll already
    # builds the trait map through its stat reads, so the aspect map comes for nothing
    # and a game with no aspect target authored yet pays no query for the walk.
    _trait_cache_built = False
    _trait_to_target_map: dict[int, "ModifierTarget"] = {}
    _aspect_to_target_map: dict[int, "ModifierTarget"] = {}

    class Meta:
        unique_together = ["category", "name"]
        ordering = ["category__display_order", "display_order", "name"]
        constraints = [
            # One target per (favor category, being) (#4333). The single "any being"
            # target per favor category is held by clean(): a partial index on a null
            # target_being cannot be scoped to the two favor categories, and every
            # other category's targets are null here.
            models.UniqueConstraint(
                fields=["category", "target_being"],
                condition=models.Q(target_being__isnull=False),
                name="unique_modifier_target_category_being",
            ),
            # One scope at a time (#4783): a target names one effect or one kind.
            models.CheckConstraint(
                condition=~(
                    models.Q(scope_maneuver_effect__isnull=False) & ~models.Q(scope_effect_kind="")
                ),
                name="modifier_target_one_scope",
            ),
            # A technique scope narrows a kind of effect (#4822): with no kind it would
            # widen to every effect, and it never rides with a single maneuver effect.
            models.CheckConstraint(
                condition=(
                    models.Q(scope_technique__isnull=True)
                    & models.Q(scope_gift__isnull=True)
                    & models.Q(scope_technique_function="")
                    & models.Q(scope_damage_type__isnull=True)
                    & models.Q(scope_resonance__isnull=True)
                )
                | (
                    models.Q(scope_effect_kind__in=TECHNIQUE_SCOPE_KINDS)
                    & models.Q(scope_maneuver_effect__isnull=True)
                ),
                name="modifier_target_technique_scope_needs_kind",
            ),
            # A damage type narrows damage and nothing else (#4822).
            models.CheckConstraint(
                condition=models.Q(scope_damage_type__isnull=True)
                | models.Q(scope_effect_kind=EffectKind.DAMAGE),
                name="modifier_target_damage_type_scope_is_damage",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["category", "name"]
        dependencies = [
            "arxii.ModifierCategory",
            "arxii.ManeuverEffect",
            "arxii.Technique",
            "arxii.Gift",
            "arxii.DamageType",
            "arxii.Resonance",
        ]

    def __str__(self):
        return f"{self.name} ({self.category.name})"

    def clean(self) -> None:
        """A favor target's being (#4333): only in the two favor categories, and one
        "any being" target (no being) per favor category."""
        super().clean()
        if not self.category_id:
            return
        self._clean_maneuver_effect_scope()
        is_favor = self.category.name in FAVOR_CATEGORY_NAMES
        if self.target_being_id and not is_favor:
            msg = "Only a favor invocation or favor earning target names a being."
            raise ValidationError({"target_being": msg})
        if is_favor and not self.target_being_id:
            others = (
                type(self)
                .objects.filter(category_id=self.category_id, target_being__isnull=True)
                .exclude(pk=self.pk)
            )
            if others.exists():
                msg = "This favor category already has its any-being target; name a being."
                raise ValidationError({"target_being": msg})

    @property
    def has_technique_scope(self) -> bool:
        """Whether any of the five technique-side scopes is set (#4822)."""
        return bool(self._set_technique_scope_fields())

    def _set_technique_scope_fields(self) -> list[str]:
        """The technique-side scope fields that are set, in the order they are reported."""
        return [
            field
            for field, is_set in (
                ("scope_technique", self.scope_technique_id is not None),
                ("scope_gift", self.scope_gift_id is not None),
                ("scope_technique_function", bool(self.scope_technique_function)),
                ("scope_damage_type", self.scope_damage_type_id is not None),
                ("scope_resonance", self.scope_resonance_id is not None),
            )
            if is_set
        ]

    def _clean_maneuver_effect_scope(self) -> None:
        """A maneuver-effect target names exactly one scope; no other category names any."""
        has_effect = self.scope_maneuver_effect_id is not None
        has_kind = bool(self.scope_effect_kind)
        technique_scope = self._set_technique_scope_fields()
        if self.category.name != MANEUVER_EFFECT_CATEGORY_NAME:
            if technique_scope:
                msg = "Only a maneuver effect target names a technique scope."
                raise ValidationError({technique_scope[0]: msg})
            if has_effect or has_kind:
                msg = "Only a maneuver effect target names an effect or a kind of effect."
                field = "scope_maneuver_effect" if has_effect else "scope_effect_kind"
                raise ValidationError({field: msg})
            return
        if technique_scope:
            self._clean_technique_scope(has_effect=has_effect, has_kind=has_kind)
            return
        if has_effect and has_kind:
            msg = "Set the effect or the kind of effect, not both."
            raise ValidationError({"scope_effect_kind": msg})
        if not has_effect and not has_kind:
            msg = "A maneuver effect target needs the effect or the kind of effect it scopes to."
            raise ValidationError({"scope_maneuver_effect": msg})

    def _clean_technique_scope(self, *, has_effect: bool, has_kind: bool) -> None:
        """A technique scope narrows a kind of effect (#4822), never one maneuver's effect."""
        if has_effect:
            msg = "A technique scope narrows a kind of effect, not one maneuver's effect."
            raise ValidationError({"scope_maneuver_effect": msg})
        if not has_kind:
            msg = "A technique scope needs the kind of effect it narrows."
            raise ValidationError({"scope_effect_kind": msg})
        if self.scope_effect_kind not in TECHNIQUE_SCOPE_KINDS:
            msg = "A technique scope narrows damage, condition severity or condition duration."
            raise ValidationError({"scope_effect_kind": msg})
        if self.scope_damage_type_id is not None and self.scope_effect_kind != EffectKind.DAMAGE:
            msg = "A damage type scope is for damage only."
            raise ValidationError({"scope_damage_type": msg})

    @classmethod
    def get_for_trait(cls, trait: "Trait") -> "ModifierTarget | None":
        """Return the ModifierTarget whose ``target_trait`` is ``trait`` (cached).

        Keyed by ``target_trait_id`` so repeated stat-modifier lookups don't
        re-query. Returns ``None`` when no target points at the trait.
        """
        if not cls._trait_cache_built:
            cls._build_trait_cache()
        return cls._trait_to_target_map.get(trait.pk)

    @classmethod
    def _build_trait_cache(cls) -> None:
        """Build the target_trait_id and target_aspect_id -> ModifierTarget maps, one query."""
        trait_map: dict[int, ModifierTarget] = {}
        aspect_map: dict[int, ModifierTarget] = {}
        for target in cls.objects.filter(
            models.Q(target_trait__isnull=False) | models.Q(target_aspect__isnull=False)
        ):
            if target.target_trait_id is not None:
                trait_map[target.target_trait_id] = target
            if target.target_aspect_id is not None:
                aspect_map[target.target_aspect_id] = target
        cls._trait_to_target_map = trait_map
        cls._aspect_to_target_map = aspect_map
        cls._trait_cache_built = True

    @classmethod
    def clear_trait_cache(cls) -> None:
        """Clear the target_trait and target_aspect caches (call when targets change)."""
        cls._trait_cache_built = False
        cls._trait_to_target_map = {}
        cls._aspect_to_target_map = {}

    @classmethod
    def get_for_aspect(cls, aspect_id: int) -> "ModifierTarget | None":
        """The target whose ``target_aspect`` is the Aspect with ``aspect_id`` (#4827).

        Served from the same map build as ``get_for_trait``; ``None`` when no target
        points at the Aspect.
        """
        if not cls._trait_cache_built:
            cls._build_trait_cache()
        return cls._aspect_to_target_map.get(aspect_id)

    @classmethod
    def aspect_targets_exist(cls) -> bool:
        """Whether any target points at an Aspect (#4827), so the check seam can skip
        the aspect walk entirely on a game that has authored none."""
        if not cls._trait_cache_built:
            cls._build_trait_cache()
        return bool(cls._aspect_to_target_map)

    def _touches_target_caches(self) -> bool:
        """Whether saving or deleting this row can change the trait or aspect map: it
        points at a trait or an Aspect now, or the built map still holds it from before.
        A resonance, affinity or favor target saved mid-roll (#4827: the check seam reads
        the aspect map on every roll) must not throw the maps away for nothing.
        """
        if self.target_trait_id is not None or self.target_aspect_id is not None:
            return True
        cls = type(self)
        if not cls._trait_cache_built:
            return False
        return any(
            held.pk == self.pk
            for held in (*cls._trait_to_target_map.values(), *cls._aspect_to_target_map.values())
        )

    def save(self, *args: object, **kwargs: object) -> None:
        """Invalidate the target caches when a mutation can change them."""
        touches = self._touches_target_caches()
        super().save(*args, **kwargs)
        if touches or self.target_trait_id is not None or self.target_aspect_id is not None:
            type(self).clear_trait_cache()

    def delete(self, *args: object, **kwargs: object) -> object:
        """Invalidate the target caches when a mapped target is removed."""
        if self._touches_target_caches():
            type(self).clear_trait_cache()
        return super().delete(*args, **kwargs)


class ModifierSource(SharedMemoryModel):
    """
    Encapsulates where a character modifier originated from.

    For distinctions, we need BOTH the effect template AND the character instance:
    - distinction_effect: Tells us WHICH modifier target this grants (effect.target)
      and the base value. A Distinction can have multiple effects, so we need
      to know which specific one this source represents.
    - character_distinction: For CASCADE deletion when the character loses the
      distinction. All modifiers from that distinction get cleaned up.

    Future source types (equipment, spells) will follow the same pattern:
    effect template + character instance.
    """

    # === Distinction Source ===
    # Effect template - tells us the modifier_target (via effect.target) and base value
    distinction_effect = models.ForeignKey(
        "arxii.DistinctionEffect",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modifier_sources",
        help_text="The effect template (defines modifier_target via effect.target)",
    )
    # Instance - for cascade deletion when character loses distinction
    character_distinction = models.ForeignKey(
        "arxii.CharacterDistinction",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="modifier_sources",
        help_text="The character's distinction instance (for cascade deletion)",
    )

    # Future: equipment_effect, equipment_instance, spell_effect, etc.

    # === Residence Comfort Source (#1514) ===
    # Marks the single shared source for residence-comfort AP-regen modifiers. Comfort has no
    # effect template (it's a computed per-character value), so it's a flag, not an FK pair;
    # ``modifier_target`` stays None (it spans both ap-regen targets) so the target-match
    # validation is skipped. Per-character comfort modifiers cascade-delete via their own
    # ``character`` FK, so this source needs no per-character instance.
    residence_comfort = models.BooleanField(
        default=False,
        help_text="Marks the shared source for residence-comfort AP-regen modifiers (#1514).",
    )

    # === Form Combat Profile Source (slice 4 — alternate self) ===
    form_combat_profile = models.ForeignKey(
        "arxii.FormCombatProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modifier_sources",
        help_text=(
            "The form combat profile this source's modifiers come from (alt-self stat-suite)."
        ),
    )

    # === Achievement Reward Source (#1522) ===
    # Marks the shared source for BONUS rewards granted by achievements (e.g. a +5 allure title).
    # Like residence comfort it carries no effect template — the granted ``CharacterModifier``
    # holds its own ``target``/``value``, and ``modifier_target`` stays None so the target-match
    # validation is skipped. Per-character cleanup is via the modifier's own ``character`` FK.
    achievement_reward = models.BooleanField(
        default=False,
        help_text="Marks the shared source for achievement-granted bonus modifiers.",
    )

    class Meta:
        verbose_name = "Modifier source"
        verbose_name_plural = "Modifier sources"

    @property
    def source_type(self) -> str:
        """Get the type of source (distinction, equipment, etc.)."""
        if self.distinction_effect_id or self.character_distinction_id:
            return SOURCE_TYPE_DISTINCTION
        if self.residence_comfort:
            return SOURCE_TYPE_RESIDENCE_COMFORT
        if self.form_combat_profile_id:
            return SOURCE_TYPE_FORM
        if self.achievement_reward:
            return SOURCE_TYPE_ACHIEVEMENT_REWARD
        return SOURCE_TYPE_UNKNOWN

    @property
    def modifier_target(self) -> ModifierTarget | None:
        """Get the modifier target from the effect template."""
        if self.distinction_effect:
            return self.distinction_effect.target
        return None

    @property
    def source_display(self) -> str:
        """Human-readable source description."""
        if self.distinction_effect:
            return f"Distinction: {self.distinction_effect.distinction.name}"
        if self.residence_comfort:
            return "Residence comfort"
        if self.form_combat_profile:
            return f"Form: {self.form_combat_profile}"
        if self.achievement_reward:
            return "Achievement reward"
        return SOURCE_TYPE_UNKNOWN.capitalize()

    def __str__(self) -> str:
        return self.source_display


class CharacterModifierQuerySet(ArxSharedMemoryQuerySet):
    """Custom queryset for CharacterModifier with batch aggregation methods."""

    def active(self) -> "CharacterModifierQuerySet":
        """Rows still in force: permanent (``expires_at`` null) or not yet expired (#4663).

        The one expiry rule for capability reads: the agency oracle
        (``get_effective_capability_value``) and the availability oracle
        (``_get_modifier_sources``) both filter through this, so they agree on whether a
        capability raised by a temporary modifier is present.
        """
        return self.filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())
        )

    def totals_by_character_for_targets(
        self,
        targets: list["ModifierTarget"],
    ) -> dict[int, dict[int, int]]:
        """Aggregate modifier totals grouped by character's ObjectDB id and target pk.

        Single query regardless of character count. Returns:
            {object_db_id: {modifier_target_pk: total_value}}
        """
        if not targets:
            return {}

        target_pks = [t.pk for t in targets]
        rows = (
            self.filter(target__pk__in=target_pks)
            .values("character__character_id", "target__pk")
            .annotate(total=models.Sum("value"))
        )

        lookup: dict[int, dict[int, int]] = {}
        for row in rows:
            obj_id = row["character__character_id"]
            target_pk = row["target__pk"]
            lookup.setdefault(obj_id, {})[target_pk] = row["total"]
        return lookup


class CharacterModifier(SharedMemoryModel):
    """Actual modifier value on a character, with source tracking.

    Modifiers from various sources (distinctions, equipment, conditions) are
    materialized as records for fast lookup during roll resolution.
    Sources are responsible for creating/deleting their modifier records.

    Each modifier has a direct ``target`` FK to ModifierTarget (what it modifies)
    and a ``source`` FK to ModifierSource (where it came from). The target is set
    once at creation and never changes.

    Stacking: All modifiers stack (sum values for a given target).
    Display: Hide modifiers with value 0.
    """

    character = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="modifiers",
        help_text="Character who has this modifier",
    )
    target = models.ForeignKey(
        ModifierTarget,
        on_delete=models.CASCADE,
        related_name="character_modifiers",
        help_text="What this modifier affects (e.g., strength, ap_daily_regen).",
    )
    value = models.IntegerField(help_text="Modifier value (can be negative)")

    # Source tracking — provenance and cascade deletion
    source = models.ForeignKey(
        ModifierSource,
        on_delete=models.CASCADE,
        related_name="modifiers",
        help_text="Where this modifier came from (for cascade deletion and display).",
    )

    # For temporary modifiers (cologne, spell effects, etc.)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this modifier expires (null = permanent)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects = CharacterModifierQuerySet.as_manager()  # type: ignore[assignment]

    class Meta:
        verbose_name = "Character modifier"
        verbose_name_plural = "Character modifiers"

    def clean(self) -> None:
        """Validate that target matches the source's modifier target."""
        source_target = self.source.modifier_target if self.source_id else None
        if source_target and self.target_id and self.target != source_target:
            raise ValidationError({"target": "Target must match the source's modifier target."})

    @property
    def modifier_target(self) -> ModifierTarget:
        """Get the modifier target. Uses the direct FK."""
        return self.target

    def __str__(self) -> str:
        type_name = self.target.name if self.target_id else "Unknown"
        return f"{self.character} {type_name}: {self.value:+d} ({self.source})"


# ---------------------------------------------------------------------------
# Property / Application layer
# ---------------------------------------------------------------------------


class Prerequisite(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    Data-driven property check that gates Capability availability.

    Evaluates whether the property_holder entity has the required Property
    at or above minimum_value. Used at two levels:
    - Capability-level (CapabilityType.prerequisite): checked for ALL sources
    - Source-level (TechniqueCapabilityGrant.prerequisite): per-source check
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    property = models.ForeignKey(
        "arxii.Property",
        on_delete=models.CASCADE,
        related_name="prerequisites",
        help_text="The property to check for on the target entity.",
    )
    property_holder = models.CharField(
        max_length=20,
        choices=PropertyHolder.choices,
        help_text="Which entity to check: character, target object, or location.",
    )
    minimum_value = models.PositiveIntegerField(
        default=1,
        help_text="Minimum property value required. 1 = property must be present.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    def evaluate(
        self,
        character: "ObjectDB",  # noqa: OBJECTDB_PARAM — prerequisites read any actor
        target_object: "ObjectDB",  # noqa: OBJECTDB_PARAM — the prop, per ChallengeInstance
        location: "ObjectDB",  # noqa: OBJECTDB_PARAM — may be a bare object, per the field
    ) -> "PrerequisiteEvaluation":
        """Evaluate this prerequisite against the current game state.

        The holder's value is its stored ``ObjectProperty`` value, or 1 when an active
        condition on it grants the property (its template's or its current stage's
        ``properties``, #4811), whichever is higher. A granted property carries no
        magnitude, so it meets a presence check (minimum 1) and nothing above it.
        """
        from world.mechanics.types import PrerequisiteEvaluation  # noqa: PLC0415

        entity_map = {
            PropertyHolder.SELF: character,
            PropertyHolder.TARGET: target_object,
            PropertyHolder.LOCATION: location,
        }
        entity = entity_map[self.property_holder]

        obj_prop = ObjectProperty.objects.filter(
            object=entity,
            property=self.property,
        ).first()
        value = obj_prop.value if obj_prop is not None else None
        if (value is None or value < self.minimum_value) and self._granted_by_condition(entity):
            value = max(value or 0, 1)

        if value is None:
            return PrerequisiteEvaluation(
                met=False,
                reason=(f"Requires {self.property.name} on {self.get_property_holder_display()}"),
            )

        if value < self.minimum_value:
            return PrerequisiteEvaluation(
                met=False,
                reason=(
                    f"Requires {self.property.name} >="
                    f" {self.minimum_value} on"
                    f" {self.get_property_holder_display()}"
                    f" (current: {value})"
                ),
            )

        return PrerequisiteEvaluation(met=True)

    def _granted_by_condition(
        self,
        entity: "ObjectDB | None",  # noqa: OBJECTDB_PARAM - the holder evaluate() resolved
    ) -> bool:
        """True when an active condition on ``entity`` grants this property, in one query.

        Reads the template's and the current stage's ``properties`` together, with the
        conditions app's notion of active (unsuppressed, not past an in-game expiry).
        """
        if entity is None:
            return False
        from world.conditions.services import _active_matching_instances  # noqa: PLC0415

        return _active_matching_instances(
            [entity],
            models.Q(condition__properties=self.property)
            | models.Q(current_stage__properties=self.property),
        ).exists()


class PropertyCategory(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """Broad groupings for Properties (e.g., elemental, physical, social)."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class Meta:
        verbose_name_plural = "Property categories"

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class Property(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    A neutral descriptive tag on targets or environments.

    Properties describe what something IS, not what can be done to it.
    Examples: flammable, locked, magical, frozen.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        PropertyCategory,
        on_delete=models.CASCADE,
        related_name="properties",
    )

    objects = NaturalKeyManager()

    class Meta:
        verbose_name_plural = "Properties"

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class ChallengeTemplateProperty(SharedMemoryModel):
    """Through model for ChallengeTemplate → Property M2M with value."""

    challenge_template = models.ForeignKey(
        "ChallengeTemplate",
        on_delete=models.CASCADE,
        related_name="challenge_template_properties",
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="challenge_template_properties",
    )
    value = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["challenge_template", "property"],
                name="challenge_template_property_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.challenge_template.name}: {self.property.name} ({self.value})"


class ObjectProperty(SharedMemoryModel):
    """Runtime property attachment on any game object."""

    # ObjectDB by design (#2608)  noqa: OBJECTDB_FIELD
    # Affordances (flammable, volatile, aerial) attach to any physical object —
    # that breadth is the model's whole point.
    object = models.ForeignKey(
        OBJECTDB_MODEL,
        on_delete=models.CASCADE,
        related_name="object_properties",
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="object_properties",
    )
    value = models.PositiveIntegerField(default=1)
    source_condition = models.ForeignKey(
        "arxii.ConditionInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_properties",
    )
    source_challenge = models.ForeignKey(
        "ChallengeInstance",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_properties",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["object", "property"],
                name="object_property_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.object.db_key}: {self.property.name} ({self.value})"


class PropertyDamageModifier(NaturalKeyMixin, SharedMemoryModel):
    """
    Defines how a target's Property modifies damage of a given type.

    Examples:
      - Flammable gives +10 to fire damage
      - Waterlogged gives -20 to lightning damage
    """

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="damage_modifiers",
    )
    damage_type = models.ForeignKey(
        _DAMAGE_TYPE_MODEL_PATH,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="property_damage_modifiers",
        help_text="Specific damage type, or null for ALL damage types",
    )
    modifier_value = models.IntegerField(
        help_text="Modifier to damage (positive = bonus, negative = reduction)",
    )

    objects = NaturalKeyManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["property", "damage_type"],
                name="property_damage_modifier_unique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["property", "damage_type"]
        dependencies = ["arxii.Property", _DAMAGE_TYPE_MODEL_PATH]

    def __str__(self) -> str:
        dt_name = self.damage_type.name if self.damage_type else "ALL"
        return f"{self.property.name} -> {self.modifier_value:+d} {dt_name}"


class PropertyDetonation(SharedMemoryModel):
    """Marks a Property as "volatile" — carrying a one-shot detonation payload.

    An object is volatile when it holds an ``ObjectProperty`` whose ``property``
    has a ``PropertyDetonation`` row (see ``Property.detonation``, the OneToOne
    reverse accessor). Combat redirect resolution (#2210) fires
    ``consequence_pool`` against everyone positioned at the volatile object's
    Position when a guardian redirects saved damage into it, then deletes the
    triggering ``ObjectProperty`` row — the volatility is spent, not reusable.
    """

    property = models.OneToOneField(
        Property,
        on_delete=models.CASCADE,
        related_name="detonation",
    )
    consequence_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        related_name="property_detonations",
        help_text="Graded/deterministic payload fired against everyone at the object's position.",
    )
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.property.name} (volatile)"


class Application(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    Pure eligibility record: Capability + Property = 'you can attempt this'.

    Applications carry no check type, narrative, or difficulty — those come
    from the delivery mechanism (Technique/tool/trait) and the Situation.
    """

    name = models.CharField(max_length=100)
    capability = models.ForeignKey(
        CAPABILITY_TYPE_MODEL,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    target_property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="applications",
        help_text="The Property on a Challenge or target that this Application addresses.",
    )
    required_effect_property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="required_by_applications",
        help_text="Effect Property the source must carry to use this Application.",
    )
    default_template = models.ForeignKey(
        _CHALLENGE_TEMPLATE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_applications",
        help_text=(
            "Authored world-interaction template minted when this Application fires "
            "against a bare object; null = no bare-object affordance"
        ),
    )
    description = models.TextField(blank=True)

    objects = NaturalKeyManager()

    class Meta:
        verbose_name_plural = "Applications"
        constraints = [
            models.UniqueConstraint(
                fields=["capability", "target_property", "name"],
                name="application_unique_cap_prop_name",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.capability.name} + {self.target_property.name})"


# ---------------------------------------------------------------------------
# Maneuver effect catalog (#4783)
# ---------------------------------------------------------------------------


class ManeuverEffect(NaturalKeyMixin, SharedMemoryModel):
    """One named part of a combat maneuver and the number it has with no modifier.

    A fixed catalog, one row per ``ManeuverEffectKey``: maneuvers stay verbs that code
    fires at set moments, and their numbers live here so staff can see and change them.
    A ``ModifierTarget`` scopes to one row, or to every row of one ``EffectKind``.
    Code finds a row by ``key``, never by name. The kind is derived from the key.
    """

    key = models.CharField(
        max_length=40,
        choices=ManeuverEffectKey.choices,
        unique=True,
        help_text="Which maneuver effect this row is. Fixed; code reads it by this key.",
    )
    base_value = models.IntegerField(
        help_text="Used when no modifier applies. The unit is the effect kind's.",
    )
    notes = models.TextField(blank=True, help_text="Staff notes. Never shown to players.")

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["key"]

    def __str__(self) -> str:
        return self.get_key_display()

    @property
    def kind(self) -> str:
        """The effect kind, derived from the key."""
        return MANEUVER_EFFECT_KIND[self.key]


# ---------------------------------------------------------------------------
# Trait → Capability derivation
# ---------------------------------------------------------------------------


class TraitCapabilityDerivation(NaturalKeyMixin, SharedMemoryModel):
    """
    Maps a Trait value to a derived Capability value.

    Allows the system to calculate capability levels from character traits
    using a simple linear formula: base_value + (trait_multiplier * trait_value).
    """

    trait = models.ForeignKey(
        TRAIT_MODEL,
        on_delete=models.CASCADE,
        related_name="capability_derivations",
    )
    capability = models.ForeignKey(
        CAPABILITY_TYPE_MODEL,
        on_delete=models.CASCADE,
        related_name="trait_derivations",
    )
    base_value = models.IntegerField(default=0)
    trait_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    objects = NaturalKeyManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["trait", "capability"],
                name="trait_capability_derivation_unique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["trait", "capability"]
        dependencies = [TRAIT_MODEL, CAPABILITY_TYPE_MODEL]

    def __str__(self) -> str:
        return f"{self.trait.name} → {self.capability.name}"

    def calculate_value(self, trait_value: int) -> int:
        """Calculate derived capability value from a trait value."""
        return int(self.base_value + (self.trait_multiplier * Decimal(trait_value)))


# ---------------------------------------------------------------------------
# Challenge system
# ---------------------------------------------------------------------------


class ChallengeCategory(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """Broad groupings for Challenges (e.g., environmental, social, combat)."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class Meta:
        verbose_name_plural = "Challenge categories"

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class ChallengeTemplate(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    Reusable blueprint for a Challenge that can be placed in Situations.

    Templates define the structure: what Properties the challenge has,
    how severe it is, what approaches can resolve it, and what consequences
    follow from success or failure.
    """

    name = models.CharField(max_length=100, unique=True)
    description_template = models.TextField(
        blank=True,
        help_text="Template string with {variables} for instance-specific text.",
    )
    properties = models.ManyToManyField(
        Property,
        through="ChallengeTemplateProperty",
        related_name="challenge_templates",
        blank=True,
    )
    severity = models.PositiveIntegerField(
        default=DIFFICULTY_VALUES[DifficultyChoice.NORMAL],
        help_text=(
            "Authored difficulty in DIFFICULTY_VALUES points (15 Trivial .. 90 Harrowing), "
            "passed straight to perform_check's target_difficulty. NOT a 1-5 rating: the "
            "old default of 1 resolved every authored challenge at the bottom rank (#2865)."
        ),
    )
    goal = models.TextField(blank=True)
    category = models.ForeignKey(
        ChallengeCategory,
        on_delete=models.CASCADE,
        related_name="challenge_templates",
    )
    challenge_type = models.CharField(
        max_length=20,
        choices=ChallengeType.choices,
        default=ChallengeType.INHIBITOR,
    )
    blocked_capability = models.ForeignKey(
        CAPABILITY_TYPE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blocking_challenges",
    )
    discovery_type = models.CharField(
        max_length=20,
        choices=DiscoveryType.choices,
        default=DiscoveryType.OBVIOUS,
    )
    consequences = models.ManyToManyField(
        CONSEQUENCE_MODEL,
        through="ChallengeTemplateConsequence",
        related_name="challenge_templates",
        blank=True,
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_properties(self) -> list[Property]:
        """Properties on this challenge. Supports Prefetch(to_attr=)."""
        return list(self.properties.all())

    @cached_property
    def cached_approaches(self) -> list["ChallengeApproach"]:
        """Approaches for this challenge. Supports Prefetch(to_attr=)."""
        return list(
            self.approaches.select_related(
                "application__capability",
                "application__target_property",
                "application__required_effect_property",
                "check_type",
                "required_effect_property",
            )
        )

    @cached_property
    def cached_template_properties(self) -> list["ChallengeTemplateProperty"]:
        """Through-model properties. Supports Prefetch(to_attr=)."""
        return list(self.challenge_template_properties.select_related("property"))

    @cached_property
    def cached_consequences(self) -> list["ChallengeTemplateConsequence"]:
        """Through-model consequences. Supports Prefetch(to_attr=)."""
        return list(self.challenge_consequences.select_related("consequence"))


class ChallengeTemplateConsequence(SharedMemoryModel):
    """Through model linking ChallengeTemplate to Consequence with challenge-specific fields."""

    challenge_template = models.ForeignKey(
        ChallengeTemplate,
        on_delete=models.CASCADE,
        related_name="challenge_consequences",
    )
    consequence = models.ForeignKey(
        CONSEQUENCE_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_template_consequences",
    )
    resolution_type = models.CharField(
        max_length=20,
        choices=ResolutionType.choices,
        default=ResolutionType.DESTROY,
    )
    resolution_duration_rounds = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["challenge_template", "consequence"],
                name="challenge_template_consequence_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.challenge_template.name}: {self.consequence.label}"


class ChallengeApproach(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    A way to resolve a Challenge, linking an Application to a check type.

    This is where the system connects 'what you can do' (Application) with
    'how to resolve it' (CheckType) for a specific Challenge.

    NK is (challenge_template, application) — the existing
    ``challenge_approach_unique_per_template`` constraint already enforces this
    as the true minimal uniqueness (a Challenge offers at most one approach per
    Application), so no new DB constraint was needed to add the natural key.
    """

    challenge_template = models.ForeignKey(
        ChallengeTemplate,
        on_delete=models.CASCADE,
        related_name="approaches",
    )
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="challenge_approaches",
    )
    check_type = models.ForeignKey(
        CHECK_TYPE_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_approaches",
    )
    required_effect_property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="required_by_approaches",
    )
    display_name = models.CharField(max_length=100, blank=True)
    custom_description = models.TextField(blank=True)
    action_template = models.ForeignKey(
        "arxii.ActionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="challenge_approaches",
        help_text="When set, resolution uses this template's check_type and pool.",
    )
    auto_succeeds = models.BooleanField(
        default=False,
        help_text=(
            "When true, this approach skips the roll and lands in the top "
            "outcome tier — the capability trivializes the obstacle."
        ),
    )
    is_default = models.BooleanField(
        default=False,
        help_text=(
            "When true, this approach is offered to every character "
            "regardless of capabilities — the fallback anyone can attempt."
        ),
    )

    objects = NaturalKeyManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["challenge_template", "application"],
                name="challenge_approach_unique_per_template",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["challenge_template", "application"]
        dependencies = [_CHALLENGE_TEMPLATE_MODEL, "arxii.Application"]

    def __str__(self) -> str:
        return self.display_name or self.application.name


class ApproachConsequence(SharedMemoryModel):
    """
    Approach-specific consequence override.

    When an approach has unique outcomes that differ from the template-level
    consequences, they are defined here. Links to a generic Consequence and
    optionally adds challenge-specific resolution_type.
    """

    approach = models.ForeignKey(
        ChallengeApproach,
        on_delete=models.CASCADE,
        related_name="consequences",
    )
    consequence = models.ForeignKey(
        CONSEQUENCE_MODEL,
        on_delete=models.CASCADE,
        related_name="approach_consequences",
    )
    resolution_type = models.CharField(
        max_length=20,
        choices=ResolutionType.choices,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["approach", "consequence"],
                name="approach_consequence_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.approach}: {self.consequence.label}"


# ---------------------------------------------------------------------------
# Situation system
# ---------------------------------------------------------------------------


class SituationTemplate(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    A reusable collection of Challenges that form a coherent scenario.

    GMs place Situations; the system generates player options automatically
    based on the Challenges' Properties and the characters' Capabilities.
    """

    name = models.CharField(max_length=100, unique=True)
    description_template = models.TextField(blank=True)
    challenges = models.ManyToManyField(
        ChallengeTemplate,
        through="SituationChallengeLink",
        related_name="situation_templates",
    )
    category = models.ForeignKey(
        ChallengeCategory,
        on_delete=models.CASCADE,
        related_name="situation_templates",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    @cached_property
    def cached_challenge_links(self) -> list["SituationChallengeLink"]:
        """Challenge links. Supports Prefetch(to_attr=)."""
        return list(self.challenge_links.select_related("challenge_template"))


class SituationChallengeLink(NaturalKeyMixin, SharedMemoryModel):
    """Through-table linking Challenges to Situations with ordering.

    NK is (situation_template, challenge_template) — the pre-existing
    ``situation_challenge_unique`` constraint already enforces exactly that, so
    registering the link in ``CONTENT_MODELS`` (#2865) needed no new DB constraint.
    """

    situation_template = models.ForeignKey(
        SituationTemplate,
        on_delete=models.CASCADE,
        related_name="challenge_links",
    )
    challenge_template = models.ForeignKey(
        ChallengeTemplate,
        on_delete=models.CASCADE,
        related_name="situation_links",
    )
    target_object_name = models.CharField(
        max_length=100,
        help_text=(
            "Display name for the ObjectDB instantiate_situation creates to embody "
            "this challenge (e.g. 'the locked door'). Player-visible via "
            "ChallengeInstanceSerializer.target_object_name."
        ),
    )
    display_order = models.PositiveIntegerField(default=0)

    objects = NaturalKeyManager()

    class Meta:
        ordering = ["display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["situation_template", "challenge_template"],
                name="situation_challenge_unique",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["situation_template", "challenge_template"]
        dependencies = ["arxii.SituationTemplate", _CHALLENGE_TEMPLATE_MODEL]

    def __str__(self) -> str:
        return f"{self.situation_template.name} → {self.challenge_template.name}"


class SituationTrapLink(NaturalKeyMixin, SharedMemoryModel):
    """Authored trap blueprint carried by a SituationTemplate.

    Instantiated into a real ``room_features.Trap`` row by
    ``instantiate_situation``. Carries only authorable fields — no
    ``is_armed``/``detected_by`` (always fresh per instantiated Trap), no
    ``position`` (traps minted from a link are always room-wide): traps are
    independent hazards, not a sequenced chain.

    NK is (situation_template, name). Unlike its challenge sibling this link had
    no uniqueness of its own, so registering it in ``CONTENT_MODELS`` (#2865)
    added the ``situation_trap_link_unique_name`` constraint the natural key
    needs — two identically-named traps on one situation were never meaningful
    (``instantiate_situation`` would mint two indistinguishable Trap rows).
    """

    situation_template = models.ForeignKey(
        SituationTemplate,
        on_delete=models.CASCADE,
        related_name="trap_links",
    )
    name = models.CharField(max_length=100)
    consequence_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        related_name="situation_trap_links",
    )
    detect_check_type = models.ForeignKey(
        CHECK_TYPE_MODEL,
        on_delete=models.PROTECT,
        related_name="detect_situation_traps",
    )
    disarm_check_type = models.ForeignKey(
        CHECK_TYPE_MODEL,
        on_delete=models.PROTECT,
        related_name="disarm_situation_traps",
    )
    detect_difficulty = models.PositiveIntegerField(default=0)
    disarm_difficulty = models.PositiveIntegerField(default=0)
    is_hidden = models.BooleanField(default=True)

    objects = NaturalKeyManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["situation_template", "name"],
                name="situation_trap_link_unique_name",
            ),
        ]

    class NaturalKeyConfig:
        fields = ["situation_template", "name"]
        dependencies = ["arxii.SituationTemplate"]

    def __str__(self) -> str:
        return f"{self.situation_template.name} — trap: {self.name}"


class SituationInstance(SharedMemoryModel):
    """A live Situation placed at a location, possibly tied to a scene."""

    template = models.ForeignKey(
        SituationTemplate,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    # ObjectDB by design (#2608)  noqa: OBJECTDB_FIELD
    # A Situation may be placed at any object, not only a profiled Room.
    # `instantiate_situation` requires a RoomProfile ONLY
    # when the template carries trap links (Trap.room_profile needs one); a
    # challenge-only situation at a bare object is supported and test-pinned
    # (test_location_without_room_profile_is_fine_when_only_challenges).
    location = models.ForeignKey(
        OBJECTDB_MODEL,
        on_delete=models.CASCADE,
        related_name="situation_instances",
    )
    template_variables = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_situations",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="situation_instances",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.template.name} at {self.location.db_key}"


class ChallengeInstance(SharedMemoryModel):
    """A live Challenge at a location, optionally part of a SituationInstance."""

    situation_instance = models.ForeignKey(
        SituationInstance,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="challenge_instances",
    )
    template = models.ForeignKey(
        ChallengeTemplate,
        on_delete=models.CASCADE,
        related_name="instances",
    )
    # ObjectDB by design (#2608)  noqa: OBJECTDB_FIELD
    # Sibling of SituationInstance.location — a
    # ChallengeInstance explicitly does NOT require a RoomProfile (see
    # `instantiate_situation`'s docstring), so it can sit at a bare object.
    location = models.ForeignKey(
        OBJECTDB_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_instances",
    )
    # ObjectDB by design (#2608)  noqa: OBJECTDB_FIELD
    # The authored prop embodying the challenge — a door, a rope, a rockfall.
    target_object = models.ForeignKey(
        OBJECTDB_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_target_instances",
        help_text="The object embodying this challenge in the world.",
    )
    is_active = models.BooleanField(default=True)
    is_revealed = models.BooleanField(default=True)
    severity_adjustment = models.SmallIntegerField(
        default=0,
        help_text=(
            "Signed one-band shift a GM applied when placing this challenge (#2865), in "
            "DIFFICULTY_VALUES points. Folded into the template's severity at resolution. "
            "Constrained to exactly one band either way — never an arbitrary offset."
        ),
    )
    adjustment_reason = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Why the GM shifted the band. Required whenever severity_adjustment is "
            "non-zero, and GM-facing only — never surfaced to players."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    severity_adjustment__in=[-DIFFICULTY_BAND_STEP, 0, DIFFICULTY_BAND_STEP]
                ),
                name="challenge_instance_adjustment_one_band",
            ),
            models.CheckConstraint(
                condition=models.Q(severity_adjustment=0) | ~models.Q(adjustment_reason=""),
                name="challenge_instance_adjustment_needs_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.template.name} at {self.location.db_key}"

    @property
    def effective_severity(self) -> int:
        """Authored severity plus this instance's GM band shift, in difficulty points.

        The single reader of ``severity_adjustment`` — every resolution path takes its
        ``target_difficulty`` from here so a placed challenge and a situation-minted one
        cannot drift apart.
        """
        return self.template.severity + self.severity_adjustment


class CharacterChallengeRecord(SharedMemoryModel):
    """Records a character's resolution of a specific Challenge instance."""

    character = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="challenge_records",
    )
    challenge_instance = models.ForeignKey(
        ChallengeInstance,
        on_delete=models.CASCADE,
        related_name="character_records",
    )
    approach = models.ForeignKey(
        ChallengeApproach,
        on_delete=models.CASCADE,
        related_name="character_records",
    )
    outcome = models.ForeignKey(
        "arxii.CheckOutcome",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="challenge_records",
    )
    consequence = models.ForeignKey(
        CONSEQUENCE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="challenge_records",
    )
    resolved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character", "challenge_instance"],
                name="character_challenge_record_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character.db_key} resolved {self.challenge_instance}"


class ContextConsequencePool(SharedMemoryModel):
    """Links a ConsequencePool to a Property for environmental consequences.

    Rider mode (check_type=null): fires alongside player-initiated actions,
    sharing the action's check result.
    Reactive mode (check_type set): fires without player action using its
    own check type (traps, hazards, environmental effects).
    """

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name="context_consequence_pools",
    )
    consequence_pool = models.ForeignKey(
        _CONSEQUENCE_POOL_MODEL,
        on_delete=models.PROTECT,
        related_name="context_attachments",
    )
    check_type = models.ForeignKey(
        CHECK_TYPE_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="context_consequence_pools",
        help_text="If set, pool can fire reactively without player action.",
    )
    description = models.TextField(
        blank=True,
        help_text="GM-facing note about this context pool.",
    )

    class Meta:
        verbose_name = "Context Consequence Pool"
        verbose_name_plural = "Context Consequence Pools"
        constraints = [
            models.UniqueConstraint(
                fields=["property", "consequence_pool"],
                name="unique_property_consequence_pool",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.property.name} → {self.consequence_pool.name}"


class AestheticAxisConfig(SharedMemoryModel):
    """Singleton (pk=1) tuning the aesthetic-axis coherence walk (#546).

    Real columns, no JSON. Lazy-created by ``get_aesthetic_config()``; consume
    via that getter rather than direct ORM access.
    """

    objects = ArxSharedMemoryManager()

    base_magnitude = models.PositiveIntegerField(
        default=5,
        help_text="Base bonus (integer) awarded per matched style facet during the coherence walk.",
    )
    full_combination_bonus = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.50"),
        help_text=(
            "Multiplier applied when a resonance's FULL bound style-set is worn. "
            "e.g. 1.50 = 50 %% bonus on top of the summed base magnitudes."
        ),
    )
    perception_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("2.00"),
        help_text="Max coherence amplification at full perception breadth.",
    )
    perception_breadth_cap = models.PositiveSmallIntegerField(
        default=5,
        help_text=(
            "Distinct STYLE_PRESENTATION endorsers at which perception amplification saturates."
        ),
    )

    def __str__(self) -> str:
        return "AestheticAxisConfig"  # noqa: STRING_LITERAL - display literal, not an identifier


from world.mechanics.engagement import CharacterEngagement  # noqa: F401, E402
