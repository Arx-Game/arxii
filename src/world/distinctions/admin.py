"""
Django admin interface for the distinctions system.

Provides administrative interfaces for managing distinction definitions,
effects, prerequisites, mutual exclusions, and character distinction grants.
"""

from django.contrib import admin

from world.distinctions.models import (
    CharacterDistinction,
    CharacterDistinctionOther,
    Distinction,
    DistinctionCategory,
    DistinctionEffect,
    DistinctionMutualExclusion,
    DistinctionPrerequisite,
    DistinctionTag,
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
        "effect_type",
        "target",
        "value_per_rank",
        "scaling_values",
        "slug_reference",
        "description",
    ]


class DistinctionPrerequisiteInline(admin.TabularInline):
    model = DistinctionPrerequisite
    extra = 0
    fields = ["rule_json", "description"]


@admin.register(Distinction)
class DistinctionAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "slug",
        "category",
        "cost_per_rank",
        "max_rank",
        "is_variant_parent",
        "trust_required",
        "is_active",
    ]
    list_filter = ["category", "is_variant_parent", "trust_required", "is_active"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["category", "parent_distinction", "trust_category"]
    filter_horizontal = ["tags"]
    inlines = [DistinctionEffectInline, DistinctionPrerequisiteInline]

    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "category")}),
        (
            "Cost & Ranks",
            {"fields": ("cost_per_rank", "max_rank")},
        ),
        (
            "Variant Configuration",
            {
                "fields": ("parent_distinction", "is_variant_parent", "allow_other"),
                "classes": ("collapse",),
            },
        ),
        ("Tags", {"fields": ("tags",)}),
        (
            "Trust Gating",
            {
                "fields": ("trust_required", "trust_value", "trust_category"),
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
    )


@admin.register(DistinctionEffect)
class DistinctionEffectAdmin(admin.ModelAdmin):
    list_display = ["distinction", "effect_type", "target", "value_per_rank"]
    list_filter = ["effect_type"]
    search_fields = ["distinction__name", "target", "description"]
    autocomplete_fields = ["distinction"]


@admin.register(DistinctionPrerequisite)
class DistinctionPrerequisiteAdmin(admin.ModelAdmin):
    list_display = ["distinction", "description"]
    search_fields = ["distinction__name", "description"]
    autocomplete_fields = ["distinction"]


@admin.register(DistinctionMutualExclusion)
class DistinctionMutualExclusionAdmin(admin.ModelAdmin):
    list_display = ["distinction_a", "distinction_b"]
    search_fields = ["distinction_a__name", "distinction_b__name"]
    autocomplete_fields = ["distinction_a", "distinction_b"]


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
    search_fields = ["character__db_key", "distinction__name"]
    autocomplete_fields = ["distinction"]
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
    search_fields = ["character__db_key", "freeform_text"]
    autocomplete_fields = ["parent_distinction", "staff_mapped_distinction"]
    readonly_fields = ["created_at"]
    actions = ["mark_approved"]

    @admin.action(description="Mark selected entries as approved")
    def mark_approved(self, request, queryset):
        updated = queryset.update(status=OtherStatus.APPROVED)
        self.message_user(request, f"{updated} entries marked as approved.")
