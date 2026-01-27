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
    list_display = ["id", "get_source_type", "source_display"]
    list_filter = [
        ("distinction_effect", admin.EmptyFieldListFilter),
    ]
    raw_id_fields = ["distinction_effect", "character_distinction"]

    @admin.display(description="Type")
    def get_source_type(self, obj):
        # Use model property, capitalize for display
        return obj.source_type.capitalize()


@admin.register(CharacterModifier)
class CharacterModifierAdmin(admin.ModelAdmin):
    """Admin for CharacterModifier.

    Note: modifier_type is a property derived from source.distinction_effect.target,
    so we use custom methods for display and can't use standard field filters.
    """

    list_display = [
        "character_name",
        "get_modifier_type",
        "value",
        "source",
        "expires_at",
        "created_at",
    ]
    list_filter = [
        ("expires_at", admin.EmptyFieldListFilter),
    ]
    search_fields = ["character__character__db_key"]
    list_select_related = [
        "character",
        "character__character",
        "source",
        "source__distinction_effect",
        "source__distinction_effect__target",
        "source__distinction_effect__target__category",
    ]
    raw_id_fields = ["character", "source"]
    readonly_fields = ["created_at"]

    @admin.display(description="Character")
    def character_name(self, obj):
        return obj.character.character.db_key

    @admin.display(description="Modifier Type")
    def get_modifier_type(self, obj):
        mod_type = obj.modifier_type
        return mod_type.name if mod_type else "Unknown"
