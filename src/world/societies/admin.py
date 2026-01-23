"""Django admin configuration for the societies system.

Provides administrative interfaces for managing realms, societies,
organizations, memberships, reputations, and legend entries.
"""

from django.contrib import admin

from world.societies.models import (
    LegendEntry,
    LegendSpread,
    Organization,
    OrganizationMembership,
    OrganizationReputation,
    OrganizationType,
    Realm,
    Society,
    SocietyReputation,
)

# =============================================================================
# Inline Classes
# =============================================================================


class SocietyInline(admin.TabularInline):
    """Inline for displaying societies within a realm."""

    model = Society
    extra = 0
    fields = ["name", "mercy", "method", "status", "change", "allegiance", "power"]
    show_change_link = True


class OrganizationInline(admin.TabularInline):
    """Inline for displaying organizations within a society."""

    model = Organization
    extra = 0
    fields = ["name", "org_type", "description"]
    show_change_link = True
    raw_id_fields = ["org_type"]


class OrganizationMembershipInline(admin.TabularInline):
    """Inline for displaying memberships within an organization."""

    model = OrganizationMembership
    extra = 0
    fields = ["guise", "rank", "joined_date"]
    readonly_fields = ["joined_date"]
    raw_id_fields = ["guise"]


class LegendSpreadInline(admin.TabularInline):
    """Inline for displaying spreads within a legend entry."""

    model = LegendSpread
    extra = 0
    fields = ["spreader_guise", "value_added", "method", "created_at"]
    readonly_fields = ["created_at"]
    raw_id_fields = ["spreader_guise"]


# =============================================================================
# Realm and Society Admins
# =============================================================================


@admin.register(Realm)
class RealmAdmin(admin.ModelAdmin):
    """Admin interface for Realm management."""

    list_display = ["name", "society_count"]
    search_fields = ["name", "description"]
    ordering = ["name"]
    inlines = [SocietyInline]

    def society_count(self, obj):
        """Return the number of societies in this realm."""
        return obj.societies.count()

    society_count.short_description = "Societies"


@admin.register(Society)
class SocietyAdmin(admin.ModelAdmin):
    """Admin interface for Society management.

    Displays all six principle fields and allows management of organizations.
    """

    list_display = [
        "name",
        "realm",
        "mercy",
        "method",
        "status",
        "change",
        "allegiance",
        "power",
        "organization_count",
    ]
    list_filter = ["realm"]
    search_fields = ["name", "description", "realm__name"]
    ordering = ["realm", "name"]
    inlines = [OrganizationInline]

    fieldsets = (
        (None, {"fields": ("name", "realm", "description")}),
        (
            "Principles",
            {
                "fields": (
                    ("mercy", "method"),
                    ("status", "change"),
                    ("allegiance", "power"),
                ),
                "description": (
                    "Values range from -5 to +5. Negative values represent one end of "
                    "the spectrum (e.g., Ruthlessness, Cunning), positive values the "
                    "other (e.g., Compassion, Honor)."
                ),
            },
        ),
    )

    def organization_count(self, obj):
        """Return the number of organizations in this society."""
        return obj.organizations.count()

    organization_count.short_description = "Organizations"


# =============================================================================
# Organization Admins
# =============================================================================


@admin.register(OrganizationType)
class OrganizationTypeAdmin(admin.ModelAdmin):
    """Admin interface for OrganizationType management.

    Manages the default rank titles for different organization categories.
    """

    list_display = [
        "name",
        "rank_1_title",
        "rank_2_title",
        "rank_3_title",
        "rank_4_title",
        "rank_5_title",
    ]
    search_fields = ["name"]
    ordering = ["name"]

    fieldsets = (
        (None, {"fields": ("name",)}),
        (
            "Default Rank Titles",
            {
                "fields": (
                    "rank_1_title",
                    "rank_2_title",
                    "rank_3_title",
                    "rank_4_title",
                    "rank_5_title",
                ),
                "description": "Rank 1 is the highest (leader), Rank 5 is the lowest.",
            },
        ),
    )


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Admin interface for Organization management.

    Shows organization details, principle overrides, and membership management.
    """

    list_display = [
        "name",
        "society",
        "org_type",
        "member_count",
    ]
    list_filter = ["society__realm", "society", "org_type"]
    search_fields = ["name", "description", "society__name"]
    ordering = ["society", "name"]
    inlines = [OrganizationMembershipInline]

    fieldsets = (
        (None, {"fields": ("name", "society", "org_type", "description")}),
        (
            "Principle Overrides",
            {
                "fields": (
                    ("mercy_override", "method_override"),
                    ("status_override", "change_override"),
                    ("allegiance_override", "power_override"),
                ),
                "description": (
                    "Leave blank to inherit from the society. Values range from -5 to +5."
                ),
                "classes": ["collapse"],
            },
        ),
        (
            "Rank Title Overrides",
            {
                "fields": (
                    "rank_1_title_override",
                    "rank_2_title_override",
                    "rank_3_title_override",
                    "rank_4_title_override",
                    "rank_5_title_override",
                ),
                "description": "Leave blank to use the organization type's defaults.",
                "classes": ["collapse"],
            },
        ),
    )

    def member_count(self, obj):
        """Return the number of members in this organization."""
        return obj.memberships.count()

    member_count.short_description = "Members"


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    """Admin interface for OrganizationMembership management."""

    list_display = ["guise", "organization", "rank", "get_title", "joined_date"]
    list_filter = ["organization__society", "organization", "rank"]
    search_fields = ["guise__name", "organization__name"]
    ordering = ["organization", "rank", "guise__name"]
    readonly_fields = ["joined_date", "get_title"]
    raw_id_fields = ["guise"]

    def get_title(self, obj):
        """Return the effective title for this membership."""
        return obj.get_title()

    get_title.short_description = "Title"


# =============================================================================
# Reputation Admins
# =============================================================================


@admin.register(SocietyReputation)
class SocietyReputationAdmin(admin.ModelAdmin):
    """Admin interface for SocietyReputation management.

    Useful for debugging and administrative adjustments to reputation.
    """

    list_display = ["guise", "society", "value", "get_tier_display"]
    list_filter = ["society__realm", "society"]
    search_fields = ["guise__name", "society__name"]
    ordering = ["society", "-value"]
    raw_id_fields = ["guise"]

    def get_tier_display(self, obj):
        """Return the reputation tier display name."""
        return obj.get_tier().display_name

    get_tier_display.short_description = "Tier"


@admin.register(OrganizationReputation)
class OrganizationReputationAdmin(admin.ModelAdmin):
    """Admin interface for OrganizationReputation management.

    Useful for debugging and administrative adjustments to reputation.
    """

    list_display = ["guise", "organization", "value", "get_tier_display"]
    list_filter = ["organization__society__realm", "organization__society", "organization"]
    search_fields = ["guise__name", "organization__name"]
    ordering = ["organization", "-value"]
    raw_id_fields = ["guise"]

    def get_tier_display(self, obj):
        """Return the reputation tier display name."""
        return obj.get_tier().display_name

    get_tier_display.short_description = "Tier"


# =============================================================================
# Legend Admins
# =============================================================================


@admin.register(LegendEntry)
class LegendEntryAdmin(admin.ModelAdmin):
    """Admin interface for LegendEntry management.

    Manages legendary deeds and their spread instances.
    """

    list_display = [
        "title",
        "guise",
        "base_value",
        "get_total_value",
        "spread_count",
        "created_at",
    ]
    list_filter = ["societies_aware", "guise__character"]
    search_fields = ["title", "description", "guise__name"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at", "get_total_value"]
    raw_id_fields = ["guise"]
    filter_horizontal = ["societies_aware"]
    inlines = [LegendSpreadInline]

    fieldsets = (
        (
            None,
            {"fields": ("guise", "title", "base_value", "get_total_value")},
        ),
        (
            "Description",
            {"fields": ("description", "source_note", "location_note")},
        ),
        (
            "Awareness",
            {
                "fields": ("societies_aware",),
                "description": "Which societies know about this deed.",
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ["collapse"]},
        ),
    )

    def get_total_value(self, obj):
        """Return the total legend value including spreads."""
        return obj.get_total_value()

    get_total_value.short_description = "Total Value"

    def spread_count(self, obj):
        """Return the number of times this legend has been spread."""
        return obj.spreads.count()

    spread_count.short_description = "Spreads"


@admin.register(LegendSpread)
class LegendSpreadAdmin(admin.ModelAdmin):
    """Admin interface for LegendSpread management."""

    list_display = [
        "legend_entry",
        "spreader_guise",
        "value_added",
        "method",
        "created_at",
    ]
    list_filter = ["societies_reached", "legend_entry__guise__character"]
    search_fields = [
        "legend_entry__title",
        "spreader_guise__name",
        "description",
        "method",
    ]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]
    raw_id_fields = ["legend_entry", "spreader_guise"]
    filter_horizontal = ["societies_reached"]

    fieldsets = (
        (
            None,
            {"fields": ("legend_entry", "spreader_guise", "value_added")},
        ),
        (
            "Details",
            {"fields": ("description", "method")},
        ),
        (
            "Reach",
            {
                "fields": ("societies_reached",),
                "description": "Which societies heard this version of the tale.",
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at",), "classes": ["collapse"]},
        ),
    )
