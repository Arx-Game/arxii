"""Models for items, equipment, and inventory."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia_extensions.models import PlayerMedia

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils.functional import cached_property
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.items.constants import BodyRegion, EquipmentLayer, GearArchetype, OwnershipEventType


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


class ItemTemplate(SharedMemoryModel):
    """
    Archetype definition for an item type (e.g., "iron longsword", "silk shirt").

    Templates define shared base properties. Individual items in the world are
    ItemInstance records that reference their template for defaults, with
    per-instance overrides for customization (custom names, descriptions, etc.).
    """

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
    image = models.ForeignKey(
        "evennia_extensions.PlayerMedia",
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
    gear_archetype = models.CharField(
        max_length=20,
        choices=GearArchetype.choices,
        default=GearArchetype.OTHER,
        help_text=(
            "Gear category. Drives covenant role × gear compatibility. "
            "Immutable across instances of this template."
        ),
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
        ]

    def __str__(self) -> str:
        return self.name

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


class ItemInstance(SharedMemoryModel):
    """
    A specific item that exists in the game world.

    References an ItemTemplate for base properties, with per-instance overrides
    for custom names, descriptions, quality, and state.
    """

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
    is_open = models.BooleanField(
        default=False,
        help_text="Whether this item is currently open.",
    )
    # #684: ownership is CharacterSheet-scoped — the body owns the item, not
    # the account. One inventory per character; personas are a display layer
    # over the same underlying gear. See docs in the spec on the GitHub issue.
    holder_character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
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
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crafted_items",
        help_text="The body that crafted this item.",
    )
    crafter_persona_display = models.ForeignKey(
        "scenes.Persona",
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
    contained_in = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contents",
        help_text=("Container item this item is stored inside (null = not in a container)."),
    )
    image = models.ForeignKey(
        "evennia_extensions.PlayerMedia",
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
    def display_image(self) -> PlayerMedia | None:
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
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items_given_away",
        help_text="Previous holder (null for creation events).",
    )
    to_character_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items_received",
        help_text="New holder.",
    )
    from_persona_display = models.ForeignKey(
        "scenes.Persona",
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
        "scenes.Persona",
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


class ItemFacet(SharedMemoryModel):
    """A single facet attached to an item instance.

    Spec D §4.2. Items carry facets either at craft time or via post-craft
    decoration. Each row carries its own attachment quality, independent of
    the item's overall quality tier. Threads anchor on the global Facet
    (not on ItemFacet); when computing wearer bonuses, the pipeline walks
    worn items → ItemFacet rows → matches against the wearer's Threads on
    those Facets.
    """

    item_instance = models.ForeignKey(
        "items.ItemInstance",
        on_delete=models.CASCADE,
        related_name="item_facets",
    )
    facet = models.ForeignKey(
        "magic.Facet",
        on_delete=models.PROTECT,
        related_name="item_attachments",
    )
    applied_by_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facet_applications",
    )
    attachment_quality_tier = models.ForeignKey(
        "items.QualityTier",
        on_delete=models.PROTECT,
        related_name="facet_attachments",
    )
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item_instance", "facet"],
                name="items_unique_itemfacet_per_instance",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.item_instance} ← {self.facet}"


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
        "character_sheets.CharacterSheet",
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
