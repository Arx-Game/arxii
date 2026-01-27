"""Admin configuration for relationships models."""

from django.contrib import admin

from world.relationships.models import CharacterRelationship, RelationshipCondition

DESCRIPTION_TRUNCATE_LENGTH = 50


@admin.register(RelationshipCondition)
class RelationshipConditionAdmin(admin.ModelAdmin):
    list_display = ["name", "description_truncated", "display_order", "modifier_count"]
    search_fields = ["name", "description"]
    ordering = ["display_order", "name"]
    list_editable = ["display_order"]
    filter_horizontal = ["gates_modifiers"]

    @admin.display(description="Description")
    def description_truncated(self, obj):
        if obj.description and len(obj.description) > DESCRIPTION_TRUNCATE_LENGTH:
            return obj.description[:DESCRIPTION_TRUNCATE_LENGTH] + "..."
        return obj.description or ""

    @admin.display(description="Modifiers")
    def modifier_count(self, obj):
        return obj.gates_modifiers.count()


@admin.register(CharacterRelationship)
class CharacterRelationshipAdmin(admin.ModelAdmin):
    list_display = [
        "source_name",
        "target_name",
        "reputation",
        "condition_count",
        "created_at",
        "updated_at",
    ]
    list_filter = ["conditions"]
    search_fields = ["source__character__db_key", "target__character__db_key"]
    list_select_related = ["source", "source__character", "target", "target__character"]
    raw_id_fields = ["source", "target"]
    filter_horizontal = ["conditions"]
    readonly_fields = ["created_at", "updated_at"]

    @admin.display(description="Source")
    def source_name(self, obj):
        return obj.source.character.db_key

    @admin.display(description="Target")
    def target_name(self, obj):
        return obj.target.character.db_key

    @admin.display(description="Conditions")
    def condition_count(self, obj):
        return obj.conditions.count()
