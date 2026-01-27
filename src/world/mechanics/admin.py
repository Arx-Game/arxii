"""
Mechanics System Admin

Admin configuration for game mechanics models.
"""

from django.contrib import admin
from django.utils.html import format_html

from world.mechanics.models import CharacterModifier, ModifierCategory, ModifierType

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


@admin.register(CharacterModifier)
class CharacterModifierAdmin(admin.ModelAdmin):
    list_display = [
        "character",
        "modifier_type",
        "value",
        "source_summary",
        "expires_at",
        "created_at",
    ]
    list_filter = [
        "modifier_type__category",
        "modifier_type",
        ("expires_at", admin.EmptyFieldListFilter),
    ]
    search_fields = ["character__db_key"]
    list_select_related = ["character", "modifier_type", "modifier_type__category"]
    raw_id_fields = ["character", "source_distinction", "source_condition"]
    readonly_fields = ["created_at"]

    @admin.display(description="Source")
    def source_summary(self, obj):
        if obj.source_distinction_id:
            return format_html("Distinction: <strong>{}</strong>", obj.source_distinction_id)
        if obj.source_condition_id:
            return format_html("Condition: <strong>{}</strong>", obj.source_condition_id)
        return "Unknown"
