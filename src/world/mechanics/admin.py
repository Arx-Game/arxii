"""
Mechanics System Admin

Admin configuration for game mechanics models.
"""

from django.contrib import admin

from world.mechanics.models import (
    CharacterModifier,
    ModifierCategory,
    ModifierSource,
    ModifierType,
)

DESCRIPTION_TRUNCATE_LENGTH = 50


@admin.register(ModifierCategory)
class ModifierCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "description_truncated", "display_order"]
    search_fields = ["name", "description"]
    ordering = ["display_order", "name"]
    list_editable = ["display_order"]

    @admin.display(description="Description")
    def description_truncated(self, obj):
        if obj.description and len(obj.description) > DESCRIPTION_TRUNCATE_LENGTH:
            return obj.description[:DESCRIPTION_TRUNCATE_LENGTH] + "..."
        return obj.description or ""


@admin.register(ModifierType)
class ModifierTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "display_order", "is_active"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "description"]
    ordering = ["category__display_order", "display_order", "name"]
    list_editable = ["display_order", "is_active"]
    list_select_related = ["category"]


@admin.register(ModifierSource)
class ModifierSourceAdmin(admin.ModelAdmin):
    list_display = ["id", "source_type", "source_display"]
    list_filter = [
        ("distinction_effect", admin.EmptyFieldListFilter),
        ("condition_instance", admin.EmptyFieldListFilter),
    ]
    raw_id_fields = ["distinction_effect", "character_distinction", "condition_instance"]

    @admin.display(description="Type")
    def source_type(self, obj):
        if obj.distinction_effect_id or obj.character_distinction_id:
            return "Distinction"
        if obj.condition_instance_id:
            return "Condition"
        return "Unknown"


@admin.register(CharacterModifier)
class CharacterModifierAdmin(admin.ModelAdmin):
    list_display = [
        "character_name",
        "modifier_type",
        "value",
        "source",
        "expires_at",
        "created_at",
    ]
    list_filter = [
        "modifier_type__category",
        "modifier_type",
        ("expires_at", admin.EmptyFieldListFilter),
    ]
    search_fields = ["character__character__db_key"]
    list_select_related = [
        "character",
        "character__character",
        "modifier_type",
        "modifier_type__category",
        "source",
    ]
    raw_id_fields = ["character", "source"]
    readonly_fields = ["created_at"]

    @admin.display(description="Character")
    def character_name(self, obj):
        return obj.character.character.db_key
