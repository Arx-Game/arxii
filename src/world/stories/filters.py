from django.db import models
import django_filters

from world.stories.models import (
    Chapter,
    Episode,
    EpisodeScene,
    PlayerTrust,
    PlayerTrustLevel,
    Story,
    StoryFeedback,
    StoryParticipation,
    TrustCategory,
)


class StoryFilter(django_filters.FilterSet):
    """Filter for Story model"""

    status = django_filters.CharFilter(field_name="status")
    privacy = django_filters.CharFilter(field_name="privacy")

    # Text search
    search = django_filters.CharFilter(method="filter_search", label="Search")

    # Owner filtering by username
    owner = django_filters.CharFilter(method="filter_owner", label="Owner Username")

    # Trust category filtering
    requires_trust_category = django_filters.CharFilter(
        method="filter_requires_trust_category", label="Requires Trust Category"
    )

    # Date range filtering
    created_after = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )

    class Meta:
        model = Story
        fields = ["status", "privacy", "is_personal_story"]

    def filter_search(self, queryset, name, value):
        """Search in title and description"""
        return queryset.filter(
            models.Q(title__icontains=value) | models.Q(description__icontains=value)
        )

    def filter_owner(self, queryset, name, value):
        """Filter by owner username"""
        return queryset.filter(owners__username__icontains=value)

    def filter_requires_trust_category(self, queryset, name, value):
        """Filter stories that require a specific trust category"""
        return queryset.filter(trust_requirements__trust_category__name=value)


class StoryParticipationFilter(django_filters.FilterSet):
    """Filter for StoryParticipation model"""

    story = django_filters.NumberFilter(field_name="story_id")
    character = django_filters.CharFilter(
        method="filter_character", label="Character Name"
    )
    participation_level = django_filters.CharFilter(field_name="participation_level")
    trusted_by_owner = django_filters.BooleanFilter()

    # Date filtering
    joined_after = django_filters.DateTimeFilter(
        field_name="joined_at", lookup_expr="gte"
    )

    class Meta:
        model = StoryParticipation
        fields = ["story", "participation_level", "is_active", "trusted_by_owner"]

    def filter_character(self, queryset, name, value):
        """Filter by character name"""
        return queryset.filter(character__db_key__icontains=value)


class ChapterFilter(django_filters.FilterSet):
    """Filter for Chapter model"""

    story = django_filters.NumberFilter(field_name="story_id")
    story_title = django_filters.CharFilter(
        field_name="story__title", lookup_expr="icontains"
    )

    # Order range filtering
    order_min = django_filters.NumberFilter(field_name="order", lookup_expr="gte")
    order_max = django_filters.NumberFilter(field_name="order", lookup_expr="lte")

    class Meta:
        model = Chapter
        fields = ["story", "is_active", "order"]


class EpisodeFilter(django_filters.FilterSet):
    """Filter for Episode model"""

    chapter = django_filters.NumberFilter(field_name="chapter_id")
    story = django_filters.NumberFilter(field_name="chapter__story_id")
    connection_to_next = django_filters.CharFilter(field_name="connection_to_next")

    # Order range filtering
    order_min = django_filters.NumberFilter(field_name="order", lookup_expr="gte")
    order_max = django_filters.NumberFilter(field_name="order", lookup_expr="lte")

    class Meta:
        model = Episode
        fields = ["chapter", "is_active", "connection_to_next"]


class EpisodeSceneFilter(django_filters.FilterSet):
    """Filter for EpisodeScene model"""

    episode = django_filters.NumberFilter(field_name="episode_id")
    connection_to_next = django_filters.CharFilter(field_name="connection_to_next")
    story = django_filters.NumberFilter(field_name="episode__chapter__story_id")

    class Meta:
        model = EpisodeScene
        fields = ["episode", "connection_to_next", "order"]


class PlayerTrustFilter(django_filters.FilterSet):
    """Filter for PlayerTrust model"""

    account = django_filters.CharFilter(
        method="filter_account", label="Account Username"
    )

    gm_trust_level = django_filters.NumberFilter()

    # Feedback filtering
    has_positive_feedback = django_filters.BooleanFilter(
        method="filter_has_positive_feedback"
    )
    has_negative_feedback = django_filters.BooleanFilter(
        method="filter_has_negative_feedback"
    )

    class Meta:
        model = PlayerTrust
        fields = ["gm_trust_level"]

    def filter_account(self, queryset, name, value):
        """Filter by account username"""
        return queryset.filter(account__username__icontains=value)

    def filter_has_positive_feedback(self, queryset, name, value):
        """Filter for accounts with positive feedback"""
        if value:
            return queryset.filter(
                trust_levels__positive_feedback_count__gt=0
            ).distinct()
        return queryset.exclude(trust_levels__positive_feedback_count__gt=0).distinct()

    def filter_has_negative_feedback(self, queryset, name, value):
        """Filter for accounts with negative feedback"""
        if value:
            return queryset.filter(
                trust_levels__negative_feedback_count__gt=0
            ).distinct()
        return queryset.exclude(trust_levels__negative_feedback_count__gt=0).distinct()


class StoryFeedbackFilter(django_filters.FilterSet):
    """Filter for StoryFeedback model"""

    story = django_filters.NumberFilter(field_name="story_id")
    story_title = django_filters.CharFilter(
        field_name="story__title", lookup_expr="icontains"
    )
    reviewer = django_filters.CharFilter(
        method="filter_reviewer", label="Reviewer Username"
    )
    reviewed_player = django_filters.CharFilter(
        method="filter_reviewed_player", label="Reviewed Player Username"
    )

    # Trust category filtering
    trust_category = django_filters.CharFilter(
        method="filter_trust_category", label="Trust Category"
    )

    # Date range filtering
    created_after = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )

    class Meta:
        model = StoryFeedback
        fields = ["story", "is_gm_feedback"]

    def filter_reviewer(self, queryset, name, value):
        """Filter by reviewer username"""
        return queryset.filter(reviewer__username__icontains=value)

    def filter_reviewed_player(self, queryset, name, value):
        """Filter by reviewed player username"""
        return queryset.filter(reviewed_player__username__icontains=value)

    def filter_trust_category(self, queryset, name, value):
        """Filter feedback that applies to a specific trust category"""
        return queryset.filter(trust_categories__name=value)


# New filters for trust system


class TrustCategoryFilter(django_filters.FilterSet):
    """Filter for TrustCategory model"""

    name = django_filters.CharFilter(lookup_expr="icontains")
    display_name = django_filters.CharFilter(lookup_expr="icontains")
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = TrustCategory
        fields = ["name", "display_name", "is_active"]


class PlayerTrustLevelFilter(django_filters.FilterSet):
    """Filter for PlayerTrustLevel model"""

    account = django_filters.CharFilter(
        method="filter_account", label="Account Username"
    )
    trust_category = django_filters.CharFilter(
        field_name="trust_category__name", lookup_expr="icontains"
    )
    trust_level = django_filters.NumberFilter()
    trust_level_min = django_filters.NumberFilter(
        field_name="trust_level", lookup_expr="gte"
    )

    class Meta:
        model = PlayerTrustLevel
        fields = ["trust_category", "trust_level"]

    def filter_account(self, queryset, name, value):
        """Filter by account username"""
        return queryset.filter(player_trust__account__username__icontains=value)
