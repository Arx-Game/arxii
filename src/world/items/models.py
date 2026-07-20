"""Models for items, equipment, and inventory."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia_extensions.models import Media
    from world.conditions.models import DamageType
    from world.mechanics.models import ModifierTarget

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils.functional import cached_property
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from actions.constants import TargetKind
from core.descriptors import ReverseOneToOneOrNone
from core.managers import ArxSharedMemoryManager
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.forms.models import ConcealmentLevel, DisguiseKind
from world.items.constants import (
    PROVENANCE_EVENT_TYPES,
    BodyRegion,
    ContainerAccessPolicy,
    EquipmentLayer,
    GearArchetype,
    OwnershipEventType,
    StyleAudacity,
)
from world.locations.constants import StatKey

# Cross-app FK strings used by multiple fields below. Centralized to avoid the
# duplicated-literal SonarCloud smell (python:S1192).
_CHARACTER_SHEET_FK = "character_sheets.CharacterSheet"
_PERSONA_FK = "scenes.Persona"
_ITEM_INSTANCE_FK = "items.ItemInstance"
SOCIETY_MODEL = "societies.Society"
CHECK_TYPE_MODEL = "checks.CheckType"
FACET_MODEL = "magic.Facet"
RESONANCE_MODEL = "magic.Resonance"


class QualityTier(SharedMemoryModel):
    """
    Discrete quality level for items, reusable across systems.

    Color-coded tiers (e.g., Common=white, Fine=green, Masterwork=purple)
    provide consistent visual language for quality/difficulty throughout the game.
    """

    name = models.CharField(max_length=50, unique=True)
    color_hex = models.CharField(
        max_length=7,
        validators=[
            RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Must be a hex color (#RRGGBB)."),
        ],
        help_text="Hex color code for UI display (e.g., '#00FF00').",
    )
    numeric_min = models.PositiveIntegerField(
        help_text="Lower bound of the internal numeric quality range.",
    )
    numeric_max = models.PositiveIntegerField(
        help_text="Upper bound of the internal numeric quality range.",
    )
    stat_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text="Multiplier applied to base stats for items of this tier.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering (lower = worse quality).",
    )

    class Meta:
        ordering = ["sort_order"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(numeric_min__lte=models.F("numeric_max")),
                name="items_quality_tier_min_lte_max",
            )
        ]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def for_score(cls, score: int) -> QualityTier | None:
        """Resolve a numeric quality score to the tier whose [min, max] contains it.

        Below the lowest range clamps to the lowest tier; above the highest
        clamps to the highest. Returns None only when no tiers exist.
        """
        match = cls.objects.filter(numeric_min__lte=score, numeric_max__gte=score).first()
        if match is not None:
            return match
        ordered = cls.objects.order_by("sort_order")
        first = ordered.first()
        if first is not None and score < first.numeric_min:
            return first
        return ordered.last()


class MaterialCategory(SharedMemoryModel):
    """A crafting-equivalence class of materials (e.g. "Precious Gemstones").

    Recipes may target a category so that any member template satisfies the
    requirement. This is the *eligibility* axis only — value/magnitude is a
    separate concern deferred to Build 0b (the gemstone-value ladder). FK
    direction is specific→general (ADR-0010): templates point here; this model
    imports nothing from its consumers.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering (lower first).",
    )

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "material categories"

    def __str__(self) -> str:
        return self.name


class InteractionType(SharedMemoryModel):
    """
    An action that can be performed on an item (eat, drink, read, wield, etc.).

    Item templates declare supported interactions via M2M. Adding new interaction
    types requires only a new DB row, not code changes.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="Internal identifier (e.g., 'eat', 'wield', 'study').",
    )
    label = models.CharField(
        max_length=50,
        help_text="Player-facing label (e.g., 'Eat', 'Wield', 'Study').",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this interaction does.",
    )

    def __str__(self) -> str:
        return self.label


class ItemTemplate(NaturalKeyMixin, SharedMemoryModel):
    """
    Archetype definition for an item type (e.g., "iron longsword", "silk shirt").

    Templates define shared base properties. Individual items in the world are
    ItemInstance records that reference their template for defaults, with
    per-instance overrides for customization (custom names, descriptions, etc.).

    Carries `NaturalKeyMixin` (#2266 review fix) so the content pipeline's
    emitted fixture JSON (natural-key format, no "pk" key) resolves an
    existing same-name row on `loaddata` instead of blind-INSERTing into it
    and raising `IntegrityError` on the unique `name` constraint. Per #946,
    `loaddata` on a `SharedMemoryModel` can INSERT via a natural key but
    cannot UPDATE — the identity map returns the cached instance before the
    new field values land. `core_management.content_fixtures.load_entries`
    (`update_or_create`) remains the only update-safe path; the emitted
    fixture JSON is fresh-DB/insert-or-resolve only.
    """

    # Reverse-OneToOne safe accessor (#2386): this template's gem-type sidecar,
    # or None if the template is not a gem type (Build 0b).
    gem_type_or_none = ReverseOneToOneOrNone("gem_details")

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(
        blank=True,
        help_text="Default full description when examined. Instances can override.",
    )
    weight = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text="Base weight of the item.",
    )
    size = models.PositiveIntegerField(
        default=1,
        help_text=("Size value for container nesting. Smaller items fit inside larger containers."),
    )
    value = models.PositiveIntegerField(
        default=0,
        help_text="Base gold value for trading/selling.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive templates cannot be used to create new items.",
    )
    material_category = models.ForeignKey(
        "items.MaterialCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="templates",
        help_text=(
            "Optional crafting-equivalence class this template belongs to "
            "(e.g. Precious Gemstones). Null = not a categorised material."
        ),
    )
    supports_open_close = models.BooleanField(
        default=False,
        help_text="Whether instances can be opened/closed (coats, bags, lockets).",
    )
    interactions = models.ManyToManyField(
        InteractionType,
        through="TemplateInteraction",
        blank=True,
        related_name="templates",
        help_text="Actions that can be performed on items of this type.",
    )
    is_container = models.BooleanField(
        default=False,
        help_text="Whether this item can hold other items.",
    )
    is_wardrobe = models.BooleanField(
        default=False,
        help_text="Whether instances of this template can store Outfit definitions.",
    )
    container_capacity = models.PositiveIntegerField(
        default=0,
        help_text="Maximum number of items this container can hold.",
    )
    container_max_item_size = models.PositiveIntegerField(
        default=0,
        help_text="Maximum size of items that fit inside this container.",
    )
    is_stackable = models.BooleanField(
        default=False,
        help_text="Whether items of this type can be stacked.",
    )
    max_stack_size = models.PositiveIntegerField(
        default=1,
        help_text="Maximum quantity in a single stack.",
    )
    is_consumable = models.BooleanField(
        default=False,
        help_text="Whether this item has limited uses/charges.",
    )
    max_charges = models.PositiveIntegerField(
        default=0,
        help_text="Maximum charges for consumable items.",
    )
    on_use_pool = models.ForeignKey(
        "actions.ConsequencePool",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Consequences applied when this item is used (null = not usable).",
    )
    on_use_check_type = models.ForeignKey(
        CHECK_TYPE_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Null = deterministic apply; set = roll a check and select from the pool.",
    )
    on_use_difficulty = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Authored target difficulty for the on-use check. Required iff on_use_check_type set."
        ),
    )
    on_use_target_kind = models.CharField(
        max_length=20,
        choices=TargetKind.choices,
        null=True,
        blank=True,
        help_text=(
            "Required kind of an external on-use target. Null = self-use only "
            "(no external target accepted). CHARACTER/ITEM/ROOM = an external "
            "target of that kind is required, validated by UseItemAction."
        ),
    )
    is_craftable = models.BooleanField(
        default=False,
        help_text="Whether this item can be crafted by players.",
    )
    minimum_quality_tier = models.ForeignKey(
        QualityTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="minimum_for_templates",
        help_text="Minimum quality tier this item can be crafted at.",
    )
    tied_resonance = models.ForeignKey(
        RESONANCE_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tied_item_templates",
        help_text="Resonance this item archetype is thematically tied to (a touchstone).",
    )
    resonance_tier = models.ForeignKey(
        "magic.ResonanceTier",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Potency tier, required together with tied_resonance.",
    )
    image = models.ForeignKey(
        "evennia_extensions.Media",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="item_templates",
        help_text="Default reference image for items of this type. Instances can override.",
    )
    facet_capacity = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Number of Facet slots this template can carry. "
            "Plain items = 0 or 1; fine items = 2-3; ceremonial = 4-5."
        ),
    )
    style_capacity = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Number of Style slots this template can carry. "
            "Plain items = 0 or 1; fine items = 2-3; ceremonial = 4-5."
        ),
    )
    adornment_capacity = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Number of gems that can be set into this template as adornment (Build 0b). "
            "A ring holds 1-2; a gem-covered table holds many; plain items = 0."
        ),
    )
    gear_archetype = models.CharField(
        max_length=20,
        choices=GearArchetype.choices,
        default=GearArchetype.OTHER,
        help_text=(
            "Gear category. Drives covenant role × gear compatibility. "
            "Immutable across instances of this template."
        ),
    )
    weapon_damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="weapon_templates",
        help_text="Damage type dealt when this item is wielded as a weapon.",
    )
    base_weapon_damage = models.PositiveIntegerField(
        default=0,
        help_text="Base weapon-damage contribution (weapon archetypes only).",
    )
    base_armor_soak = models.PositiveIntegerField(
        default=0,
        help_text="Base damage-mitigation soak when worn (armor archetypes only).",
    )
    max_durability = models.PositiveIntegerField(
        default=0,
        help_text="Max durability. 0 = item is not durability-tracked.",
    )
    # #676 Phase F — Polish contribution. Drives both room polish (when
    # placed via RoomItem) and fashion polish (when equipped on a body).
    # Typical values: 0.1-1 per per-item (stored as scaled integers ×10
    # by callers), signature items higher. 0 = item contributes no polish.
    polish_value = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Polish contribution per item (Renown system). Stored as a "
            "scaled integer — callers convert from per-spec fractional "
            "values (×10). Applied either as room polish (when placed) "
            "or fashion polish (when equipped)."
        ),
    )
    polish_category = models.ForeignKey(
        "buildings.PolishCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="item_templates",
        help_text=(
            "Polish category for this item's contribution. Null means "
            "polish_value is ignored (item is functional, not decorative)."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(is_container=True) | models.Q(container_capacity=0),
                name="items_container_capacity_requires_is_container",
            ),
            models.CheckConstraint(
                check=(models.Q(is_container=True) | models.Q(container_max_item_size=0)),
                name="items_container_max_size_requires_is_container",
            ),
            models.CheckConstraint(
                check=models.Q(is_stackable=True) | models.Q(max_stack_size=1),
                name="items_stack_size_requires_is_stackable",
            ),
            models.CheckConstraint(
                check=models.Q(is_consumable=True) | models.Q(max_charges=0),
                name="items_charges_requires_is_consumable",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(
                        gear_archetype__in=[
                            GearArchetype.MELEE_ONE_HAND,
                            GearArchetype.MELEE_TWO_HAND,
                            GearArchetype.RANGED,
                            GearArchetype.THROWN,
                            GearArchetype.SHIELD,
                            GearArchetype.LANCE,
                        ]
                    )
                    | models.Q(base_weapon_damage=0)
                ),
                name="items_weapon_damage_requires_weapon_archetype",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(
                        gear_archetype__in=[
                            GearArchetype.LIGHT_ARMOR,
                            GearArchetype.MEDIUM_ARMOR,
                            GearArchetype.HEAVY_ARMOR,
                            GearArchetype.ROBE,
                            GearArchetype.SHIELD,
                        ]
                    )
                    | models.Q(base_armor_soak=0)
                ),
                name="items_armor_soak_requires_armor_archetype",
            ),
            models.CheckConstraint(
                check=(
                    (models.Q(tied_resonance__isnull=True) & models.Q(resonance_tier__isnull=True))
                    | (
                        models.Q(tied_resonance__isnull=False)
                        & models.Q(resonance_tier__isnull=False)
                    )
                ),
                name="itemtemplate_resonance_tier_together",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.on_use_check_type_id is not None and self.on_use_difficulty is None:
            raise ValidationError({"on_use_difficulty": "Required when on_use_check_type is set."})
        if self.on_use_check_type_id is None and self.on_use_difficulty is not None:
            raise ValidationError(
                {"on_use_difficulty": "Only valid when on_use_check_type is set."}
            )
        has_resonance = self.tied_resonance_id is not None
        has_tier = self.resonance_tier_id is not None
        if has_resonance != has_tier:
            msg = "tied_resonance and resonance_tier must be set together, or both left unset."
            raise ValidationError(msg)

    @property
    def is_usable(self) -> bool:
        """Whether this template can be used (has an on-use pool or appearance effects).

        Canonical 'usable' predicate; consumables are the charge-spending subset.
        A template with appearance effects but no pool is usable (cosmetic-only items).

        Note: the appearance_effects check is deferred to use_item itself to avoid
        N+1 queries in list serializers. This property returns True when the template
        has an on_use_pool; callers that need cosmetic-only usability should check
        appearance_effects separately.
        """
        return self.on_use_pool_id is not None

    @cached_property
    def cached_slots(self) -> list[TemplateSlot]:
        """
        Get equipment slots for this template.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate: del instance.cached_slots
        """
        return list(self.slots.all())

    @cached_property
    def cached_interaction_bindings(self) -> list[TemplateInteraction]:
        """
        Get interaction bindings with interaction types loaded.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate: del instance.cached_interaction_bindings
        """
        return list(self.interaction_bindings.select_related("interaction_type").all())


class ItemTemplateProperty(NaturalKeyMixin, SharedMemoryModel):
    """Declares a Property this item template carries by default.

    Mirrors ``mechanics.ChallengeTemplateProperty`` and ``mechanics.ObjectProperty``:
    a magnitude-carrying Property attachment, but authored on the template (every
    instance minted from it starts with these) rather than granted at runtime.
    This is the bridge-object half of #2503 — a bare object's affordances come
    from its template's declared Properties, read by the same oracle that reads
    granted-technique Properties.
    """

    item_template = models.ForeignKey(
        ItemTemplate,
        on_delete=models.CASCADE,
        related_name="default_properties",
    )
    property = models.ForeignKey(
        "mechanics.Property",
        on_delete=models.CASCADE,
        related_name="item_template_defaults",
    )
    value = models.PositiveIntegerField(default=1)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["item_template", "property"]
        dependencies = ["items.ItemTemplate", "mechanics.Property"]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item_template", "property"],
                name="items_template_property_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_template.name}: {self.property.name} ({self.value})"


class TemplateSlot(SharedMemoryModel):
    """
    Declares which body region + equipment layer an item template occupies.

    A single template can have multiple slots (e.g., full plate armor occupies
    torso/over + left_arm/over + right_arm/over).
    """

    template = models.ForeignKey(
        ItemTemplate,
        on_delete=models.CASCADE,
        related_name="slots",
    )
    body_region = models.CharField(
        max_length=20,
        choices=BodyRegion.choices,
    )
    equipment_layer = models.CharField(
        max_length=20,
        choices=EquipmentLayer.choices,
    )
    covers_lower_layers = models.BooleanField(
        default=False,
        help_text=("Whether this slot hides items on lower layers at the same region."),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "body_region", "equipment_layer"],
                name="items_unique_template_slot",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.template.name}: "
            f"{self.get_body_region_display()}"
            f"/{self.get_equipment_layer_display()}"
        )


class ItemInstanceManager(NaturalKeyManager):
    """Manager for ItemInstance with natural-key support + in-play filtering."""

    def in_play(self) -> models.QuerySet[ItemInstance]:
        """Rows still in play (not consumed/destroyed)."""
        return self.get_queryset().filter(destroyed_at__isnull=True)


class ItemInstance(SharedMemoryModel):
    """
    A specific item that exists in the game world.

    References an ItemTemplate for base properties, with per-instance overrides
    for custom names, descriptions, quality, and state.
    """

    # Reverse-OneToOne safe accessors (#2386): missing row -> None.
    building_permit_details_or_none = ReverseOneToOneOrNone("building_permit_details")
    # A cut/graded gem instance (Build 0b) — None for non-gems.
    gem_or_none = ReverseOneToOneOrNone("gem_instance_details")

    template = models.ForeignKey(
        ItemTemplate,
        on_delete=models.PROTECT,
        related_name="instances",
        help_text="The archetype this item is based on.",
    )
    game_object = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="item_instance",
        help_text=("The Evennia object representing this item in the game world."),
    )
    custom_name = models.CharField(
        max_length=300,
        blank=True,
        help_text="MU*-style descriptive name override.",
    )
    custom_description = models.TextField(
        blank=True,
        help_text="Custom examination text, overrides template description.",
    )
    quality_tier = models.ForeignKey(
        QualityTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="item_instances",
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Stack quantity for stackable items.",
    )
    charges = models.PositiveIntegerField(
        default=0,
        help_text="Remaining charges for consumable items.",
    )
    durability = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Current durability. Null = not tracked; 0 = broken.",
    )
    is_open = models.BooleanField(
        default=False,
        help_text="Whether this item is currently open.",
    )
    access_policy = models.CharField(
        max_length=20,
        choices=ContainerAccessPolicy.choices,
        default=ContainerAccessPolicy.OPEN,
        help_text="Container-only: who may take contents (#1909). Non-containers ignore it.",
    )
    # #684: ownership is CharacterSheet-scoped — the body owns the item, not
    # the account. One inventory per character; personas are a display layer
    # over the same underlying gear. See docs in the spec on the GitHub issue.
    holder_character_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_items",
        help_text=(
            "The CharacterSheet (body) that owns this item. SET_NULL on sheet "
            "delete so the item survives. Persona display is computed at "
            "serialization time from holder_character_sheet.primary_persona."
        ),
    )
    crafter_character_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crafted_items",
        help_text="The body that crafted this item.",
    )
    attuned_to_character_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attuned_touchstones",
        help_text="Character this touchstone instance has been personally attuned to.",
    )
    attuned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When attune_touchstone() bound this instance to its character.",
    )
    crafter_persona_display = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The persona the crafter was presenting as at the forge — the "
            "maker's mark Bob signed it with. Validated to be a persona of "
            "crafter_character_sheet. Null falls back to "
            "crafter_character_sheet.primary_persona at render time."
        ),
    )
    designer_character_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="designed_items",
        help_text=(
            "The body that named/described this item (#2066 dual provenance — "
            "Arx 1 erased the prose author). Equal to the crafter on "
            "self-finished work; the ware finishing pass and service crafting "
            "stamp the buyer."
        ),
    )
    designer_persona_display = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The persona the designer was presenting as. Renders as "
            "'Crafted by X, Designed by Y', collapsing when equal."
        ),
    )
    contained_in = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contents",
        help_text=("Container item this item is stored inside (null = not in a container)."),
    )
    image = models.ForeignKey(
        "evennia_extensions.Media",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="item_instances",
        help_text="Custom reference image override for this specific item.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    lore_value = models.IntegerField(
        default=0,
        help_text=(
            "Material construction-value boost. Used by the buildings system "
            "to inflate this instance's value when contributed as a MATERIAL "
            "to a BUILDING_CONSTRUCTION project. Pure number — more = more "
            "valuable in construction. Special properties (e.g. godswar stone "
            "grants resonance_amp to inhabitants) live on world.buildings."
            "MaterialLoreEffect, NOT here."
        ),
    )
    destroyed_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Set when the item is consumed/destroyed and removed from play. Null = in play.",
    )
    legend_deeds = models.ManyToManyField(
        "societies.LegendEntry",
        blank=True,
        related_name="linked_items",
        help_text="Deeds that made this item legendary (#2359). Provenance-preserving link.",
    )

    objects = ItemInstanceManager()

    class Meta:
        indexes = [
            models.Index(fields=["template"]),
            models.Index(fields=["holder_character_sheet"]),
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        """Return custom name if set, otherwise template name."""
        return self.custom_name or self.template.name

    @property
    def display_description(self) -> str:
        """Return custom description if set, otherwise template description."""
        return self.custom_description or self.template.description

    @property
    def legend_value(self) -> int:
        """Sum of all active linked deeds' total values (#2359)."""
        return sum(d.get_total_value() for d in self.legend_deeds.filter(is_active=True))

    def crafted_modifier_value(self, target: ModifierTarget) -> int:
        """Total crafted modifier value for ``target`` across all recipes on this item.

        Iterates the prefetched ``cached_crafted_recipes`` (set by
        ``CharacterEquipmentHandler``) and their nested
        ``recipe.cached_modifier_outcomes``, computing each value as:
            base_value + round(quality_scale_factor * quality_tier.stat_multiplier)
        """
        total = 0
        for crafted in self.cached_crafted_recipes:
            for outcome in crafted.recipe.cached_modifier_outcomes:
                if outcome.target == target:
                    total += outcome.base_value + round(
                        outcome.quality_scale_factor * crafted.quality_tier.stat_multiplier
                    )
        return total

    @property
    def display_image(self) -> Media | None:
        """Return custom image if set, otherwise template image."""
        return self.image or self.template.image

    @cached_property
    def cached_item_facets(self) -> list[ItemFacet]:
        """Facets attached to this item instance.

        Targeted by Prefetch(..., to_attr=). When prefetched, Django populates
        this directly. When accessed without prefetch, falls back to a fresh
        query.

        To invalidate: del instance.cached_item_facets
        """
        return list(self.item_facets.select_related("facet", "attachment_quality_tier"))

    @cached_property
    def cached_item_styles(self) -> list[ItemStyle]:
        """Styles attached to this item instance (#546).

        Targeted by Prefetch(..., to_attr=). When prefetched, Django populates
        this directly. When accessed without prefetch, falls back to a fresh
        query.

        To invalidate: del instance.cached_item_styles
        """
        return list(self.item_styles.select_related("style", "attachment_quality_tier"))

    @property
    def is_broken(self) -> bool:
        return self.durability is not None and self.durability == 0

    @property
    def differs_from_template(self) -> bool:
        """True if this instance carries per-instance data worth preserving on
        destruction (soft-delete). Bare template-identical throwaways return False."""
        if self.custom_name or self.custom_description or self.lore_value or self.quality_tier_id:
            return True
        if self.cached_item_facets:
            return True
        return self.ownership_events.exclude(event_type=OwnershipEventType.CREATED).exists()

    @property
    def is_lore_critical(self) -> bool:
        """True if this instance must never be auto-purged by the soft-delete
        cleanup: it carries material ``lore_value``, facets, or transfer
        provenance (it changed hands). Subset of ``differs_from_template`` —
        cosmetic-only data (custom name / quality tier) is NOT lore-critical."""
        if self.lore_value:
            return True
        if self.cached_item_facets:
            return True
        return self.ownership_events.filter(event_type__in=PROVENANCE_EVENT_TYPES).exists()

    def _quality_multiplier(self) -> Decimal:
        if self.quality_tier is None:
            return Decimal(1)
        return Decimal(str(self.quality_tier.stat_multiplier))

    @cached_property
    def effective_weapon_damage(self) -> int:
        if self.is_broken:
            return 0
        return round(self.template.base_weapon_damage * self._quality_multiplier())

    @cached_property
    def effective_armor_soak(self) -> int:
        if self.is_broken:
            return 0
        return round(self.template.base_armor_soak * self._quality_multiplier())

    @property
    def effective_weapon_damage_type(self) -> DamageType | None:
        return self.template.weapon_damage_type


class TemplateInteraction(SharedMemoryModel):
    """
    Links an ItemTemplate to an InteractionType with optional flavor text.

    The flavor text provides contextual description for the interaction --
    what a muffin tastes like when eaten, what a perfume smells like, what
    memory an artifact triggers when equipped.
    """

    template = models.ForeignKey(
        ItemTemplate,
        on_delete=models.CASCADE,
        related_name="interaction_bindings",
    )
    interaction_type = models.ForeignKey(
        InteractionType,
        on_delete=models.CASCADE,
        related_name="template_bindings",
    )
    flavor_text = models.TextField(
        blank=True,
        help_text="Contextual text shown when this interaction is performed.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "interaction_type"],
                name="items_unique_template_interaction",
            )
        ]

    def __str__(self) -> str:
        return f"{self.template.name}: {self.interaction_type.label}"


class ItemTemplateAppearanceEffect(SharedMemoryModel):
    """Declares a cosmetic appearance edit an item template can perform on use.

    When a character uses an item whose template has appearance-effect rows,
    use_item calls change_appearance for each row, editing the character's
    real form in-place. The item IS the gate -- the player needs a cosmetic
    item to change a trait; they never ask 'is this trait editable?'

    clean() validates that the declared FormTrait has is_cosmetic=True,
    preventing misconfigured items from editing fixed traits (height, species
    markers) via the cosmetic path.
    """

    item_template = models.ForeignKey(
        ItemTemplate,
        on_delete=models.CASCADE,
        related_name="appearance_effects",
        help_text="The item template this cosmetic effect belongs to.",
    )
    trait = models.ForeignKey(
        "forms.FormTrait",
        on_delete=models.PROTECT,
        related_name="item_template_effects",
        help_text="The appearance trait this item can change (e.g., hair_color).",
    )
    target_option = models.ForeignKey(
        "forms.FormTraitOption",
        on_delete=models.PROTECT,
        related_name="item_template_effects",
        help_text="The value the trait is set to when this item is used.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item_template", "trait"],
                name="items_one_appearance_effect_per_trait_per_template",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_template.name}: {self.trait.display_name}"

    def clean(self) -> None:
        """Validate the target option belongs to the trait and the trait is cosmetic."""
        super().clean()
        if self.target_option_id is not None and self.target_option.trait_id != self.trait_id:
            raise ValidationError({"target_option": "Option does not belong to this trait."})
        if not self.trait.is_cosmetic:
            raise ValidationError(
                {"trait": f"{self.trait.display_name} is not a cosmetically editable trait."}
            )


class DisguiseKitEffect(SharedMemoryModel):
    """Declares a disguise overlay an item template can apply on use (#2249).

    When a character uses an item whose template has disguise-kit-effect rows,
    ``use_item`` calls ``apply_disguise`` for each row, painting a fake overlay
    over the character's real form. Unlike ``ItemTemplateAppearanceEffect``
    (which edits the real form in-place via ``change_appearance``), this applies
    a pierceable overlay — the real form is preserved beneath.

    ``disguise_kind`` records how the overlay is pierced (mundane → perception,
    magical → dispel). ``concealment_level`` controls what an unpierced viewer
    sees (#1272).
    """

    item_template = models.ForeignKey(
        ItemTemplate,
        on_delete=models.CASCADE,
        related_name="disguise_kit_effects",
        help_text="The item template this disguise-kit effect belongs to.",
    )
    disguise_kind = models.CharField(
        max_length=20,
        choices=DisguiseKind.choices,
        default=DisguiseKind.MUNDANE,
        help_text="How the overlay is pierced: mundane (perception) or magical (dispel).",
    )
    concealment_level = models.CharField(
        max_length=20,
        choices=ConcealmentLevel.choices,
        default=ConcealmentLevel.NONE,
        help_text="What the overlay conceals from an unpierced viewer (#1272).",
    )

    def __str__(self) -> str:
        return f"{self.item_template.name}: {self.get_disguise_kind_display()}"


class EquippedItem(SharedMemoryModel):
    """
    Tracks a currently equipped item on a character at a specific body region + layer.

    The unique constraint on (character, body_region, equipment_layer) ensures
    only one item per slot. Multi-region items create multiple EquippedItem rows.
    """

    character = models.ForeignKey(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="equipped_items",
        help_text="The character wearing/wielding this item.",
    )
    item_instance = models.ForeignKey(
        ItemInstance,
        on_delete=models.CASCADE,
        related_name="equipped_slots",
    )
    body_region = models.CharField(
        max_length=20,
        choices=BodyRegion.choices,
    )
    equipment_layer = models.CharField(
        max_length=20,
        choices=EquipmentLayer.choices,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character", "body_region", "equipment_layer"],
                name="items_unique_equipped_slot",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.item_instance.display_name} on "
            f"{self.get_body_region_display()}"
            f"/{self.get_equipment_layer_display()}"
        )


class RoomItem(SharedMemoryModel):
    """#676 Phase F — Placement of a decorative item in a room.

    Records that an ItemInstance is placed (as decor) in a specific
    RoomProfile. Mutually exclusive with EquippedItem at the service
    layer — ``place_item_in_room`` and ``equip_item`` both check the
    other state and refuse if it's set.

    When placed, the item's template ``polish_value`` flows into
    ``RoomPolish`` via ``apply_room_polish_delta``. On removal, the same
    delta is subtracted.
    """

    room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.CASCADE,
        related_name="placed_items",
    )
    item_instance = models.OneToOneField(
        ItemInstance,
        on_delete=models.CASCADE,
        related_name="room_placement",
        help_text=(
            "OneToOne — an item is placed in at most one room. "
            "Combined with the place/equip exclusivity check at the "
            "service layer, this enforces the spec's "
            "'placed XOR equipped' invariant."
        ),
    )

    def __str__(self) -> str:
        return f"{self.item_instance.display_name} in {self.room}"


class OwnershipEvent(SharedMemoryModel):
    """
    Append-only ledger tracking important ownership transitions.

    Records creation, gift, theft, and administrative transfers.
    """

    item_instance = models.ForeignKey(
        ItemInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ownership_events",
    )
    event_type = models.CharField(
        max_length=20,
        choices=OwnershipEventType.choices,
    )
    # #684: audit truth lives at the CharacterSheet (body) level. The
    # persona_display fields below snapshot how each side appeared IC at
    # the moment of transfer — narrative layer, never a permission gate.
    from_character_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items_given_away",
        help_text="Previous holder (null for creation events).",
    )
    to_character_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items_received",
        help_text="New holder.",
    )
    from_persona_display = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Persona the giver was presenting when the transfer happened. "
            "IC narrative only — the audit truth is from_character_sheet."
        ),
    )
    to_persona_display = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "Persona the receiver was presenting when the transfer happened. "
            "IC narrative only — the audit truth is to_character_sheet."
        ),
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional context for this event.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        display = self.item_instance.display_name if self.item_instance else "deleted"
        return f"{display}: {self.get_event_type_display()}"


class CurrencyBalance(SharedMemoryModel):
    """
    Abstract gold balance for a character.

    One currency (gold), not physical items. Tracked per character (IC possession),
    not per account.
    """

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="currency_balance",
        help_text="The character who holds this gold.",
    )
    gold = models.PositiveIntegerField(
        default=0,
        help_text="Current gold balance.",
    )

    def __str__(self) -> str:
        return f"{self.character}: {self.gold} gold"


class ItemAttachment(SharedMemoryModel):
    """Abstract base for tag models that attach a vocabulary term to an ItemInstance.

    Carries the three housekeeping fields shared by every attachment subclass:
    who applied it, at what quality, and when. The ``%(class)s`` token in the
    related_names expands to the concrete subclass name (e.g. ``itemfacet``,
    ``itemstyle``), giving each subclass its own distinct reverse accessor on
    AccountDB and QualityTier without collision.

    Concrete subclasses MUST declare their own ``item_instance`` FK with an
    explicit ``related_name`` so the hot ItemInstance accessors stay stable.
    """

    applied_by_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_applications",
    )
    attachment_quality_tier = models.ForeignKey(
        "items.QualityTier",
        on_delete=models.PROTECT,
        related_name="%(class)s_attachments",
    )
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class ItemFacet(ItemAttachment):
    """A single facet attached to an item instance.

    Spec D §4.2. Items carry facets either at craft time or via post-craft
    decoration. Each row carries its own attachment quality, independent of
    the item's overall quality tier. Threads anchor on the global Facet
    (not on ItemFacet); when computing wearer bonuses, the pipeline walks
    worn items → ItemFacet rows → matches against the wearer's Threads on
    those Facets.
    """

    item_instance = models.ForeignKey(
        _ITEM_INSTANCE_FK,
        on_delete=models.CASCADE,
        related_name="item_facets",
    )
    facet = models.ForeignKey(
        FACET_MODEL,
        on_delete=models.PROTECT,
        related_name="item_attachments",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item_instance", "facet"],
                name="items_unique_itemfacet_per_instance",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_instance} ← {self.facet}"


class ItemStyle(ItemAttachment):
    """A single aesthetic style tag attached to an item instance (#546).

    Parallel to ItemFacet: each row records which Style vocabulary term has
    been applied to the item, at what quality, and by whom. Items may carry
    multiple styles up to their template's ``style_capacity``.
    """

    item_instance = models.ForeignKey(
        _ITEM_INSTANCE_FK,
        on_delete=models.CASCADE,
        related_name="item_styles",
    )
    style = models.ForeignKey(
        "items.Style",
        on_delete=models.PROTECT,
        related_name="item_attachments",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item_instance", "style"],
                name="items_unique_itemstyle_per_instance",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_instance} ← {self.style}"


class Outfit(SharedMemoryModel):
    """A named saved look — a defined arrangement of items in body slots.

    Owned by a CharacterSheet (the source-of-truth above personas). Stored
    in a wardrobe (an ItemInstance whose template is_wardrobe=True).
    Applying an outfit equips its pieces atomically. Deleting an outfit
    removes the definition only — items are not affected.

    The model permits any wardrobe item regardless of who owns it; the
    service and REST layers enforce that the wardrobe is reachable by the
    character. Future shared-storage features (organizations, co-housing)
    can use this permissive shape.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    character_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="outfits",
    )
    wardrobe = models.ForeignKey(
        ItemInstance,
        on_delete=models.CASCADE,
        related_name="stored_outfits",
        help_text="The wardrobe ItemInstance this outfit is stored in.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "name"],
                name="items_outfit_unique_name_per_character",
            ),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if not self.wardrobe.template.is_wardrobe:
            raise ValidationError(
                {"wardrobe": "Outfits can only be stored in items flagged as wardrobes."}
            )

    @cached_property
    def cached_outfit_slots(self) -> list[OutfitSlot]:
        """Slots on this outfit, with item_instance + template prefetched.

        Cache target for ``Prefetch(..., to_attr="cached_outfit_slots")``.
        Falls back to a fresh query if accessed without prefetch.
        """
        return list(
            self.slots.select_related(
                "item_instance",
                "item_instance__template",
                "item_instance__quality_tier",
            ).all()
        )


class OutfitSlot(SharedMemoryModel):
    """One item assignment within an outfit definition.

    Mirrors EquippedItem's per-slot uniqueness. Multi-region items create
    multiple OutfitSlot rows just like EquippedItem.
    """

    outfit = models.ForeignKey(
        Outfit,
        on_delete=models.CASCADE,
        related_name="slots",
    )
    item_instance = models.ForeignKey(
        ItemInstance,
        on_delete=models.CASCADE,
        related_name="outfit_slots",
    )
    body_region = models.CharField(max_length=20, choices=BodyRegion.choices)
    equipment_layer = models.CharField(max_length=20, choices=EquipmentLayer.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["outfit", "body_region", "equipment_layer"],
                name="items_outfit_slot_unique_per_outfit",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.outfit.name}: {self.item_instance.display_name}"


class FashionPresentation(SharedMemoryModel):
    """A character modelling an outfit at an event, judged by a society (#514)."""

    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="fashion_presentations",
    )
    presenter = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="fashion_presentations",
    )
    outfit = models.ForeignKey(
        "items.Outfit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="presentations",
        help_text="The outfit presented (record-keeping; the check reads equipped items).",
    )
    perceiving_society = models.ForeignKey(
        SOCIETY_MODEL,
        on_delete=models.PROTECT,
        related_name="fashion_presentations",
    )
    base_score = models.IntegerField(
        default=0,
        help_text="Floor from the society-taste-shaped presentation check.",
    )
    acclaim = models.IntegerField(
        default=0,
        help_text="Final acclaim = base_score + heavily-weighted peer endorsements.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["presenter", "created_at"])]

    def __str__(self) -> str:
        return f"FashionPresentation({self.presenter_id}@{self.event_id})"


class FacetVogueMomentum(SharedMemoryModel):
    """Accumulating popularity of a facet within a society (#514).

    Bumped by acclaimed presentations (for the facets actually worn);
    cron-decayed. Read by the seasonal trendsetter ceremony to choose a
    society's new in-vogue facets.
    """

    society = models.ForeignKey(
        SOCIETY_MODEL,
        on_delete=models.CASCADE,
        related_name="facet_momentum",
    )
    facet = models.ForeignKey(
        FACET_MODEL,
        on_delete=models.CASCADE,
        related_name="vogue_momentum",
    )
    points = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["society", "facet"], name="unique_facet_momentum"),
        ]
        ordering = ["-points"]

    def __str__(self) -> str:
        return f"FacetVogueMomentum({self.society_id}/{self.facet_id}={self.points})"


class ItemCheckModifier(SharedMemoryModel):
    """Authored check modifier contributed by an item template when equipped.

    Mirrors ``ConditionCheckModifier``: one row per (template, check_type) pair
    carries a flat integer modifier.  When the character has an equipped item
    whose template has a matching row, ``collect_check_modifiers`` emits an
    EQUIPMENT ``ModifierContribution`` for it.

    Examples:
      - Padded boots give +5 to Stealth checks
      - A sorcerer's staff gives +10 to Arcane checks
      - Heavy plate armour gives -10 to Stealth checks
    """

    template = models.ForeignKey(
        ItemTemplate,
        on_delete=models.CASCADE,
        related_name="check_modifiers",
        help_text="Item template that carries this modifier.",
    )
    check_type = models.ForeignKey(
        CHECK_TYPE_MODEL,
        on_delete=models.CASCADE,
        related_name="item_check_modifiers",
        help_text="The check type this modifier affects.",
    )
    modifier_value = models.IntegerField(
        help_text=(
            "Flat modifier applied when the item is equipped "
            "(positive = bonus, negative = penalty)."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "check_type"],
                name="items_unique_itemcheckmodifier_per_template_check",
            )
        ]

    def __str__(self) -> str:
        sign = "+" if self.modifier_value >= 0 else ""
        return f"{self.template.name}: {sign}{self.modifier_value} to {self.check_type.name}"


class FashionStyle(NaturalKeyMixin, SharedMemoryModel):
    """An admin-authored 'what's in vogue' definition (Outfits Phase B, #513).

    A society points at its current FashionStyle; worn items carrying the
    style's in-vogue facets contribute a perception-relative fashion bonus.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    in_vogue_facets = models.ManyToManyField(
        FACET_MODEL,
        related_name="fashion_styles",
        blank=True,
        help_text="Facets that are currently fashionable in this style.",
    )
    in_vogue_styles = models.ManyToManyField(
        "items.Style",
        related_name="vogue_in",
        blank=True,
        help_text="Aesthetic styles (vocabulary words) that are currently fashionable.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Style(NaturalKeyMixin, SharedMemoryModel):
    """A staff-curated aesthetic vocabulary word (e.g. "Seductive", "Menacing", "Regal").

    Phase A of the magical-aesthetic-axis (#546). Later phases tag items with
    styles and bind them to resonances.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    audacity = models.IntegerField(
        choices=StyleAudacity.choices,
        default=StyleAudacity.EXPRESSIVE,
        help_text="How daring this style reads — scales its mechanical reward via "
        "AudacityTuning (#2029).",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class FashionStyleBonus(SharedMemoryModel):
    """Maps a FashionStyle to a check-type ModifierTarget it flatters.

    The authored ``weight`` is the magnitude multiplier applied to the worn
    facet-match value. 'All social' = one row per Social check-type target.
    """

    fashion_style = models.ForeignKey(
        "items.FashionStyle",
        on_delete=models.CASCADE,
        related_name="bonuses",
    )
    target = models.ForeignKey(
        "mechanics.ModifierTarget",
        on_delete=models.PROTECT,
        related_name="fashion_style_bonuses",
    )
    weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1,
        help_text="Authored magnitude multiplier on the worn facet-match value.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["fashion_style", "target"],
                name="items_unique_fashionstylebonus_per_target",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.fashion_style.name} → {self.target.name} (x{self.weight})"


class AudacityTuning(SharedMemoryModel):
    """Singleton tuning surface (pk=1) for the per-``StyleAudacity``-tier reward
    multiplier (#2029).

    Staff-tunable knob scaling how much more (or less) daring ``Style`` rows are
    mechanically rewarded, consumed by both the passive motif-coherence bonus
    (``_compute_motif_coherence_bonus`` in ``world/mechanics/services.py``) and peer
    style-presentation endorsements (``create_style_presentation_endorsement`` in
    ``world/magic/services/gain.py``). Access via ``get_audacity_tuning()``
    (``world/items/services/styles.py``) — singleton-by-convention, no DB-level
    uniqueness constraint (mirrors ``RelationshipBondPullTuning``).
    """

    objects = ArxSharedMemoryManager()

    understated_mult = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("0.75"),
        help_text="Reward multiplier for UNDERSTATED-audacity styles.",
    )
    expressive_mult = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Reward multiplier for EXPRESSIVE-audacity styles.",
    )
    bold_mult = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.35"),
        help_text="Reward multiplier for BOLD-audacity styles.",
    )
    outrageous_mult = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.75"),
        help_text="Reward multiplier for OUTRAGEOUS-audacity styles.",
    )

    def __str__(self) -> str:
        return f"AudacityTuning(pk={self.pk})"

    def multiplier_for(self, audacity: int) -> Decimal:
        """Return the tuned multiplier for a ``StyleAudacity`` ordinal.

        Falls back to ``expressive_mult`` for an unrecognized value rather than
        raising, so a stray/legacy int never crashes a reward computation.
        """
        return {
            StyleAudacity.UNDERSTATED: self.understated_mult,
            StyleAudacity.EXPRESSIVE: self.expressive_mult,
            StyleAudacity.BOLD: self.bold_mult,
            StyleAudacity.OUTRAGEOUS: self.outrageous_mult,
        }.get(audacity, self.expressive_mult)


class Mantle(SharedMemoryModel):
    """An attunable artifact with a story.

    Each Mantle is one specific ItemInstance in the world (a particular
    sword, amulet, banner, etc.) — not a category. The OneToOne FK to
    ItemInstance makes that explicit: at most one Mantle per item, at most
    one item per Mantle. Multiple mantles can share an ItemTemplate (two
    mantles that are both swords are two different ItemInstances of the
    "Sword" template), with no conflict.

    PROTECT on the FK prevents accidental deletion of an ItemInstance that
    has mantle metadata; staff would need to explicitly retire the Mantle
    first.

    Each Mantle has 1..N authored levels (MantleLevelDefinition rows). Characters
    progress by clearing each level's research (CodexEntry) + mission gates
    in order, recording MantleLevelClearance rows. Attunement to a mantle is
    represented as a Thread of kind=MANTLE anchored on the Mantle; the
    thread's level cannot exceed the character's max-cleared mantle level.
    Each character must clear gates and weave their own thread separately.
    """

    item_instance = models.OneToOneField(
        _ITEM_INSTANCE_FK,
        on_delete=models.PROTECT,
        related_name="mantle",
        help_text="The unique ItemInstance that is this Mantle.",
    )
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(
        help_text="The flavor lore visible to authors and (selectively) players.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="If false, attunement weaving is blocked.",
    )
    max_level = models.PositiveSmallIntegerField(
        default=5,
        help_text="How many attunement levels exist for this mantle.",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(max_level__gte=1) & models.Q(max_level__lte=10),
                name="items_mantle_max_level_range",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class MantleLevelDefinition(SharedMemoryModel):
    """Authored content for a single mantle level.

    Each level requires both a Codex entry to be researched and a mission
    to be completed before the level's clearance can be recorded.
    """

    mantle = models.ForeignKey(
        Mantle,
        on_delete=models.CASCADE,
        related_name="level_defs",
    )
    level = models.PositiveSmallIntegerField()
    codex_entry_required = models.ForeignKey(
        "codex.CodexEntry",
        on_delete=models.PROTECT,
        related_name="mantle_level_gates",
        help_text="Lore the character must research before this level can clear.",
    )

    # No `mission_required` FK in this spec. Mission system is a future
    # spec; once it ships, that spec adds a `mission_required` FK to
    # MantleLevelDefinition via migration and updates the clearance logic
    # to require both gates. PR2 of this spec gates mantle clearances by
    # Codex research alone.
    unlock_description = models.TextField(
        help_text="Player-facing description of what this level grants.",
    )

    class Meta:
        ordering = ["level"]
        constraints = [
            models.UniqueConstraint(
                fields=["mantle", "level"],
                name="items_unique_mantle_level",
            ),
        ]


class MantleLevelClearance(SharedMemoryModel):
    """Per-character record that a mantle's level N gates have been cleared.

    Created when both research and mission gates are met. Existence of a
    clearance row at level N raises the character's effective MANTLE thread
    cap on that mantle to N × 10 (subject to path cap min).
    """

    character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="mantle_clearances",
    )
    mantle = models.ForeignKey(
        Mantle,
        on_delete=models.CASCADE,
        related_name="clearances",
    )
    level = models.PositiveSmallIntegerField()
    cleared_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["level"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "mantle", "level"],
                name="items_unique_mantle_clearance_per_character",
            ),
        ]


class Trendsetter(SharedMemoryModel):
    """A crowned 'toast of the season' whose look set a society's trend (#514)."""

    society = models.ForeignKey(
        SOCIETY_MODEL,
        on_delete=models.CASCADE,
        related_name="trendsetters",
    )
    persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.CASCADE,
        related_name="trendsetter_crownings",
    )
    fashion_style = models.ForeignKey(
        "items.FashionStyle",
        on_delete=models.CASCADE,
        related_name="trendsetter_crownings",
    )
    crowned_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-crowned_at"]

    def __str__(self) -> str:
        return f"Trendsetter({self.persona_id} for society {self.society_id})"


class GarmentMitigation(SharedMemoryModel):
    """One exposure axis a garment template mitigates while worn (#1522/#1514 comfort).

    ``(item_template, stat_key, resonance) -> value``: a worn garment reduces what its wearer
    *feels* on that axis (a fur coat → COLD; a sun hat → HEAT), floored at 0 — it never makes the
    wearer colder or touches another axis. Mirrors the ``(parent, stat_key, value)`` affinity
    pattern (``buildings.StyleAffinity`` / ``weather.WeatherTypeExposure``), but read **per
    character** (off the wearer's ``EquippedItem`` rows), not materialized onto a room.

    A ``resonance`` row marks a *magical* mitigation (an imbued/woven garment): authored large, so
    a scantily-clad but resonance-warded character still shrugs off the cold. Mundane mitigation
    leaves ``resonance`` null. Magnitudes are a PLACEHOLDER author pass; the deeper
    imbuing-drives-this integration (per-instance, via the magic Thread/Facet system) is a
    follow-up — this is the authored-on-the-kind first cut.
    """

    item_template = models.ForeignKey(
        ItemTemplate,
        on_delete=models.CASCADE,
        related_name="garment_mitigations",
    )
    stat_key = models.CharField(max_length=20, choices=StatKey.choices)
    value = models.PositiveIntegerField(
        help_text="How much felt exposure this garment removes on the axis while worn.",
    )
    resonance = models.ForeignKey(
        RESONANCE_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="garment_mitigations",
        help_text=(
            "Set when this mitigation is magically imbued — a big comfort swing independent of "
            "coverage. Null = mundane (material/fit). PLACEHOLDER magnitudes."
        ),
    )

    class Meta:
        ordering = ["item_template", "stat_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["item_template", "stat_key", "resonance"],
                name="items_unique_garment_mitigation",
            ),
        ]

    def __str__(self) -> str:
        tag = f" [{self.resonance.name}]" if self.resonance_id else ""
        return f"{self.item_template.name}: {self.stat_key} -{self.value}{tag}"


# ---------------------------------------------------------------------------
# Crafting submodule — import last so all models above are registered first
# ---------------------------------------------------------------------------
from world.items.crafting.models import (  # noqa: E402,F401
    CraftedItemRecipe,
    CraftingMaterialRequirement,
    CraftingRecipe,
    CraftingRecipeConsequence,
    CraftingRecipeModifier,
    CraftingSkillCap,
)

# ---------------------------------------------------------------------------
# Gems submodule (Build 0b) — gem value model
# ---------------------------------------------------------------------------
from world.items.gems.models import (  # noqa: E402,F401
    Adornment,
    CommonGemBucket,
    GemDetails,
    GemGrade,
    GemInstanceDetails,
    OrgGemStock,
    PendingRareFind,
    StreamCommonGemPool,
)

# ---------------------------------------------------------------------------
# Market submodule (#2066) — import last so all models above register first
# ---------------------------------------------------------------------------
from world.items.market.models import (  # noqa: E402,F401
    CraftingServiceOffer,
    FinishingPass,
    MarketSale,
    MarketSquare,
    MarketStall,
    StockListing,
    WareListing,
)

# ---------------------------------------------------------------------------
# Org vault (#2540 Layer 4) — logical org custody of items
# ---------------------------------------------------------------------------
from world.items.org_vault_models import (  # noqa: E402,F401
    OrganizationVault,
    OrgVaultEvent,
    VaultHolding,
)


class ReclamationClaim(SharedMemoryModel):
    """A wronged party's live claim on a stolen item (#2368).

    The provenance ledger records the truth; the claim unlocks the trace over
    it. ``original_claimant_sheet`` is the immunity anchor — reclamation
    standing (steal it back, no crime) belongs to the wronged alone and never
    transfers with the claim (assignment moves the trace + lawful route only).
    The current holder is never notified a claim exists.
    """

    item_instance = models.ForeignKey(
        ItemInstance, on_delete=models.CASCADE, related_name="reclamation_claims"
    )
    claimant_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK, on_delete=models.CASCADE, related_name="reclamation_claims"
    )
    original_claimant_sheet = models.ForeignKey(
        _CHARACTER_SHEET_FK,
        on_delete=models.CASCADE,
        related_name="original_reclamation_claims",
        help_text="Set once at minting; the immunity anchor. Never reassigned.",
    )
    origin = models.CharField(max_length=30)
    estate_claim = models.ForeignKey(
        "estates.EstateClaim",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reclamation_claims",
        help_text="The heir grievance this trace was opened from, when any.",
    )
    acquired_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignments",
        help_text="Assignment lineage — a claim is a sellable document.",
    )
    status = models.CharField(max_length=30, default="open")
    trace_position = models.PositiveSmallIntegerField(
        default=0, help_text="Hops of the ownership chain revealed so far."
    )
    trace_chilled_until = models.DateTimeField(null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["item_instance", "claimant_sheet"],
                condition=models.Q(status="open"),
                name="one_open_claim_per_item_claimant",
            ),
        ]

    def __str__(self) -> str:
        return f"claim ({self.status}) on item {self.item_instance_id}"


class ClaimTraceStep(SharedMemoryModel):
    """One earned hop of a claim's trace (#2368) — the claimant's mystery log.

    Hops are revealed one at a time (never a free read of the full chain);
    each step's prose names the transfer in-world terms. Authored mystery
    content may layer via clue triggers; these rows are the procedural floor.
    """

    claim = models.ForeignKey(
        ReclamationClaim, on_delete=models.CASCADE, related_name="trace_steps"
    )
    position = models.PositiveSmallIntegerField()
    ownership_event = models.ForeignKey(
        OwnershipEvent, on_delete=models.CASCADE, related_name="trace_steps"
    )
    revealed_text = models.TextField(blank=True)
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["claim", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["claim", "position"], name="one_step_per_claim_position"
            ),
        ]

    def __str__(self) -> str:
        return f"trace step {self.position} of claim {self.claim_id}"
