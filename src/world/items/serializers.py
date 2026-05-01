"""DRF serializers for items API."""

from rest_framework import serializers

from world.items.exceptions import (
    FacetAlreadyAttached,
    FacetCapacityExceeded,
)
from world.items.models import (
    EquippedItem,
    InteractionType,
    ItemFacet,
    ItemInstance,
    ItemTemplate,
    QualityTier,
    TemplateInteraction,
    TemplateSlot,
)
from world.items.services.facets import attach_facet_to_item


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
    """Write serializer for ItemFacet (POST create)."""

    class Meta:
        model = ItemFacet
        fields = ["item_instance", "facet", "attachment_quality_tier"]

    def create(self, validated_data: dict) -> ItemFacet:  # type: ignore[override]  # DRF base returns Model; we narrow to ItemFacet
        """Delegate creation to the facet service."""
        crafter = self.context["request"].user
        try:
            return attach_facet_to_item(
                crafter=crafter,
                item_instance=validated_data["item_instance"],
                facet=validated_data["facet"],
                attachment_quality_tier=validated_data["attachment_quality_tier"],
            )
        except FacetAlreadyAttached as exc:
            raise serializers.ValidationError({"non_field_errors": [exc.user_message]}) from exc
        except FacetCapacityExceeded as exc:
            raise serializers.ValidationError({"non_field_errors": [exc.user_message]}) from exc


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
