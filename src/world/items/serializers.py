"""DRF serializers for items API."""

from __future__ import annotations

from rest_framework import serializers

from flows.service_functions.outfits import (
    add_outfit_slot,
    save_outfit,
)
from world.items.exceptions import (
    NotAContainer,
    NotReachable,
    PermissionDenied,
    SlotIncompatible,
)
from world.items.models import (
    EquippedItem,
    FashionPresentation,
    InteractionType,
    ItemFacet,
    ItemInstance,
    ItemStyle,
    ItemTemplate,
    Outfit,
    OutfitSlot,
    QualityTier,
    TemplateInteraction,
    TemplateSlot,
)
from world.magic.models.endorsement import PresentationEndorsement


class QualityTierSerializer(serializers.ModelSerializer):
    """Serializer for QualityTier lookup records."""

    class Meta:
        model = QualityTier
        fields = [
            "id",
            "name",
            "color_hex",
            "numeric_min",
            "numeric_max",
            "stat_multiplier",
            "sort_order",
        ]
        read_only_fields = fields


class InteractionTypeSerializer(serializers.ModelSerializer):
    """Serializer for InteractionType lookup records."""

    class Meta:
        model = InteractionType
        fields = ["id", "name", "label", "description"]
        read_only_fields = fields


class UseItemSerializer(serializers.Serializer):
    """Request body for the inventory ``use`` action.

    Intentionally empty: the REST endpoint applies on-use effects to the
    holder (self) only. Targeted use belongs in the future use-item Action
    layer, which has proximity/prerequisite checks; accepting a target pk
    here would let a player apply on-use effects to any character by pk.
    """


class UseItemResultSerializer(serializers.Serializer):
    """Response shape mirroring ``UseItemResult`` (issue #509)."""

    charges_remaining = serializers.IntegerField()
    destroyed = serializers.BooleanField()
    soft_deleted = serializers.BooleanField()
    applied_effect_count = serializers.IntegerField()


class TemplateSlotSerializer(serializers.ModelSerializer):
    """Serializer for TemplateSlot (region/layer assignment)."""

    body_region_display = serializers.CharField(source="get_body_region_display", read_only=True)
    equipment_layer_display = serializers.CharField(
        source="get_equipment_layer_display", read_only=True
    )

    class Meta:
        model = TemplateSlot
        fields = [
            "body_region",
            "body_region_display",
            "equipment_layer",
            "equipment_layer_display",
            "covers_lower_layers",
        ]
        read_only_fields = fields


class TemplateInteractionSerializer(serializers.ModelSerializer):
    """Serializer for interaction bindings with flavor text."""

    interaction_type = InteractionTypeSerializer(read_only=True)

    class Meta:
        model = TemplateInteraction
        fields = ["interaction_type", "flavor_text"]
        read_only_fields = fields


class ItemFacetReadSerializer(serializers.ModelSerializer):
    """Read serializer for ItemFacet (GET list/detail)."""

    class Meta:
        model = ItemFacet
        fields = [
            "id",
            "item_instance",
            "facet",
            "applied_by_account",
            "attachment_quality_tier",
            "applied_at",
        ]
        read_only_fields = fields


class ItemFacetWriteSerializer(serializers.ModelSerializer):
    """Write serializer for ItemFacet (POST create) — input validation only.

    The viewset drives the crafting service directly; this serializer parses
    and validates the ``item_instance`` and ``facet`` foreign keys.
    """

    class Meta:
        model = ItemFacet
        fields = ["item_instance", "facet"]
        # DRF auto-injects a UniqueTogetherValidator from
        # UniqueConstraint(item_instance, facet); suppress it so the
        # FacetAlreadyAttached exception in the service raises a user-message
        # error instead of DRF's generic "must make a unique set" message.
        validators: list = []


class FacetCraftResultSerializer(serializers.Serializer):
    """Response for a facet-craft attempt: rolled outcome + resolved tier + the row."""

    attached = serializers.BooleanField()
    outcome_name = serializers.SerializerMethodField()
    success_level = serializers.SerializerMethodField()
    quality_tier = QualityTierSerializer(allow_null=True)
    item_facet = ItemFacetReadSerializer(allow_null=True)
    consumed = serializers.DictField(allow_null=True)
    consequence_label = serializers.CharField(allow_null=True)

    def get_outcome_name(self, obj) -> str | None:
        return obj.outcome.name if obj.outcome else None

    def get_success_level(self, obj) -> int | None:
        return obj.outcome.success_level if obj.outcome else None


class ItemStyleReadSerializer(serializers.ModelSerializer):
    """Read serializer for ItemStyle (GET list/detail)."""

    class Meta:
        model = ItemStyle
        fields = [
            "id",
            "item_instance",
            "style",
            "applied_by_account",
            "attachment_quality_tier",
            "applied_at",
        ]
        read_only_fields = fields


class ItemStyleWriteSerializer(serializers.ModelSerializer):
    """Write serializer for ItemStyle (POST create) — input validation only.

    The viewset drives the crafting service directly; this serializer parses
    and validates the ``item_instance`` and ``style`` foreign keys.
    """

    class Meta:
        model = ItemStyle
        fields = ["item_instance", "style"]
        # DRF auto-injects a UniqueTogetherValidator from
        # UniqueConstraint(item_instance, style); suppress it so the
        # StyleAlreadyAttached exception in the service raises a user-message
        # error instead of DRF's generic "must make a unique set" message.
        validators: list = []


class StyleCraftResultSerializer(serializers.Serializer):
    """Response for a style-craft attempt: rolled outcome + resolved tier + the row."""

    attached = serializers.BooleanField()
    outcome_name = serializers.SerializerMethodField()
    success_level = serializers.SerializerMethodField()
    quality_tier = QualityTierSerializer(allow_null=True)
    item_style = ItemStyleReadSerializer(allow_null=True)
    consumed = serializers.DictField(allow_null=True)
    consequence_label = serializers.CharField(allow_null=True)

    def get_outcome_name(self, obj) -> str | None:
        return obj.outcome.name if obj.outcome else None

    def get_success_level(self, obj) -> int | None:
        return obj.outcome.success_level if obj.outcome else None


class CraftingQuoteMaterialSerializer(serializers.Serializer):
    """One material requirement row within a crafting quote."""

    item_template_id = serializers.IntegerField()
    name = serializers.CharField()
    quantity_required = serializers.IntegerField()
    have = serializers.IntegerField()


class CraftingQuoteCostSerializer(serializers.Serializer):
    """Resource cost breakdown within a crafting quote."""

    action_points = serializers.IntegerField()
    action_points_have = serializers.IntegerField()
    anima = serializers.IntegerField()
    anima_have = serializers.IntegerField()
    materials = CraftingQuoteMaterialSerializer(many=True)


class CraftingQuoteRiskSerializer(serializers.Serializer):
    """A single failure-risk row within a crafting quote."""

    outcome_name = serializers.CharField(allow_null=True)
    cost_consumption = serializers.CharField()
    label = serializers.CharField(allow_null=True)


class CraftingQuoteSerializer(serializers.Serializer):
    """Read-only quote: costs, affordability, max quality tier, failure risks."""

    costs = CraftingQuoteCostSerializer()
    affordable = serializers.BooleanField()
    max_quality_tier = QualityTierSerializer(allow_null=True)
    failure_risk = CraftingQuoteRiskSerializer(many=True)


class EquippedItemReadSerializer(serializers.ModelSerializer):
    """Read serializer for EquippedItem (GET list/detail)."""

    body_region_display = serializers.CharField(source="get_body_region_display", read_only=True)
    equipment_layer_display = serializers.CharField(
        source="get_equipment_layer_display", read_only=True
    )

    class Meta:
        model = EquippedItem
        fields = [
            "id",
            "character",
            "item_instance",
            "body_region",
            "equipment_layer",
            "body_region_display",
            "equipment_layer_display",
        ]
        read_only_fields = fields


class ItemTemplateListSerializer(serializers.ModelSerializer):
    """List serializer for ItemTemplate (minimal fields)."""

    image_url = serializers.CharField(source="image.cloudinary_url", default=None, read_only=True)

    class Meta:
        model = ItemTemplate
        fields = [
            "id",
            "name",
            "weight",
            "size",
            "value",
            "is_container",
            "is_stackable",
            "is_consumable",
            "is_craftable",
            "image_url",
        ]
        read_only_fields = fields


class ItemInstanceReadSerializer(serializers.ModelSerializer):
    """Read serializer for ItemInstance — used by the inventory listing."""

    template = ItemTemplateListSerializer(read_only=True)
    quality_tier = QualityTierSerializer(read_only=True)
    display_name = serializers.CharField(read_only=True)
    display_description = serializers.CharField(read_only=True)
    display_image_url = serializers.SerializerMethodField()
    is_usable = serializers.SerializerMethodField()
    contained_in = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ItemInstance
        fields = [
            "id",
            "template",
            "quality_tier",
            "display_name",
            "display_description",
            "display_image_url",
            "is_usable",
            "contained_in",
            "quantity",
            "charges",
            "is_open",
        ]
        read_only_fields = fields

    def get_display_image_url(self, obj: ItemInstance) -> str | None:
        """Return the cloudinary URL for the item's display image, if any."""
        media = obj.display_image
        return media.cloudinary_url if media else None

    def get_is_usable(self, obj: ItemInstance) -> bool:
        """True iff use_item would proceed: the template has an on-use pool.
        Mirrors the precondition in services.usage.use_item."""
        return obj.template.on_use_pool_id is not None


class VisibleWornItemSerializer(serializers.Serializer):
    """Slim shape for ``VisibleWornItem`` dataclass entries.

    Used by the ``visible-worn`` list endpoint — exposes only the bits
    needed to render a per-character "what they're wearing" listing
    (id + display name + region + layer). For full per-item data the
    client follows up with the visible-item-detail endpoint.
    """

    id = serializers.IntegerField(source="item_instance.id", read_only=True)
    display_name = serializers.CharField(source="item_instance.display_name", read_only=True)
    body_region = serializers.CharField(read_only=True)
    equipment_layer = serializers.CharField(read_only=True)


class ItemTemplateDetailSerializer(serializers.ModelSerializer):
    """Detail serializer for ItemTemplate with slots and interactions."""

    slots = TemplateSlotSerializer(source="cached_slots", many=True, read_only=True)
    interactions = TemplateInteractionSerializer(
        source="cached_interaction_bindings", many=True, read_only=True
    )
    minimum_quality_tier = QualityTierSerializer(read_only=True)
    image_url = serializers.CharField(source="image.cloudinary_url", default=None, read_only=True)

    class Meta:
        model = ItemTemplate
        fields = [
            "id",
            "name",
            "description",
            "weight",
            "size",
            "value",
            "is_container",
            "container_capacity",
            "container_max_item_size",
            "is_stackable",
            "max_stack_size",
            "is_consumable",
            "max_charges",
            "is_craftable",
            "minimum_quality_tier",
            "supports_open_close",
            "slots",
            "interactions",
            "image_url",
        ]
        read_only_fields = fields


class OutfitSlotReadSerializer(serializers.ModelSerializer):
    """Read serializer for OutfitSlot — nests the item instance."""

    item_instance = ItemInstanceReadSerializer(read_only=True)

    class Meta:
        model = OutfitSlot
        fields = ["id", "outfit", "item_instance", "body_region", "equipment_layer"]
        read_only_fields = fields


class OutfitSlotWriteSerializer(serializers.ModelSerializer):
    """Write serializer for OutfitSlot — delegates to add_outfit_slot service."""

    class Meta:
        model = OutfitSlot
        fields = ["id", "outfit", "item_instance", "body_region", "equipment_layer"]
        # DRF auto-injects a UniqueTogetherValidator from
        # UniqueConstraint(outfit, body_region, equipment_layer); suppress it
        # so add_outfit_slot can replace the existing slot at that (region,
        # layer) instead of erroring out at validation.
        validators: list = []

    def create(self, validated_data: dict) -> OutfitSlot:  # type: ignore[override]
        """Delegate creation to the add_outfit_slot service.

        The service validates template compatibility and item ownership,
        and replaces any existing slot at the same (region, layer).
        """
        try:
            return add_outfit_slot(
                outfit=validated_data["outfit"],
                item_instance=validated_data["item_instance"],
                body_region=validated_data["body_region"],
                equipment_layer=validated_data["equipment_layer"],
            )
        except SlotIncompatible as exc:
            raise serializers.ValidationError({"non_field_errors": [exc.user_message]}) from exc
        except PermissionDenied as exc:
            raise serializers.ValidationError({"item_instance": [exc.user_message]}) from exc


class OutfitReadSerializer(serializers.ModelSerializer):
    """Read serializer for Outfit — nests slot rows."""

    slots = OutfitSlotReadSerializer(source="cached_outfit_slots", many=True, read_only=True)

    class Meta:
        model = Outfit
        fields = [
            "id",
            "name",
            "description",
            "character_sheet",
            "wardrobe",
            "slots",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OutfitWriteSerializer(serializers.ModelSerializer):
    """Write serializer for Outfit — POST snapshots current loadout via save_outfit."""

    class Meta:
        model = Outfit
        fields = ["id", "name", "description", "character_sheet", "wardrobe"]

    def create(self, validated_data: dict) -> Outfit:  # type: ignore[override]
        """Delegate creation to the save_outfit service.

        The service captures the current EquippedItem loadout for the
        sheet's character into OutfitSlot rows.
        """
        try:
            return save_outfit(
                character_sheet=validated_data["character_sheet"],
                wardrobe=validated_data["wardrobe"],
                name=validated_data["name"],
                description=validated_data.get("description", ""),
            )
        except NotAContainer as exc:
            raise serializers.ValidationError({"wardrobe": [exc.user_message]}) from exc
        except NotReachable as exc:
            raise serializers.ValidationError({"wardrobe": [exc.user_message]}) from exc

    def update(self, instance: Outfit, validated_data: dict) -> Outfit:  # type: ignore[override]
        """Update only renames/redescribes — character_sheet and wardrobe are write-once.

        Allowing PATCH to change ``character_sheet`` would let a user transfer
        an outfit to a different character; allowing PATCH to change
        ``wardrobe`` would let them relocate the outfit's anchor item to any
        item id on the planet. Both are silently dropped here — the serializer
        accepts the fields on POST (for create) but ignores them on PATCH.

        Note: the OutfitViewSet's PUT/PATCH endpoints declare
        ``OutfitRenameSerializer`` (below) to the schema instead, so OpenAPI
        consumers see the accurate field set. This serializer's update path
        only fires if a caller bypasses the viewset and reuses this class
        directly for PATCH.
        """
        validated_data.pop("character_sheet", None)
        validated_data.pop("wardrobe", None)
        return super().update(instance, validated_data)


class OutfitRenameSerializer(serializers.ModelSerializer):
    """Write serializer for renames/redescribes (PUT / PATCH on Outfit).

    Distinct from ``OutfitWriteSerializer`` because update only touches
    ``name`` and ``description`` — exposing ``character_sheet`` and
    ``wardrobe`` in the request schema would imply they're editable when
    they're write-once. The viewset wires this serializer via
    ``@extend_schema`` on update/partial_update so the public API contract
    matches reality.
    """

    class Meta:
        model = Outfit
        fields = ["id", "name", "description"]


class FashionPresentationSerializer(serializers.ModelSerializer):
    """Serializer for FashionPresentation create + read (#514).

    Write: accepts ``event`` (required) + optional ``outfit`` PKs from the
    request body. The ``presenter`` is resolved from the requesting account in
    the view (``FashionPresentationViewSet.perform_create``) and injected via
    ``serializer.save(presenter=sheet)`` — never supplied by the client
    (mirrors the endorsement views' ``endorser_sheet`` handling).

    Read: all fields are present; read-only fields cannot be supplied.
    """

    class Meta:
        model = FashionPresentation
        fields = [
            "id",
            "event",
            "presenter",
            "outfit",
            "perceiving_society",
            "base_score",
            "acclaim",
            "created_at",
        ]
        read_only_fields = [
            "presenter",
            "perceiving_society",
            "base_score",
            "acclaim",
            "created_at",
        ]

    def create(self, validated_data: dict) -> FashionPresentation:  # type: ignore[override]
        """Delegate to ``present_outfit``; surface service errors as 400."""
        from world.items.exceptions import FashionPresentationError  # noqa: PLC0415
        from world.items.services.fashion_presentation import present_outfit  # noqa: PLC0415

        presenter = validated_data.pop("presenter")
        event = validated_data["event"]
        outfit = validated_data.get("outfit")
        try:
            return present_outfit(presenter, event, outfit)
        except FashionPresentationError as exc:
            raise serializers.ValidationError({"detail": exc.user_message}) from exc


class FashionJudgementSerializer(serializers.Serializer):
    """Serializer for judging a fashion presentation (#514).

    Write: accepts ``presentation`` PK from the request body. The ``judge`` is
    resolved from the requesting account in the view and injected via
    ``serializer.save(judge=sheet)`` — never supplied by the client. On success
    the created ``PresentationEndorsement`` is exposed via the
    ``PresentationEndorsementSerializer`` read shape.
    """

    presentation = serializers.PrimaryKeyRelatedField(
        queryset=FashionPresentation.objects.all(),
    )

    def create(self, validated_data: dict) -> PresentationEndorsement:
        """Delegate to ``judge_presentation``; surface service errors as 400."""
        from world.items.exceptions import FashionPresentationError  # noqa: PLC0415
        from world.items.services.fashion_presentation import judge_presentation  # noqa: PLC0415

        judge = validated_data.pop("judge")
        presentation = validated_data["presentation"]
        try:
            return judge_presentation(judge, presentation)
        except FashionPresentationError as exc:
            raise serializers.ValidationError({"detail": exc.user_message}) from exc


class PresentationEndorsementSerializer(serializers.ModelSerializer):
    """Read serializer for PresentationEndorsement rows (#514)."""

    class Meta:
        model = PresentationEndorsement
        fields = [
            "id",
            "presentation",
            "endorser_sheet",
            "endorsee_sheet",
            "persona_snapshot",
            "weight",
            "created_at",
        ]
        read_only_fields = fields
