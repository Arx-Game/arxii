from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from world.character_sheets.models import (
    CharacterSheet,
    Gender,
    Profile,
    ProfileTextVersion,
    Pronouns,
)
from world.character_sheets.types import ProfileTextField


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Admin for the narrative bio Profile (#1270)."""

    # owning_sheet is a reverse OneToOneRel — can't use autocomplete_fields/raw_id_fields
    large_table_widget_exempt = ["owning_sheet"]

    list_display = ["__str__", "concept"]
    search_fields = ["concept", "real_concept"]
    raw_id_fields = ("heritage", "origin_realm", "family", "tarot_card")
    fields = (
        "concept",
        "real_concept",
        "quote",
        "personality",
        "background",
        "obituary",
        # Lineage moved to Profile (#1270 slice 3) — edit it here.
        "heritage",
        "origin_realm",
        "family",
        "tarot_card",
        "tarot_reversed",
    )

    def save_model(self, request: HttpRequest, obj: Profile, form: Any, change: bool) -> None:
        """Route versioned prose fields through the snapshot service (#2631).

        Staff edits must never overwrite background/personality silently — the
        same history invariant the table-request flow holds. The pre-edit text
        comes from ``form.initial``: the identity map means the instance (and
        any refetch) already holds the new value by the time we get here.
        """
        from world.character_sheets.services import update_profile_text  # noqa: PLC0415

        versioned_changed = [
            f for f in ProfileTextField.values if change and f in form.changed_data
        ]
        previous = {f: form.initial.get(f) or "" for f in versioned_changed}
        super().save_model(request, obj, form, change)
        for field in versioned_changed:
            update_profile_text(
                obj,
                field,
                getattr(obj, field),
                edited_by=request.user,
                previous_text=previous[field],
            )


@admin.register(ProfileTextVersion)
class ProfileTextVersionAdmin(admin.ModelAdmin):
    """Read-oriented admin for the profile prose history (#2631)."""

    list_display = ["__str__", "field", "created_at", "era", "edited_by"]
    list_filter = ["field"]
    raw_id_fields = ("profile", "era", "edited_by")
    readonly_fields = ("created_at",)


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
    autocomplete_fields = ["active_persona", "character", "created_by"]
    # roster_entry is a reverse OneToOneRel — can't use autocomplete_fields/raw_id_fields
    large_table_widget_exempt = ["roster_entry"]
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
    search_fields = ["character__db_key", "true_profile__concept", "true_profile__family__name"]
    readonly_fields = ["created_date", "updated_date", "decay_tier_display"]
    raw_id_fields = ["true_profile", "current_residence"]

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
                    "true_profile",
                    "vocation",
                    "social_rank",
                    "marital_status",
                ),
                "description": "Narrative bio (concept/quote/background/…) AND lineage "
                "(family/heritage/tarot/origin) live on the linked Profile (#1270) — "
                "edit them there.",
            },
        ),
        (
            "Descriptions",
            {
                "fields": ("additional_desc",),
                "classes": ["collapse"],
            },
        ),
        (
            "Housing (#2036)",
            {
                "fields": ("current_residence",),
                "description": "Declared residence — where the daily resonance trickle "
                "reads its room-aura tags from. Staff fix-up for a stuck or wrong "
                "declaration; players declare via `room/home` (set_primary_home).",
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
