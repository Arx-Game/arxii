from django.contrib import admin

from world.character_sheets.models import (
    Characteristic,
    CharacteristicValue,
    CharacterSheet,
    CharacterSheetValue,
    Guise,
)


@admin.register(CharacterSheet)
class CharacterSheetAdmin(admin.ModelAdmin):
    list_display = ["character", "age", "gender", "concept", "social_rank"]
    list_filter = ["gender", "marital_status"]
    search_fields = ["character__db_key", "concept", "family"]
    readonly_fields = ["created_date", "updated_date"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("character", "age", "real_age", "gender", "birthday")},
        ),
        (
            "Identity & Social",
            {
                "fields": (
                    "concept",
                    "real_concept",
                    "family",
                    "vocation",
                    "social_rank",
                    "marital_status",
                )
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


@admin.register(CharacterSheetValue)
class CharacterSheetValueAdmin(admin.ModelAdmin):
    list_display = ["character_sheet", "characteristic_value", "created_date"]
    list_filter = ["characteristic_value__characteristic"]
    search_fields = [
        "character_sheet__character__db_key",
        "characteristic_value__value",
    ]
    readonly_fields = ["created_date", "updated_date"]


# Add inlines to make editing easier
CharacteristicAdmin.inlines = [CharacteristicValueInline]
CharacterSheetAdmin.inlines = [CharacterSheetValueInline]
