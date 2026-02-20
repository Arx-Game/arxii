from django.contrib import admin

from world.character_sheets.models import (
    Characteristic,
    CharacteristicValue,
    CharacterSheet,
    CharacterSheetValue,
    Gender,
    Guise,
    Pronouns,
)


@admin.register(Gender)
class GenderAdmin(admin.ModelAdmin):
    """Admin for Gender options."""

    list_display = ["key", "display_name", "is_default"]
    search_fields = ["key", "display_name"]
    ordering = ["display_name"]


@admin.register(Pronouns)
class PronounsAdmin(admin.ModelAdmin):
    """Admin for Pronoun sets."""

    list_display = ["key", "display_name", "subject", "object", "possessive", "is_default"]
    search_fields = ["key", "display_name"]
    ordering = ["display_name"]


@admin.register(CharacterSheet)
class CharacterSheetAdmin(admin.ModelAdmin):
    list_display = ["character", "age", "gender", "concept", "social_rank"]
    list_filter = ["gender", "marital_status"]
    search_fields = ["character__db_key", "concept", "family"]
    readonly_fields = ["created_date", "updated_date"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("character", "age", "real_age", "gender", "pronouns", "birthday")},
        ),
        (
            "Pronouns (Direct)",
            {
                "fields": ("pronoun_subject", "pronoun_object", "pronoun_possessive"),
                "description": "Individual pronoun fields (auto-derived from gender, editable)",
            },
        ),
        (
            "Identity & Social",
            {
                "fields": (
                    "concept",
                    "real_concept",
                    "family",
                    "tarot_card",
                    "tarot_reversed",
                    "vocation",
                    "social_rank",
                    "marital_status",
                ),
            },
        ),
        (
            "Descriptions",
            {
                "fields": (
                    "quote",
                    "personality",
                    "background",
                    "additional_desc",
                    "obituary",
                ),
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_date", "updated_date"), "classes": ["collapse"]},
        ),
    )


# CharacterDescription admin removed - display data now handled by:
# - evennia_extensions.ObjectDisplayData for basic display info
# - world.character_sheets.Guise for false names and contextual appearances


@admin.register(Guise)
class GuiseAdmin(admin.ModelAdmin):
    list_display = ["name", "character", "is_default", "created_date"]
    list_filter = ["is_default"]
    search_fields = ["character__db_key", "name"]
    readonly_fields = ["created_date", "updated_date"]


@admin.register(Characteristic)
class CharacteristicAdmin(admin.ModelAdmin):
    list_display = ["name", "display_name", "is_active", "values_count"]
    list_filter = ["is_active"]
    search_fields = ["name", "display_name"]

    def values_count(self, obj):
        return obj.values.count()

    values_count.short_description = "Number of Values"


class CharacteristicValueInline(admin.TabularInline):
    model = CharacteristicValue
    extra = 1


@admin.register(CharacteristicValue)
class CharacteristicValueAdmin(admin.ModelAdmin):
    list_display = ["characteristic", "value", "display_value", "is_active"]
    list_filter = ["characteristic", "is_active"]
    search_fields = ["value", "display_value"]


class CharacterSheetValueInline(admin.TabularInline):
    model = CharacterSheetValue
    extra = 1


# Add inlines to make editing easier
CharacteristicAdmin.inlines = [CharacteristicValueInline]
CharacterSheetAdmin.inlines = [CharacterSheetValueInline]
