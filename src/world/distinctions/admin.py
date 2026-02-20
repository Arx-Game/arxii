"""
Django admin interface for the distinctions system.

Provides administrative interfaces for managing distinction definitions,
effects, prerequisites, and character distinction grants.
"""

from django.contrib import admin

from world.codex.models import DistinctionCodexGrant
from world.distinctions.models import (
    CharacterDistinction,
    CharacterDistinctionOther,
    Distinction,
    DistinctionCategory,
    DistinctionEffect,
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
        "target",
        "value_per_rank",
        "scaling_values",
        "description",
    ]
    autocomplete_fields = ["target"]


class DistinctionPrerequisiteInline(admin.TabularInline):
    model = DistinctionPrerequisite
    extra = 0
    fields = ["rule_json", "description"]


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
        "has_trust_requirement",
        "is_active",
    ]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ["category", "parent_distinction", "trust_category"]
    filter_horizontal = ["tags", "mutually_exclusive_with"]
    inlines = [DistinctionEffectInline, DistinctionPrerequisiteInline, DistinctionCodexGrantInline]

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
            "Trust Gating",
            {
                "fields": ("trust_value", "trust_category"),
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

    @admin.display(boolean=True, description="Has Variants")
    def has_variants(self, obj):
        return obj.is_variant_parent

    @admin.display(boolean=True, description="Trust Required")
    def has_trust_requirement(self, obj):
        return obj.trust_required


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
