"""GM admin configuration."""

from django.contrib import admin

from world.gm.models import (
    CatalogSuggestion,
    CheckTypeSituationFit,
    ConsequencePoolGuide,
    DistinctionChangeRequestDetails,
    GMApplication,
    GMLevelCap,
    GMLevelChange,
    GMProfile,
    GMRewardConfig,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
    GMWeeklyRewardTracker,
    ProfileTextRequestDetails,
    SituationDifficultyGuide,
    SituationKind,
    StoryArea,
    StoryRoomGrant,
    TableUpdateRequest,
)


@admin.register(GMProfile)
class GMProfileAdmin(admin.ModelAdmin):
    list_display = ["account", "level", "approved_at"]
    list_filter = ["level"]
    raw_id_fields = ["account", "approved_by"]
    search_fields = ["account__username"]


@admin.register(GMApplication)
class GMApplicationAdmin(admin.ModelAdmin):
    list_display = ["account", "status", "created_at", "reviewed_by"]
    list_filter = ["status"]
    raw_id_fields = ["account", "reviewed_by"]


@admin.register(GMTable)
class GMTableAdmin(admin.ModelAdmin):
    list_display = ["name", "gm", "status", "created_at"]
    list_filter = ["status"]
    raw_id_fields = ["gm"]


@admin.register(GMTableMembership)
class GMTableMembershipAdmin(admin.ModelAdmin):
    list_display = ["table", "persona", "joined_at", "left_at"]
    list_filter = ["left_at"]
    raw_id_fields = ["table", "persona"]


@admin.register(GMRosterInvite)
class GMRosterInviteAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "roster_entry",
        "created_by",
        "created_at",
        "expires_at",
        "is_public",
        "claimed_by",
    ]
    list_filter = ["is_public", "claimed_at"]
    search_fields = ["code", "invited_email"]
    raw_id_fields = ["roster_entry", "created_by", "claimed_by"]


@admin.register(GMLevelCap)
class GMLevelCapAdmin(admin.ModelAdmin):
    list_display = [
        "level",
        "max_beat_risk",
        "allow_custom_stakes",
        "allow_global_scope_authoring",
        "auto_clear_regional",
        "max_story_areas",
        "max_story_rooms_per_area",
    ]
    list_filter = [
        "max_beat_risk",
        "allow_custom_stakes",
        "allow_global_scope_authoring",
        "auto_clear_regional",
    ]


@admin.register(GMLevelChange)
class GMLevelChangeAdmin(admin.ModelAdmin):
    """Audit row for a staff-driven GM level change — written by ``promote_gm`` only.

    Read-only in admin: no add/change/delete, so the audit trail can't be
    hand-edited or backdated.
    """

    list_display = ["profile", "old_level", "new_level", "changed_by", "created_at"]
    list_filter = ["old_level", "new_level"]
    raw_id_fields = ["profile", "changed_by"]

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        return False

    def has_change_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(StoryArea)
class StoryAreaAdmin(admin.ModelAdmin):
    list_display = ("area", "gm", "created_at")
    raw_id_fields = ("gm", "area")


@admin.register(StoryRoomGrant)
class StoryRoomGrantAdmin(admin.ModelAdmin):
    list_display = ("room", "character", "granted_by", "created_at")
    raw_id_fields = ("room", "character", "granted_by", "return_location")


@admin.register(SituationKind)
class SituationKindAdmin(admin.ModelAdmin):
    list_display = ["name", "minimum_gm_level"]
    list_filter = ["minimum_gm_level"]
    search_fields = ["name"]


@admin.register(CheckTypeSituationFit)
class CheckTypeSituationFitAdmin(admin.ModelAdmin):
    list_display = ["situation_kind", "check_type"]
    list_filter = ["situation_kind"]
    raw_id_fields = ["check_type", "situation_kind"]


@admin.register(SituationDifficultyGuide)
class SituationDifficultyGuideAdmin(admin.ModelAdmin):
    list_display = ["situation_kind", "risk", "recommended_difficulty"]
    list_filter = ["risk", "recommended_difficulty"]
    raw_id_fields = ["situation_kind"]


@admin.register(ConsequencePoolGuide)
class ConsequencePoolGuideAdmin(admin.ModelAdmin):
    list_display = ["situation_kind", "pool", "is_default"]
    list_filter = ["is_default"]
    raw_id_fields = ["situation_kind", "pool"]


@admin.register(CatalogSuggestion)
class CatalogSuggestionAdmin(admin.ModelAdmin):
    list_display = ["submitted_by", "proposal_kind", "status", "created_at", "reviewer"]
    list_filter = ["proposal_kind", "status"]
    raw_id_fields = ["submitted_by", "situation_kind", "reviewer"]
    search_fields = ["proposal_text"]


@admin.register(GMRewardConfig)
class GMRewardConfigAdmin(admin.ModelAdmin):
    """Admin interface for the GM Story Reward's tunable award values (#2123)."""

    list_display = [
        "beat_xp_per_player",
        "beat_xp_cap",
        "episode_xp_per_player",
        "episode_xp_cap",
        "story_completion_xp_per_player",
        "story_completion_xp_cap",
        "weekly_reward_cap",
        "feedback_xp_per_rating_point",
    ]

    fieldsets = (
        (
            "Beat mark",
            {"fields": ("beat_xp_per_player", "beat_xp_cap")},
        ),
        (
            "Episode resolution",
            {"fields": ("episode_xp_per_player", "episode_xp_cap")},
        ),
        (
            "Story completion",
            {"fields": ("story_completion_xp_per_player", "story_completion_xp_cap")},
        ),
        (
            "Story feedback",
            {"fields": ("feedback_xp_per_rating_point",)},
        ),
        (
            "Weekly ceiling",
            {"fields": ("weekly_reward_cap",)},
        ),
    )

    def has_add_permission(self, request) -> bool:  # noqa: ARG002
        """Singleton — no adding a second row via admin."""
        return not GMRewardConfig.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        """Singleton — never delete the row (services rely on it existing)."""
        return False


@admin.register(GMWeeklyRewardTracker)
class GMWeeklyRewardTrackerAdmin(admin.ModelAdmin):
    """Admin interface for the per-GM weekly reward ledger (#2123). Read-only audit."""

    list_display = ["gm_profile", "game_week", "xp_awarded_this_week"]
    list_filter = ["game_week"]
    raw_id_fields = ["gm_profile", "game_week"]
    search_fields = ["gm_profile__account__username"]


class ProfileTextRequestDetailsInline(admin.StackedInline):
    """Inline payload view for PROFILE_TEXT requests (#2631)."""

    model = ProfileTextRequestDetails
    extra = 0
    raw_id_fields = ["applied_version"]


class DistinctionChangeRequestDetailsInline(admin.StackedInline):
    """Inline payload view for DISTINCTION_CHANGE requests (#2631)."""

    model = DistinctionChangeRequestDetails
    extra = 0
    raw_id_fields = ["distinction", "character_distinction", "sheet_update_request"]


@admin.register(TableUpdateRequest)
class TableUpdateRequestAdmin(admin.ModelAdmin):
    """Admin for player-submitted sheet-update requests (#2631)."""

    list_display = ["__str__", "kind", "status", "created_at", "resolved_by"]
    list_filter = ["kind", "status"]
    raw_id_fields = ["membership", "resolved_by"]
    readonly_fields = ["created_at", "resolved_at", "completed_at"]
    inlines = [ProfileTextRequestDetailsInline, DistinctionChangeRequestDetailsInline]
