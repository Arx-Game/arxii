"""
Django admin interface for the distinctions system.

Provides administrative interfaces for managing distinction definitions,
effects, and character distinction grants.
"""

from django.contrib import admin

from world.codex.models import DistinctionCodexGrant
from world.contributors.admin import CREDIT_FIELDSET
from world.distinctions.models import (
    CharacterDistinction,
    CharacterDistinctionOther,
    Distinction,
    DistinctionCategory,
    DistinctionEffect,
    DistinctionTag,
    SheetUpdateRequest,
)
from world.distinctions.types import OtherStatus


@admin.register(DistinctionCategory)
class DistinctionCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "display_order", "distinction_count"]
    list_editable = ["display_order"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    ordering = ["display_order", "name"]

    @admin.display(description="Distinctions")
    def distinction_count(self, obj):
        return obj.distinctions.count()


@admin.register(DistinctionTag)
class DistinctionTagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


class DistinctionEffectInline(admin.TabularInline):
    model = DistinctionEffect
    extra = 1
    fields = [
        "target",
        "value_per_rank",
        "scaling_values",
        "description",
    ]
    autocomplete_fields = ["target"]


class DistinctionCodexGrantInline(admin.TabularInline):
    model = DistinctionCodexGrant
    extra = 1
    autocomplete_fields = ["entry"]


@admin.register(Distinction)
class DistinctionAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "category",
        "cost_per_rank",
        "max_rank",
        "has_variants",
        "is_active",
    ]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["category", "parent_distinction"]
    filter_horizontal = ["tags", "mutually_exclusive_with"]
    inlines = [DistinctionEffectInline, DistinctionCodexGrantInline]
    readonly_fields = ["get_resonance_grants"]

    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "category")}),
        (
            "Cost & Ranks",
            {"fields": ("cost_per_rank", "max_rank")},
        ),
        (
            "Variant Configuration",
            {
                "fields": ("parent_distinction", "allow_other"),
                "classes": ("collapse",),
            },
        ),
        ("Tags", {"fields": ("tags",)}),
        (
            "Mutual Exclusions",
            {
                "fields": ("mutually_exclusive_with",),
                "classes": ("collapse",),
            },
        ),
        (
            "Automatic Distinctions",
            {
                "fields": ("is_automatic", "requires_slot_filled"),
                "classes": ("collapse",),
            },
        ),
        ("Status", {"fields": ("is_active",)}),
        (
            "Resonance Wiring",
            {
                "fields": ("get_resonance_grants",),
                "description": (
                    "Authored in world.magic (ADR-0010: the general Resonance primitive "
                    "must not import back into distinctions), so this app can't see it "
                    "without an explicit summary."
                ),
                "classes": ("collapse",),
            },
        ),
        CREDIT_FIELDSET,
    )

    @admin.display(boolean=True, description="Has Variants")
    def has_variants(self, obj):
        return obj.is_variant_parent

    @admin.display(description="Resonance grants/thresholds")
    def get_resonance_grants(self, obj: Distinction) -> str:
        if not obj.pk:
            return "-"
        grants = ", ".join(
            f"{g.resonance.name} (+{g.flat_amount_per_rank}/rank)"
            for g in obj.resonance_grants.select_related("resonance")
        )
        thresholds = ", ".join(
            f"{t.resonance.name} @rank{t.rank}"
            for t in obj.resonance_rank_thresholds.select_related("resonance")
        )
        parts = []
        if grants:
            parts.append(f"Grants: {grants}")
        if thresholds:
            parts.append(f"Rank thresholds: {thresholds}")
        return "; ".join(parts) or "None"


@admin.register(DistinctionEffect)
class DistinctionEffectAdmin(admin.ModelAdmin):
    list_display = ["distinction", "target", "category", "value_per_rank"]
    list_filter = ["target__category"]
    search_fields = ["distinction__name", "target__name", "description"]
    autocomplete_fields = ["distinction", "target"]
    list_select_related = ["distinction", "target", "target__category"]

    @admin.display(description="Category")
    def category(self, obj):
        return obj.target.category.name


@admin.register(CharacterDistinction)
class CharacterDistinctionAdmin(admin.ModelAdmin):
    list_display = [
        "character",
        "distinction",
        "rank",
        "origin",
        "is_temporary",
        "created_at",
    ]
    list_filter = ["origin", "is_temporary", "distinction__category"]
    list_select_related = ["character", "distinction", "distinction__category"]
    search_fields = ["character__character__db_key", "distinction__name"]
    autocomplete_fields = ["character", "distinction"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(CharacterDistinctionOther)
class CharacterDistinctionOtherAdmin(admin.ModelAdmin):
    list_display = [
        "character",
        "parent_distinction",
        "freeform_text",
        "status",
        "created_at",
    ]
    list_filter = ["status", "parent_distinction"]
    search_fields = ["character__character__db_key", "freeform_text"]
    autocomplete_fields = ["character", "parent_distinction", "staff_mapped_distinction"]
    readonly_fields = ["created_at"]
    actions = ["mark_approved"]

    @admin.action(description="Mark selected entries as approved")
    def mark_approved(self, request, queryset):
        updated = queryset.update(status=OtherStatus.APPROVED)
        self.message_user(request, f"{updated} entries marked as approved.")


@admin.register(SheetUpdateRequest)
class SheetUpdateRequestAdmin(admin.ModelAdmin):
    list_display = ("character_sheet", "request_type", "status", "xp_cost", "created_at")
    list_filter = ("request_type", "status")
    readonly_fields = ("created_at", "reviewed_at")
    raw_id_fields = (
        "character_sheet",
        "target_distinction",
        "target_character_distinction",
        "reviewed_by",
        "submitted_by",
    )
