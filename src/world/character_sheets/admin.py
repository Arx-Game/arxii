from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin, messages
from django.http import HttpRequest

from world.character_sheets.models import (
    CharacterEnemy,
    CharacterSheet,
    Gender,
    Heritage,
    MoodOption,
    Profile,
    ProfileBeginnings,
    ProfileTextVersion,
    Pronouns,
)
from world.character_sheets.types import ProfileTextField

if TYPE_CHECKING:
    from world.roster.models import RosterEntry


class ProfileBeginningsInline(admin.TabularInline):
    """Every origin this character holds, and why (#3775)."""

    model = ProfileBeginnings
    extra = 0
    fields = ["beginnings", "source", "note", "gained_at"]
    readonly_fields = ["gained_at"]
    autocomplete_fields = ["beginnings"]
    verbose_name_plural = (
        "Beginnings: every origin this character holds. The wizard adds where play "
        "began; add a recovered memory or past life here and its entries are granted "
        "on save."
    )


def _roster_entry_of_profile(profile: Profile) -> RosterEntry | None:
    """The roster entry playing this profile's owning sheet, if any (#3775).

    A ``Profile`` that is not a sheet's ``true_profile`` (a cover persona's
    fabricated bio) has no owning sheet at all, and even a true profile's sheet
    may not be attached to a roster entry yet - both are expected absences, not
    bugs, so this reads the two reverse one-to-ones through their ``_or_none``
    descriptors rather than the raw (exception-raising) accessors.
    """
    sheet = profile.owning_sheet_or_none
    if sheet is None:
        return None
    return sheet.roster_entry_or_none


def apply_new_origin_rows(request: HttpRequest, formsets) -> int:
    """Grant each newly added origin's codex entries to this one character (#3775).

    Unlike ``GrantReachOnSaveMixin`` (which reaches every character holding a
    Beginnings when a *grant* row is added), this reaches only the one
    character whose Profile just gained a *new origin* row - the documented
    behaviour is that a recovered memory or past life teaches that character
    what the origin already grants, not that it retroactively reaches anyone
    else who happens to share the Beginnings.
    """
    from world.codex.services import grant_codex_entry  # noqa: PLC0415

    learned = 0
    for formset in formsets:
        # save_new_objects (called above, inside super().save_related()) always
        # sets this on a BaseModelFormSet before returning - same guarantee
        # GrantReachOnSaveMixin relies on (world/codex/admin.py).
        for row in formset.new_objects:
            if not isinstance(row, ProfileBeginnings):
                continue
            roster_entry = _roster_entry_of_profile(row.profile)
            if roster_entry is None:
                continue
            for grant in row.beginnings.codex_grants.all():
                _, created = grant_codex_entry(roster_entry, grant.entry)
                learned += int(created)
    if learned:
        messages.info(request, f"New origin(s) taught this character {learned} entries.")
    return learned


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Admin for the narrative bio Profile (#1270)."""

    # owning_sheet is a reverse OneToOneRel — can't use autocomplete_fields/raw_id_fields
    large_table_widget_exempt = ["owning_sheet"]

    list_display = ["__str__", "concept"]
    search_fields = ["concept", "real_concept"]
    raw_id_fields = ("heritage", "origin_realm", "family", "tarot_card")
    inlines = [ProfileBeginningsInline]
    fields = (
        "concept",
        "real_concept",
        "quote",
        "never_do",
        "protect",
        "fear",
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

        Staff edits must never overwrite versioned prose silently — the
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

    def save_related(self, request: HttpRequest, form: Any, formsets, change: bool) -> None:
        """After the inlines save, grant any newly added origin's entries (#3775)."""
        super().save_related(request, form, formsets, change)
        apply_new_origin_rows(request, formsets)


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


@admin.register(MoodOption)
class MoodOptionAdmin(admin.ModelAdmin):
    """Admin for Mood options (#2994) — the curated ``feel <state>`` vocabulary."""

    list_display = ["name", "sort_order", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "description"]
    ordering = ["sort_order", "name"]


@admin.register(CharacterSheet)
class CharacterSheetAdmin(admin.ModelAdmin):
    autocomplete_fields = ["active_persona", "character", "created_by", "current_residence"]
    # roster_entry is a reverse OneToOneRel — can't use autocomplete_fields/raw_id_fields
    large_table_widget_exempt = ["roster_entry"]
    list_display = [
        "character",
        "matured_years",
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
    raw_id_fields = ["true_profile"]

    @admin.display(description="Decay tier (computed)")
    def decay_tier_display(self, obj: CharacterSheet) -> str:
        return obj.decay_tier or "ACTIVE"

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("character", "gender", "pronouns")},
        ),
        (
            "Age Axes (#2756)",
            {
                "fields": (
                    "matured_years",
                    "withered_years",
                    "aging_paused",
                    "ic_birth_year",
                    "birthday_month",
                    "birthday_day",
                ),
                "description": (
                    "Biological age = matured + withered; chronological derives from "
                    "ic_birth_year vs the game clock (null = Unknown); apparent age is "
                    "biological — cosmetic overrides live in the appearance layer."
                ),
            },
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


@admin.register(Heritage)
class HeritageAdmin(admin.ModelAdmin):
    """Heritage rows, including the IC date the first of each were born (#3663).

    ``first_appeared_ic`` is the anchor for the CG age ceiling; on production
    it is set here once (the seed only fills it on an empty database).
    """

    list_display = ["name", "is_special", "family_known", "first_appeared_ic"]
    search_fields = ["name"]
    fields = (
        "name",
        "description",
        "is_special",
        "family_known",
        "family_display",
        "chronological_age_unknown",
        "first_appeared_ic",
    )


@admin.register(CharacterEnemy)
class CharacterEnemyAdmin(admin.ModelAdmin):
    """Who wants a character to fail, priced (#3621).

    Staff place a free-written enemy here: linking a real group (or rating a person)
    recomputes the price on save and flips the row to placed.
    """

    list_display = ["character", "kind", "target_name", "degree", "price", "status"]
    list_filter = ["kind", "degree", "status"]
    search_fields = ["figure_name", "organization__name", "family__name"]
    raw_id_fields = ["character", "organization", "family", "secret"]
    readonly_fields = ["price", "reach", "created_at"]

    def save_model(
        self, request: HttpRequest, obj: CharacterEnemy, form: Any, change: bool
    ) -> None:
        from world.character_creation.enemies import enemy_price  # noqa: PLC0415
        from world.character_sheets.types import EnemyKind, EnemyStatus  # noqa: PLC0415

        if obj.kind == EnemyKind.GROUP and obj.organization_id is not None:
            obj.reach = obj.organization.org_type.reach
            scale = obj.reach
        elif obj.kind == EnemyKind.PERSON:
            scale = obj.power_tier
        else:
            scale = ""
        obj.price = enemy_price(obj.kind, scale, obj.degree)
        obj.status = EnemyStatus.PLACED if scale else EnemyStatus.PENDING
        super().save_model(request, obj, form, change)
