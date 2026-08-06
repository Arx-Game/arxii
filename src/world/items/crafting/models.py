"""Models for the crafting submodule.

All models set ``Meta.app_label = "arxii"`` so Django registers them under the
single collapsed app (#2906; no new Django app needed). Migrations are deferred
to Task 7 of the crafting framework PR.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.items.crafting.constants import CostConsumption, CraftingRecipeKind
from world.room_features.models import RoomFeatureInstance

if TYPE_CHECKING:
    from world.items.models import QualityTier

# Cross-app FK strings — centralised to avoid duplicated-literal smell.
_CHECK_TYPE_FK = "arxii.CheckType"
_TRAIT_FK = "arxii.Trait"
_QUALITY_TIER_FK = "arxii.QualityTier"
_ITEM_TEMPLATE_FK = "arxii.ItemTemplate"
_MODIFIER_TARGET_FK = "arxii.ModifierTarget"
_ITEM_INSTANCE_FK = "arxii.ItemInstance"
_CONSEQUENCE_FK = "arxii.Consequence"


class CraftingRecipe(NaturalKeyMixin, SharedMemoryModel):
    """Top-level recipe that drives a crafting workflow.

    Each recipe kind is unique (one recipe per kind for now) and carries the
    check configuration, resource costs, and default consumption policy for
    crafting attempts.

    Carries `NaturalKeyMixin` (#3006) so the recipe family is lore-authorable:
    `name` is already unique, so it is the natural key with no schema change.
    """

    name = models.CharField(max_length=200, unique=True)
    kind = models.CharField(
        max_length=40,
        choices=CraftingRecipeKind.choices,
        help_text="Determines which crafting flow this recipe drives.",
    )
    check_type = models.ForeignKey(
        _CHECK_TYPE_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Check rolled when attempting this recipe. Unset = recipe disabled.",
    )
    base_difficulty = models.PositiveIntegerField(
        default=0,
        help_text="Base target difficulty passed to perform_check.",
    )
    success_level_step = models.PositiveIntegerField(
        default=10,
        help_text="Quality-score points added per success_level above min_success_level.",
    )
    min_success_level = models.IntegerField(
        default=1,
        help_text="Success levels below this threshold → attempt fails, no output produced.",
    )
    skill_trait = models.ForeignKey(
        _TRAIT_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Trait (skill) whose rank gates or boosts this recipe. Optional.",
    )
    specialization = models.ForeignKey(
        "arxii.Specialization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Specialization this recipe exercises (#2886, e.g. Honeyed Wine → "
            "Brewing). Additive with the skill everywhere: its value joins the "
            "craft/accent rolls AND the quality-cap lookup, so skill 50 + spec "
            "50 crafts like skill 100 (Apostate's ruling)."
        ),
    )
    action_point_cost = models.PositiveIntegerField(
        default=0,
        help_text="Action points spent when initiating a crafting attempt.",
    )
    anima_cost = models.PositiveIntegerField(
        default=0,
        help_text="Anima spent when initiating a crafting attempt.",
    )
    default_cost_consumption = models.CharField(
        max_length=20,
        choices=CostConsumption.choices,
        default=CostConsumption.FULL,
        help_text="How ingredient items are consumed by default on resolution.",
    )
    requires_station = models.BooleanField(
        default=True,
        help_text=(
            "Whether this recipe requires an active, undamaged LAB station in the "
            "crafter's room. Default True; future non-physical crafting kinds may "
            "opt out without a schema change."
        ),
    )
    required_feature_kind = models.ForeignKey(
        "arxii.RoomFeatureKind",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gated_recipes",
        help_text=(
            "When set, the crafter's room must carry an active RoomFeatureInstance "
            "of this kind (#2862 — generalizes the LAB hardcode; e.g. the Workshop "
            "of Iniquity gates illicit refinement). Independent of requires_station."
        ),
    )
    output_item_template = models.ForeignKey(
        "arxii.ItemTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "For ITEM_CREATE: the template this recipe produces. Null for attach "
            "kinds (FACET_ATTACH / STYLE_ATTACH)."
        ),
    )
    requires_knowledge = models.BooleanField(
        default=False,
        help_text=(
            "When True, only a character who holds CharacterRecipeKnowledge for this "
            "recipe may browse or craft it (#2242) — a taught/discovered pattern. "
            "Default False: an open recipe anyone with the skill can make."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        app_label = "arxii"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "output_item_template"],
                name="items_craftingrecipe_kind_output_unique",
                # Postgres NULLs are distinct by default, so without this the
                # constraint does NOT enforce one-row-per-kind for the
                # null-output attach/cut kinds (#3006) — the seeded-default +
                # fixture-upsert single-row assumption needs a real guarantee.
                nulls_distinct=False,
            ),
        ]

    def __str__(self) -> str:
        return self.name  # noqa: STRING_LITERAL — model display, not an identifier

    @cached_property
    def cached_modifier_outcomes(self) -> list[CraftingRecipeModifier]:
        """Modifier outcomes for this recipe, loaded once and cached."""
        return list(self.modifier_outcomes.all().select_related("target"))


class CraftingMaterialRequirement(NaturalKeyMixin, SharedMemoryModel):
    """An ingredient required to attempt a crafting recipe.

    Each row declares one item template (and optional minimum quality) that must
    be present in the crafter's inventory when initiating a crafting attempt.

    Carries `NaturalKeyMixin` (#3006). Unlike the sibling crafting models this
    had no `UniqueConstraint` at all before #3006 added the two partial ones
    below, one per XOR branch — the natural key mirrors that XOR: it spans
    both `item_template` and `material_category`, and whichever branch is
    null on a given row resolves as `None` (the mixin's null-FK handling,
    mirroring `conditions.ConditionCheckModifier`'s check_type/check_category
    XOR).
    """

    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="material_requirements",
    )
    item_template = models.ForeignKey(
        _ITEM_TEMPLATE_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="A specific ingredient template. Mutually exclusive with material_category.",
    )
    material_category = models.ForeignKey(
        "arxii.MaterialCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Any template in this category satisfies the requirement. Mutually "
            "exclusive with item_template."
        ),
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Number of items required.",
    )
    min_quality_tier = models.ForeignKey(
        _QUALITY_TIER_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Minimum quality tier required for the ingredient. Null = any tier.",
    )
    required_value = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Bulk mode (Build 0b): value drawn from the crafter's common-gem bucket for "
            "this material_category tier, instead of counting instances. Only valid with "
            "material_category; when set, quantity is ignored."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["recipe", "item_template", "material_category"]
        dependencies = ["arxii.CraftingRecipe", "arxii.ItemTemplate", "arxii.MaterialCategory"]

    class Meta:
        app_label = "arxii"
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(item_template__isnull=False, material_category__isnull=True)
                    | Q(item_template__isnull=True, material_category__isnull=False)
                ),
                name="items_craftingmaterialrequirement_template_xor_category",
            ),
            # required_value (bulk mode) only pairs with a material_category, never a template.
            models.CheckConstraint(
                check=Q(required_value__isnull=True) | Q(material_category__isnull=False),
                name="items_craftingmaterialrequirement_value_needs_category",
            ),
            # #3006: this model had no UniqueConstraint at all before this pair —
            # one per XOR branch, both partial so the null branch never collides.
            models.UniqueConstraint(
                fields=["recipe", "item_template"],
                condition=Q(item_template__isnull=False),
                name="items_craftingmaterialrequirement_recipe_template_unique",
            ),
            models.UniqueConstraint(
                fields=["recipe", "material_category"],
                condition=Q(material_category__isnull=False),
                name="items_craftingmaterialrequirement_recipe_category_unique",
            ),
        ]

    def __str__(self) -> str:
        target = self.item_template if self.item_template_id else self.material_category
        if self.required_value is not None:
            return f"{self.required_value} value of {target} for {self.recipe}"
        return f"{self.quantity}x {target} for {self.recipe}"


class CraftingSkillCap(NaturalKeyMixin, SharedMemoryModel):
    """Maps a minimum skill value to the maximum quality tier craftable.

    Rows are ordered by ``min_skill_value``; the classmethod ``for_skill`` returns
    the max_quality_tier of the highest row whose threshold the crafter meets.

    Carries `NaturalKeyMixin` (#3006): the key is the existing
    ``(recipe, min_skill_value)`` UniqueConstraint below.
    """

    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="skill_caps",
    )
    min_skill_value = models.IntegerField(
        help_text="Minimum skill rank required to reach this quality cap.",
    )
    max_quality_tier = models.ForeignKey(
        _QUALITY_TIER_FK,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Highest quality tier achievable at this skill band.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["recipe", "min_skill_value"]
        dependencies = ["arxii.CraftingRecipe"]

    class Meta:
        app_label = "arxii"
        ordering = ["min_skill_value"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipe", "min_skill_value"],
                name="items_craftingskillcap_recipe_min_skill_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.recipe}: skill>={self.min_skill_value} → {self.max_quality_tier}"

    @classmethod
    def for_skill(cls, recipe: CraftingRecipe, skill_value: int) -> QualityTier | None:
        """Return the max_quality_tier for the highest skill cap band the crafter qualifies for.

        Finds the row with the largest ``min_skill_value`` that is still <= ``skill_value``
        and returns its ``max_quality_tier``. Returns ``None`` when no rows exist for the
        recipe or when the crafter's skill is below every band's threshold.
        """
        row = (
            cls.objects.filter(recipe=recipe, min_skill_value__lte=skill_value)
            .order_by("-min_skill_value")
            .select_related("max_quality_tier")
            .first()
        )
        if row is None:
            return None
        return row.max_quality_tier


class CraftingRecipeConsequence(NaturalKeyMixin, SharedMemoryModel):
    """A weighted consequence pool entry for a crafting recipe.

    Pulls from the generic ``checks.Consequence`` model; optionally overrides
    the consequence weight and declares how ingredient costs are consumed if
    this consequence fires.

    Carries `NaturalKeyMixin` (#3006): the key is the existing
    ``(recipe, consequence)`` UniqueConstraint below. Caveat: ``checks.Consequence``
    itself carries no natural key (no live caller needs one today — the same gap
    ``mechanics.ChallengeTemplateConsequence`` already lives with unregistered), so
    a fixture-authored row here resolves its ``consequence`` component by raw pk,
    not a portable key. Fine for round-tripping within one database; giving
    ``Consequence`` a natural key is a separate, broader change out of scope here.
    """

    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="consequence_rows",
    )
    consequence = models.ForeignKey(
        _CONSEQUENCE_FK,
        on_delete=models.PROTECT,
        related_name="+",
    )
    weight_override = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Overrides the consequence's default weight in this recipe's pool.",
    )
    cost_consumption = models.CharField(
        max_length=20,
        choices=CostConsumption.choices,
        default=CostConsumption.FULL,
        help_text="How ingredient costs are consumed when this consequence fires.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["recipe", "consequence"]
        dependencies = ["arxii.CraftingRecipe"]

    class Meta:
        app_label = "arxii"
        constraints = [
            models.UniqueConstraint(
                fields=["recipe", "consequence"],
                name="items_craftingrecipeconsequence_recipe_consequence_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.recipe}: {self.consequence}"


class CraftingRecipeModifier(SharedMemoryModel):
    """A modifier outcome a crafting recipe grants on the output item.

    Designers author (recipe, target, base_value, quality_scale_factor) rows.
    On successful craft, the service records a CraftedItemRecipe join row.
    At read time, the value is computed:
        final_value = base_value + round(quality_scale_factor * quality_tier.stat_multiplier)
    """

    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="modifier_outcomes",
    )
    target = models.ForeignKey(
        _MODIFIER_TARGET_FK,
        on_delete=models.CASCADE,
        related_name="+",
    )
    base_value = models.IntegerField(
        help_text="Flat value granted regardless of quality (can be negative).",
    )
    quality_scale_factor = models.IntegerField(
        default=0,
        help_text="Additional value scaled by the resolved QualityTier.stat_multiplier.",
    )

    class Meta:
        app_label = "arxii"
        constraints = [
            models.UniqueConstraint(
                fields=["recipe", "target"],
                name="items_craftingrecipemodifier_recipe_target_unique",
            )
        ]

    def __str__(self) -> str:
        sign = "+" if self.base_value >= 0 else ""
        return f"{self.recipe.name}: {sign}{self.base_value} to {self.target.name}"


class CraftedItemRecipe(SharedMemoryModel):
    """Join: a crafting recipe applied to an item instance at a specific quality.

    The quality_tier is the resolved crafting outcome quality (snapshotted at
    craft time). Modifier values are computed at read time from the recipe's
    modifier outcomes × this quality tier. Maker/designer credits live on
    ItemInstance's #2066 dual-provenance fields, never here (#2878 dedup).
    """

    item_instance = models.ForeignKey(
        _ITEM_INSTANCE_FK,
        on_delete=models.CASCADE,
        related_name="crafted_recipes",
    )
    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="crafted_items",
    )
    quality_tier = models.ForeignKey(
        "arxii.QualityTier",
        on_delete=models.PROTECT,
        related_name="crafted_item_recipes",
        help_text="Quality tier resolved at craft time, used to scale modifier outcomes.",
    )

    class Meta:
        app_label = "arxii"
        constraints = [
            models.UniqueConstraint(
                fields=["item_instance", "recipe"],
                name="items_crafteditemrecipe_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.item_instance} ← {self.recipe.name} ({self.quality_tier.name})"


class ItemAccent(SharedMemoryModel):
    """A style axis the crafter worked into a specific piece (#2878).

    Per-instance, chosen at the forge (or added later by refinement) — never
    recipe or template data: "sexy recipe vs terrifying recipe" is exactly the
    shape this model rejects. Each Accent rolled its own check at craft time;
    ``level`` is how strongly the intent realized. Read alongside the
    recipe-derived modifiers by ``ItemInstance.crafted_modifier_value``.
    """

    item_instance = models.ForeignKey(
        _ITEM_INSTANCE_FK,
        on_delete=models.CASCADE,
        related_name="accents",
    )
    target = models.ForeignKey(
        _MODIFIER_TARGET_FK,
        on_delete=models.PROTECT,
        related_name="item_accents",
        help_text="The styleable axis (is_styleable=True): allure, menace, …",
    )
    level = models.ForeignKey(
        "arxii.AccentLevel",
        on_delete=models.PROTECT,
        related_name="item_accents",
        help_text="How strongly the accent realized (its own roll at craft time).",
    )

    class Meta:
        app_label = "arxii"
        ordering = ["target__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["item_instance", "target"],
                name="items_itemaccent_unique_per_target",
            )
        ]

    def __str__(self) -> str:
        return f"{self.item_instance}: {self.level.name} {self.target.name}"


class AccentExclusion(SharedMemoryModel):
    """A symmetric pair of accent axes that cannot coexist on one item (#2886).

    Data rows, never an enum: "Dramatic and Unassuming are opposites" is a
    content ruling, and future oppositions are row inserts. Store each pair
    once; ``conflict_exists`` checks both orientations.
    """

    target_a = models.ForeignKey(
        _MODIFIER_TARGET_FK,
        on_delete=models.CASCADE,
        related_name="accent_exclusions_a",
    )
    target_b = models.ForeignKey(
        _MODIFIER_TARGET_FK,
        on_delete=models.CASCADE,
        related_name="accent_exclusions_b",
    )

    class Meta:
        app_label = "arxii"
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["target_a", "target_b"],
                name="items_accentexclusion_unique_pair",
            )
        ]

    def __str__(self) -> str:
        return f"{self.target_a.name} ⊥ {self.target_b.name}"

    @classmethod
    def conflict_exists(cls, target_pks: list[int]) -> tuple[int, int] | None:
        """The first excluded (a, b) pk pair present in ``target_pks``, or None."""
        pks = set(target_pks)
        for row in cls.objects.all():
            if row.target_a_id in pks and row.target_b_id in pks:
                return (row.target_a_id, row.target_b_id)
        return None


class AccentArchetypeAllowance(SharedMemoryModel):
    """Where an accent axis may be worked in, by gear archetype (#2886).

    Allowlist semantics: a target with ANY rows is allowed only on the listed
    archetypes; a target with none is unrestricted (custom axes stay usable
    until curated). Apostate's ratified matrix: function accents (stealthy,
    unassuming, nimble) are garment-only — except unassuming plate, which can
    get lost in a crowd; presence accents span everything worn including
    jewelry; menace touches weapons (and jewelry — spiked torcs); regal
    weapons are ornate. Data rows, never an enum.
    """

    target = models.ForeignKey(
        _MODIFIER_TARGET_FK,
        on_delete=models.CASCADE,
        related_name="accent_archetype_allowances",
    )
    gear_archetype = models.CharField(max_length=40)

    class Meta:
        app_label = "arxii"
        ordering = ["target__name", "gear_archetype"]
        constraints = [
            models.UniqueConstraint(
                fields=["target", "gear_archetype"],
                name="items_accentarchetypeallowance_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.target.name} on {self.gear_archetype}"

    @classmethod
    def permits(cls, target: object, gear_archetype: str) -> bool:
        """True when ``target`` may be accented onto this archetype."""
        rows = list(cls.objects.filter(target=target).values_list("gear_archetype", flat=True))
        return not rows or gear_archetype in rows


class ItemRefinementDetails(SharedMemoryModel):
    """Per-kind details for an ITEM_REFINEMENT project (#2878).

    Follows the RANSOM pattern: the consumer app owns the details model and
    points at ``projects.Project`` (ADR-0010 specific→general). The project is
    the deterministic accumulator — AP and coin contributions advance progress
    with **no rolls** (Apostate's ruling: roll-to-see-failure gacha is
    unsatisfying; the road is guaranteed but gets longer/costlier per rung).
    On threshold the instant-completion handler applies +1 to the goal:
    ``accent_target`` set = raise (or add) that Accent; null = raise the
    piece's base quality rung. The reachable rung is capped by the
    highest-capped contributor (master-and-atelier: the final, crossing
    contribution needs a sufficiently thread-woven crafter on the project).
    """

    project = models.OneToOneField(
        "arxii.Project",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="item_refinement_details",
    )
    item_instance = models.ForeignKey(
        _ITEM_INSTANCE_FK,
        on_delete=models.CASCADE,
        related_name="refinement_projects",
    )
    accent_target = models.ForeignKey(
        _MODIFIER_TARGET_FK,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="refinement_projects",
        help_text="The Accent axis being raised/added; null = base quality.",
    )

    class Meta:
        app_label = "arxii"

    def __str__(self) -> str:
        goal = self.accent_target.name if self.accent_target else "quality"
        return f"Refinement of {self.item_instance} ({goal})"


class LabStationDetails(SharedMemoryModel):
    """Per-Lab durability state — the crafting-station economy (#1234).

    OneToOne to RoomFeatureInstance (mirrors SanctumDetails' shape). Durability
    wears by 1 on every crafting attempt that reaches the roll; a broken (durability
    0) or missing station blocks crafting outright. Repaired via
    ``repair_station_durability`` (world/items/crafting/station.py), a coppers-only
    sink through ``currency.services.transfer``.
    """

    feature_instance = models.OneToOneField(
        RoomFeatureInstance,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="lab_station_details",
    )
    durability = models.PositiveIntegerField(
        help_text="Current wear-remaining before the station is broken.",
    )
    max_durability = models.PositiveIntegerField(
        help_text="Durability ceiling for this station's current level.",
    )

    class Meta:
        app_label = "arxii"

    def __str__(self) -> str:
        room_id = self.feature_instance.room_profile_id
        return f"Lab station @ room {room_id}: {self.durability}/{self.max_durability}"

    @property
    def is_broken(self) -> bool:
        return self.durability <= 0


class CharacterRecipeKnowledge(SharedMemoryModel):
    """A recipe a character has learned — taught, discovered, or granted (#2242).

    Gates the ``requires_knowledge`` recipes: a character may only browse/craft a
    gated recipe if they hold one of these rows. Open recipes (the default) need
    no row. The acquisition seams are ``teach_recipe`` (an information economy —
    who knows the alaricite pattern) and ``grant_recipe_knowledge`` (GM / future
    discovery via the clue loop).
    """

    character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="recipe_knowledge",
    )
    recipe = models.ForeignKey(
        CraftingRecipe,
        on_delete=models.CASCADE,
        related_name="known_by",
    )
    learned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "arxii"
        ordering = ["character_sheet", "recipe"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "recipe"],
                name="items_characterrecipeknowledge_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"sheet {self.character_sheet_id} knows {self.recipe}"
