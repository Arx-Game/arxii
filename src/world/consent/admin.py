"""Django admin configuration for the consent system."""

from django.contrib import admin

from world.consent.models import (
    ConsentGroup,
    ConsentGroupMember,
    SocialConsentCategory,
    SocialConsentCategoryRule,
    SocialConsentPreference,
    SocialConsentWhitelist,
)


class ConsentGroupMemberInline(admin.TabularInline):
    """Inline admin for group members."""

    model = ConsentGroupMember
    extra = 1
    raw_id_fields = ["tenure"]


@admin.register(ConsentGroup)
class ConsentGroupAdmin(admin.ModelAdmin):
    """Admin interface for ConsentGroup."""

    list_display = ["name", "owner", "member_count", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "owner__roster_entry__character__db_key"]
    raw_id_fields = ["owner"]
    inlines = [ConsentGroupMemberInline]

    def member_count(self, obj: ConsentGroup) -> int:
        return obj.members.count()

    member_count.short_description = "Members"


@admin.register(SocialConsentCategory)
class SocialConsentCategoryAdmin(admin.ModelAdmin):
    """Admin interface for SocialConsentCategory."""

    list_display = ["key", "name", "display_order"]
    list_editable = ["display_order"]
    search_fields = ["key", "name"]
    ordering = ["display_order", "name"]


class SocialConsentCategoryRuleInline(admin.TabularInline):
    """Inline admin for per-category consent rules on a preference."""

    model = SocialConsentCategoryRule
    extra = 0
    raw_id_fields = ["category"]


@admin.register(SocialConsentPreference)
class SocialConsentPreferenceAdmin(admin.ModelAdmin):
    """Admin interface for SocialConsentPreference."""

    list_display = ["tenure", "allow_social_actions"]
    list_filter = ["allow_social_actions"]
    search_fields = ["tenure__roster_entry__character__db_key"]
    raw_id_fields = ["tenure"]
    inlines = [SocialConsentCategoryRuleInline]


@admin.register(SocialConsentWhitelist)
class SocialConsentWhitelistAdmin(admin.ModelAdmin):
    """Admin interface for SocialConsentWhitelist."""

    list_display = ["owner_tenure", "allowed_tenure", "category", "added_at"]
    list_filter = ["category"]
    search_fields = [
        "owner_tenure__roster_entry__character__db_key",
        "allowed_tenure__roster_entry__character__db_key",
    ]
    raw_id_fields = ["owner_tenure", "allowed_tenure", "category"]
