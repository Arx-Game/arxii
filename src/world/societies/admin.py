"""Django admin configuration for the societies system.

Provides administrative interfaces for managing societies,
organizations, memberships, reputations, and legend entries.

Note: Realm admin is in the `realms` app.
"""

from django.contrib import admin

from world.societies.models import (
    CovenantLegendCredit,
    GangTurfDetails,
    GangTurfReputationAward,
    GangTurfTierThreshold,
    LegendDeedStory,
    LegendEntry,
    LegendEvent,
    LegendSourceType,
    LegendSpread,
    Organization,
    OrganizationGiftGrant,
    OrganizationMembership,
    OrganizationMembershipOffer,
    OrganizationObligation,
    OrganizationRank,
    OrganizationReputation,
    OrganizationType,
    RankingBandLabel,
    Society,
    SocietyReputation,
    SpreadingConfig,
)

# =============================================================================
# Inline Classes
# =============================================================================


class OrganizationInline(admin.TabularInline):
    """Inline for displaying organizations within a society."""

    model = Organization
    extra = 0
    fields = ["name", "org_type", "description"]
    show_change_link = True


class OrganizationRankInline(admin.TabularInline):
    """Inline for editing the organization's rank ladder."""

    model = OrganizationRank
    extra = 0
    fields = ["name", "tier", "can_invite", "can_kick", "can_manage_ranks"]


class OrganizationMembershipInline(admin.TabularInline):
    """Inline for displaying memberships within an organization."""

    model = OrganizationMembership
    extra = 0
    fields = ["persona", "rank", "joined_date", "left_at", "exiled_at"]
    readonly_fields = ["joined_date", "left_at", "exiled_at"]
    raw_id_fields = ["persona"]


class OrganizationGiftGrantInline(admin.TabularInline):
    """Inline for displaying gift grants within an organization."""

    model = OrganizationGiftGrant
    extra = 0
    fields = ["gift", "anchor_cap", "project"]
    readonly_fields = ["project"]
    raw_id_fields = ["gift", "project"]


class LegendSpreadInline(admin.TabularInline):
    """Inline for displaying spreads within a legend entry."""

    model = LegendSpread
    extra = 0
    fields = [
        "spreader_persona",
        "value_added",
        "method",
        "skill",
        "audience_factor",
        "created_at",
    ]
    readonly_fields = ["created_at"]
    raw_id_fields = ["spreader_persona", "skill"]


class LegendDeedStoryInline(admin.TabularInline):
    """Inline for displaying player narratives within a legend entry."""

    model = LegendDeedStory
    extra = 0
    fields = ["author", "text", "created_at", "updated_at"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["author"]


# =============================================================================
# Society Admin
# =============================================================================


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
        "current_fashion_style",
        "organization_count",
    ]
    list_filter = ["realm"]
    search_fields = ["name", "description", "realm__name"]
    ordering = ["realm", "name"]
    autocomplete_fields = ["current_fashion_style"]
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
        (
            "Fashion",
            {
                "fields": ("current_fashion_style",),
                "description": "The active FashionStyle driving outfit bonuses for this society.",
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
        "tradition",
        "org_type",
        "member_count",
    ]
    list_filter = ["society__realm", "society", "org_type"]
    search_fields = ["name", "description", "society__name"]
    ordering = ["society", "name"]
    raw_id_fields = ["tradition"]
    inlines = [OrganizationRankInline, OrganizationMembershipInline, OrganizationGiftGrantInline]

    fieldsets = (
        (None, {"fields": ("name", "society", "org_type", "tradition", "description")}),
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

    list_display = [
        "persona",
        "organization",
        "rank",
        "get_title",
        "joined_date",
        "left_at",
        "exiled_at",
    ]
    list_filter = ["organization__society", "organization", "rank"]
    search_fields = ["persona__name", "organization__name"]
    ordering = ["organization", "rank__tier", "persona__name"]
    readonly_fields = ["joined_date", "get_title", "left_at", "exiled_at"]
    raw_id_fields = ["persona"]

    def get_title(self, obj):
        """Return the effective title for this membership."""
        return obj.get_title()

    get_title.short_description = "Title"


@admin.register(OrganizationObligation)
class OrganizationObligationAdmin(admin.ModelAdmin):
    """Admin interface for OrganizationObligation management (#2428 Golden Hares).

    ``state``/``settled_at``/``settled_by_token`` are read-only here:
    ``world.societies.obligation_services.settle_obligation`` is the only writer —
    it redeems a real Golden Hare (``currency.redeem_favor_token``) as part of the
    same transaction that flips these fields, so hand-editing them in admin would
    mark a debt settled with no Hare ever changing hands. In play this row is
    settled at the Academy Registrar's SETTLE_OBLIGATION offer
    (``world.npc_services.effects.run_settle_obligation_offer``); from staff
    tooling, mint the debtor a Hare (GM Award action, ``award_type="favor_token"``)
    and have them settle it through that same flow, or call ``settle_obligation``
    directly.
    """

    list_display = [
        "debtor",
        "creditor",
        "origin",
        "state",
        "created_at",
        "settled_at",
    ]
    list_filter = ["origin", "state", "creditor"]
    search_fields = ["debtor__character__db_key", "creditor__name"]
    readonly_fields = ["created_at", "state", "settled_at", "settled_by_token"]
    raw_id_fields = ["debtor"]


@admin.register(OrganizationRank)
class OrganizationRankAdmin(admin.ModelAdmin):
    """Admin interface for OrganizationRank management."""

    list_display = [
        "organization",
        "name",
        "tier",
        "can_invite",
        "can_kick",
        "can_manage_ranks",
        "can_lead_rituals",
    ]
    list_filter = ["organization", "can_invite", "can_kick", "can_manage_ranks", "can_lead_rituals"]
    ordering = ["organization", "tier"]


@admin.register(OrganizationMembershipOffer)
class OrganizationMembershipOfferAdmin(admin.ModelAdmin):
    """Admin interface for OrganizationMembershipOffer management."""

    list_display = ["organization", "kind", "status", "from_persona", "to_persona", "created_at"]
    list_filter = ["kind", "status", "organization"]
    readonly_fields = ["created_at", "resolved_at"]
    raw_id_fields = ["organization", "from_persona", "to_persona"]


# =============================================================================
# Reputation Admins
# =============================================================================


@admin.register(SocietyReputation)
class SocietyReputationAdmin(admin.ModelAdmin):
    """Admin interface for SocietyReputation management.

    Useful for debugging and administrative adjustments to reputation.
    """

    list_display = ["persona", "society", "value", "get_tier_display"]
    list_filter = ["society__realm", "society"]
    search_fields = ["persona__name", "society__name"]
    ordering = ["society", "-value"]
    raw_id_fields = ["persona"]

    def get_tier_display(self, obj):
        """Return the reputation tier display name."""
        return obj.get_tier().display_name

    get_tier_display.short_description = "Tier"


@admin.register(OrganizationReputation)
class OrganizationReputationAdmin(admin.ModelAdmin):
    """Admin interface for OrganizationReputation management.

    Useful for debugging and administrative adjustments to reputation.
    """

    list_display = ["persona", "organization", "value", "get_tier_display"]
    list_filter = ["organization__society__realm", "organization__society", "organization"]
    search_fields = ["persona__name", "organization__name"]
    ordering = ["organization", "-value"]
    raw_id_fields = ["persona"]

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

    autocomplete_fields = ["linked_items"]

    list_display = [
        "title",
        "persona",
        "base_value",
        "get_total_value",
        "source_type",
        "is_active",
        "spread_count",
        "created_at",
    ]
    list_filter = [
        "is_active",
        "source_type",
        "societies_aware",
        "persona__character_sheet__character",
    ]
    search_fields = ["title", "description", "persona__name"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at", "get_total_value"]
    raw_id_fields = ["persona", "event", "scene", "story"]
    filter_horizontal = ["societies_aware"]
    inlines = [LegendSpreadInline, LegendDeedStoryInline]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "persona",
                    "title",
                    "base_value",
                    "get_total_value",
                    "source_type",
                    "is_active",
                    "spread_multiplier",
                ),
            },
        ),
        (
            "Links",
            {
                "fields": ("event", "scene", "story"),
                "classes": ["collapse"],
            },
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

    def get_total_value(self, obj: LegendEntry) -> int:
        """Return the total legend value including spreads."""
        return obj.get_total_value()

    get_total_value.short_description = "Total Value"

    def spread_count(self, obj: LegendEntry) -> int:
        """Return the number of times this legend has been spread."""
        return obj.spreads.count()

    spread_count.short_description = "Spreads"


@admin.register(LegendSpread)
class LegendSpreadAdmin(admin.ModelAdmin):
    """Admin interface for LegendSpread management."""

    list_display = [
        "legend_entry",
        "spreader_persona",
        "value_added",
        "method",
        "created_at",
    ]
    list_filter = ["societies_reached", "legend_entry__persona__character_sheet__character"]
    search_fields = [
        "legend_entry__title",
        "spreader_persona__name",
        "description",
        "method",
    ]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]
    raw_id_fields = ["legend_entry", "spreader_persona", "skill", "scene"]
    filter_horizontal = ["societies_reached"]

    fieldsets = (
        (
            None,
            {"fields": ("legend_entry", "spreader_persona", "value_added")},
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


@admin.register(LegendSourceType)
class LegendSourceTypeAdmin(admin.ModelAdmin):
    """Admin interface for legend source type management."""

    list_display = ["name", "display_order", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    ordering = ["display_order", "name"]


@admin.register(LegendEvent)
class LegendEventAdmin(admin.ModelAdmin):
    """Admin interface for legend event management."""

    list_display = ["title", "source_type", "base_value", "deed_count", "created_at"]
    list_filter = ["source_type"]
    search_fields = ["title", "description"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]
    raw_id_fields = ["scene", "story", "created_by"]

    def deed_count(self, obj: LegendEvent) -> int:
        """Return the number of deeds linked to this event."""
        return obj.deeds.count()

    deed_count.short_description = "Deeds"


@admin.register(SpreadingConfig)
class SpreadingConfigAdmin(admin.ModelAdmin):
    """Admin interface for spreading configuration (single-row)."""

    list_display = ["default_spread_multiplier", "base_audience_factor"]

    def has_add_permission(self, request: object) -> bool:  # noqa: ARG002
        """Prevent adding if config already exists."""
        return not SpreadingConfig.objects.exists()

    def has_delete_permission(
        self,
        request: object,  # noqa: ARG002
        obj: object = None,  # noqa: ARG002
    ) -> bool:
        """Prevent deleting the config."""
        return False


@admin.register(CovenantLegendCredit)
class CovenantLegendCreditAdmin(admin.ModelAdmin):
    """Admin interface for CovenantLegendCredit management."""

    list_display = ("entry", "covenant", "created_at")
    list_select_related = ("entry", "covenant")


@admin.register(RankingBandLabel)
class RankingBandLabelAdmin(admin.ModelAdmin):
    """#761 — qualitative band labels (per-society; null = global default set)."""

    list_display = ("__str__", "society", "rank_min", "rank_max", "is_active")
    list_filter = ("is_active", "society")
    search_fields = ("label",)


@admin.register(GangTurfDetails)
class GangTurfDetailsAdmin(admin.ModelAdmin):
    """#1891 — per-(GANG_TURF Project) payload."""

    list_display = ("project", "organization", "target_area")
    list_select_related = ("organization", "target_area")
    search_fields = ("organization__name",)


@admin.register(GangTurfTierThreshold)
class GangTurfTierThresholdAdmin(admin.ModelAdmin):
    """#1891 — progress band → CheckOutcome tier mapping per project."""

    list_display = ("details", "outcome_tier", "min_progress")
    list_select_related = ("details", "outcome_tier")
    ordering = ("details", "-min_progress")


@admin.register(GangTurfReputationAward)
class GangTurfReputationAwardAdmin(admin.ModelAdmin):
    """#1891 — global tier → reputation delta table (staff-tunable)."""

    list_display = ("outcome_tier", "reputation_delta")
    list_select_related = ("outcome_tier",)
    ordering = ("outcome_tier__success_level",)


# ---------------------------------------------------------------------------
# Houses (#1884 Phase D) — the staff review queue for CG house claims
# ---------------------------------------------------------------------------

from world.societies.houses.models import (  # noqa: E402
    HouseAspectDefinition,
    HouseAspectOption,
    HouseClaim,
    HouseClaimAspect,
    HouseFeature,
    HouseTemplate,
)


@admin.register(HouseTemplate)
class HouseTemplateAdmin(admin.ModelAdmin):
    """#1884 Phase D — realm recipes for CG-defined houses."""

    list_display = ("name", "realm", "family_type", "liege", "starting_kin_slots")
    list_select_related = ("realm", "liege")
    list_filter = ("realm", "family_type")
    search_fields = ("name",)
    filter_horizontal = ("holdings", "aspect_definitions", "features")


class HouseAspectOptionInline(admin.TabularInline):
    """#2079 — the catalog rows behind a definition."""

    model = HouseAspectOption
    extra = 0


@admin.register(HouseAspectDefinition)
class HouseAspectDefinitionAdmin(admin.ModelAdmin):
    """#2079 — authored, catalog-only required choices (ADR-0101)."""

    list_display = ("name", "min_picks", "max_picks", "display_order")
    search_fields = ("name", "prompt")
    inlines = (HouseAspectOptionInline,)


@admin.register(HouseFeature)
class HouseFeatureAdmin(admin.ModelAdmin):
    """#2079 — cultural facts stamped on houses; slug is the code anchor."""

    list_display = ("name", "slug", "display_order")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


class HouseClaimAspectInline(admin.TabularInline):
    """#2079 — the founder's picks, read-only for the review queue."""

    model = HouseClaimAspect
    extra = 0
    readonly_fields = ("definition", "option")
    can_delete = False

    def has_add_permission(self, request: object, obj: object = None) -> bool:  # noqa: ARG002
        return False


@admin.register(HouseClaim)
class HouseClaimAdmin(admin.ModelAdmin):
    """#1884 Phase D — approve/reject CG house claims (v1 review surface).

    Approval is the staff greenlight only; the house materializes at CG
    finalization, so approving here never creates rows by itself.
    """

    autocomplete_fields = ["reviewed_by"]

    list_display = ("house_name", "title", "template", "status", "created_at", "reviewed_by")
    list_select_related = ("title", "template", "reviewed_by")
    list_filter = ("status",)
    search_fields = ("house_name", "backstory")
    readonly_fields = ("draft", "reviewed_by", "reviewed_at")
    actions = ("approve_claims", "reject_claims")
    inlines = (HouseClaimAspectInline,)

    @admin.action(description="Approve selected claims")
    def approve_claims(self, request, queryset):
        from world.societies.houses.creator import approve_house_claim  # noqa: PLC0415

        for claim in queryset:
            approve_house_claim(claim, reviewer=request.user)
        self.message_user(request, f"Approved {queryset.count()} claim(s).")

    @admin.action(description="Reject selected claims")
    def reject_claims(self, request, queryset):
        from world.societies.houses.creator import reject_house_claim  # noqa: PLC0415

        for claim in queryset:
            reject_house_claim(claim, reviewer=request.user)
        self.message_user(request, f"Rejected {queryset.count()} claim(s).")
