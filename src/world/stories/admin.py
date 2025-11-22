from django.contrib import admin
from django.utils.html import format_html

from world.stories.models import (
    Chapter,
    Episode,
    EpisodeScene,
    PlayerTrustLevel,
    Story,
    StoryFeedback,
    StoryParticipation,
    StoryTrustRequirement,
    TrustCategory,
    TrustCategoryFeedbackRating,
)


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "status",
        "privacy",
        "is_personal_story",
        "active_gms_count",
        "participants_count",
        "created_at",
    ]
    list_filter = ["status", "privacy", "is_personal_story", "created_at"]
    search_fields = ["title", "description"]
    filter_horizontal = ["owners", "active_gms"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("title", "description", "status", "privacy")}),
        ("Ownership & Management", {"fields": ("owners", "active_gms")}),
        (
            "Personal Story",
            {
                "fields": ("is_personal_story", "personal_story_character"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at", "completed_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def active_gms_count(self, obj):
        return obj.active_gms.count()

    active_gms_count.short_description = "Active GMs"

    def participants_count(self, obj):
        return obj.participants.filter(is_active=True).count()

    participants_count.short_description = "Active Participants"


@admin.register(StoryParticipation)
class StoryParticipationAdmin(admin.ModelAdmin):
    list_display = [
        "character",
        "story",
        "participation_level",
        "trusted_by_owner",
        "is_active",
        "joined_at",
    ]
    list_filter = ["participation_level", "trusted_by_owner", "is_active", "joined_at"]
    search_fields = ["character__db_key", "story__title"]
    readonly_fields = ["joined_at"]

    fieldsets = (
        (None, {"fields": ("story", "character", "participation_level", "is_active")}),
        (
            "Trust & Permissions",
            {"fields": ("trusted_by_owner",)},
        ),
        ("Tracking", {"fields": ("joined_at",), "classes": ("collapse",)}),
    )


class EpisodeInline(admin.TabularInline):
    model = Episode
    extra = 0
    fields = ["order", "title", "is_active", "completed_at"]
    readonly_fields = ["completed_at"]


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = [
        "story",
        "order",
        "title",
        "is_active",
        "episodes_count",
        "completed_at",
    ]
    list_filter = ["is_active", "completed_at", "created_at"]
    search_fields = ["title", "story__title"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [EpisodeInline]

    fieldsets = (
        (None, {"fields": ("story", "order", "title", "description", "is_active")}),
        (
            "Narrative Tracking",
            {"fields": ("summary", "consequences"), "classes": ("collapse",)},
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at", "completed_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def episodes_count(self, obj):
        return obj.episodes.count()

    episodes_count.short_description = "Episodes"


class EpisodeSceneInline(admin.TabularInline):
    model = EpisodeScene
    extra = 0
    fields = ["order", "scene", "connection_to_next", "connection_summary"]


@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = [
        "chapter",
        "order",
        "title",
        "is_active",
        "scenes_count",
        "connection_display",
        "completed_at",
    ]
    list_filter = ["is_active", "connection_to_next", "completed_at", "created_at"]
    search_fields = ["title", "chapter__title", "chapter__story__title"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [EpisodeSceneInline]

    fieldsets = (
        (None, {"fields": ("chapter", "order", "title", "description", "is_active")}),
        (
            "Narrative Connections",
            {
                "fields": (
                    "connection_to_next",
                    "connection_summary",
                    "summary",
                    "consequences",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at", "completed_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def scenes_count(self, obj):
        return obj.episode_scenes.count()

    scenes_count.short_description = "Scenes"

    def connection_display(self, obj):
        if obj.connection_to_next:
            return format_html(
                '<span style="color: {};">{}</span>',
                (
                    "#28a745"
                    if obj.connection_to_next in ["therefore", "but"]
                    else "#ffc107"
                ),
                obj.connection_to_next.title(),
            )
        return "-"

    connection_display.short_description = "Connection Type"


@admin.register(EpisodeScene)
class EpisodeSceneAdmin(admin.ModelAdmin):
    list_display = [
        "episode",
        "order",
        "scene",
        "connection_to_next",
        "connection_summary",
    ]
    list_filter = ["connection_to_next"]
    search_fields = ["episode__title", "episode__chapter__story__title", "scene__name"]

    fieldsets = (
        (None, {"fields": ("episode", "scene", "order")}),
        (
            "Narrative Connection",
            {"fields": ("connection_to_next", "connection_summary")},
        ),
    )


class TrustCategoryFeedbackRatingInline(admin.TabularInline):
    model = TrustCategoryFeedbackRating
    extra = 0
    fields = ["trust_category", "rating", "notes"]


@admin.register(StoryFeedback)
class StoryFeedbackAdmin(admin.ModelAdmin):
    list_display = [
        "story",
        "reviewed_player",
        "reviewer",
        "average_rating_display",
        "is_gm_feedback",
        "created_at",
    ]
    list_filter = ["is_gm_feedback", "created_at"]
    search_fields = [
        "story__title",
        "reviewed_player__username",
        "reviewer__username",
        "comments",
    ]
    readonly_fields = ["created_at"]
    inlines = [TrustCategoryFeedbackRatingInline]

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "story",
                    "reviewer",
                    "reviewed_player",
                    "is_gm_feedback",
                ),
            },
        ),
        ("Feedback Details", {"fields": ("comments",)}),
        ("Timestamp", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    def average_rating_display(self, obj):
        avg = obj.get_average_rating()
        if avg > 1:
            color = "#28a745"  # Green
        elif avg > 0:
            color = "#17a2b8"  # Light blue
        elif avg == 0:
            color = "#6c757d"  # Gray
        else:
            color = "#dc3545"  # Red

        return format_html('<span style="color: {};">{:.1f}</span>', color, avg)

    average_rating_display.short_description = "Avg Rating"


@admin.register(TrustCategory)
class TrustCategoryAdmin(admin.ModelAdmin):
    list_display = ["display_name", "name", "is_active", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "display_name", "description"]
    readonly_fields = ["created_at"]

    fieldsets = (
        (None, {"fields": ("name", "display_name", "description")}),
        ("Organization", {"fields": ("is_active",)}),
        (
            "Metadata",
            {"fields": ("created_by", "created_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(PlayerTrustLevel)
class PlayerTrustLevelAdmin(admin.ModelAdmin):
    list_display = [
        "player_trust",
        "trust_category",
        "trust_level_display",
        "feedback_summary",
        "updated_at",
    ]
    list_filter = ["trust_level", "trust_category", "updated_at"]
    search_fields = ["player_trust__account__username", "trust_category__name", "notes"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None, {"fields": ("player_trust", "trust_category", "trust_level")}),
        (
            "Feedback Tracking",
            {"fields": ("positive_feedback_count", "negative_feedback_count")},
        ),
        (
            "Metadata",
            {
                "fields": ("notes", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def trust_level_display(self, obj):
        colors = {
            0: "#dc3545",  # Red - Untrusted
            1: "#ffc107",  # Yellow - Basic
            2: "#17a2b8",  # Light blue - Intermediate
            3: "#28a745",  # Green - Advanced
            4: "#007bff",  # Blue - Expert
        }
        return format_html(
            '<span style="color: {};">{}</span>',
            colors.get(obj.trust_level, "#6c757d"),
            obj.get_trust_level_display(),
        )

    trust_level_display.short_description = "Trust Level"

    def feedback_summary(self, obj):
        return f"+{obj.positive_feedback_count}/-{obj.negative_feedback_count}"

    feedback_summary.short_description = "Feedback"


@admin.register(StoryTrustRequirement)
class StoryTrustRequirementAdmin(admin.ModelAdmin):
    list_display = [
        "story",
        "trust_category",
        "minimum_trust_level_display",
        "created_by",
        "created_at",
    ]
    list_filter = ["minimum_trust_level", "trust_category", "created_at"]
    search_fields = ["story__title", "trust_category__name", "notes"]
    readonly_fields = ["created_at"]

    fieldsets = (
        (None, {"fields": ("story", "trust_category", "minimum_trust_level")}),
        (
            "Metadata",
            {"fields": ("created_by", "notes", "created_at"), "classes": ("collapse",)},
        ),
    )

    def minimum_trust_level_display(self, obj):
        colors = {
            0: "#dc3545",  # Red - Untrusted
            1: "#ffc107",  # Yellow - Basic
            2: "#17a2b8",  # Light blue - Intermediate
            3: "#28a745",  # Green - Advanced
            4: "#007bff",  # Blue - Expert
        }
        return format_html(
            '<span style="color: {};">{}</span>',
            colors.get(obj.minimum_trust_level, "#6c757d"),
            obj.get_minimum_trust_level_display(),
        )

    minimum_trust_level_display.short_description = "Min Trust Level"
