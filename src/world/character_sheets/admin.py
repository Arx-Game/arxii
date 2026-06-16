from django.contrib import admin

from world.character_sheets.models import (
    CharacterSheet,
    Gender,
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
    list_display = [
        "character",
        "age",
        "gender",
        "concept",
        "social_rank",
        "activity_state",
        "lifecycle_state",
        "is_oc",
    ]
    list_filter = [
        "gender",
        "marital_status",
        "activity_state",
        "lifecycle_state",
        "is_oc",
    ]
    search_fields = ["character__db_key", "concept", "family"]
    readonly_fields = ["created_date", "updated_date", "decay_tier_display"]

    @admin.display(description="Decay tier (computed)")
    def decay_tier_display(self, obj: CharacterSheet) -> str:
        return obj.decay_tier or "ACTIVE"

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
            "Activity & Lifecycle (#671)",
            {
                "fields": (
                    "activity_state",
                    "activity_state_until",
                    "lifecycle_state",
                    "lifecycle_state_at",
                    "decay_tier_display",
                    "is_oc",
                    "created_by",
                ),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_date", "updated_date"), "classes": ["collapse"]},
        ),
    )


# CharacterDescription admin removed - display data now handled by:
# - evennia_extensions.ObjectDisplayData for basic display info
# - world.scenes.Persona for character identities and contextual appearances
