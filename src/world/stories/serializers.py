from rest_framework import serializers

from world.stories.models import (
    Chapter,
    Episode,
    EpisodeScene,
    PlayerTrust,
    PlayerTrustLevel,
    Story,
    StoryFeedback,
    StoryParticipation,
    StoryTrustRequirement,
    TrustCategory,
    TrustCategoryFeedbackRating,
)


class StoryListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for story list views"""

    owners_count = serializers.IntegerField(source="owners.count", read_only=True)
    active_gms_count = serializers.IntegerField(
        source="active_gms.count",
        read_only=True,
    )
    participants_count = serializers.IntegerField(
        source="participants.filter(is_active=True).count",
        read_only=True,
    )

    class Meta:
        model = Story
        fields = [
            "id",
            "title",
            "status",
            "privacy",
            "is_personal_story",
            "owners_count",
            "active_gms_count",
            "participants_count",
            "created_at",
            "updated_at",
        ]


class StoryDetailSerializer(serializers.ModelSerializer):
    """Full serializer for story detail views"""

    owners = serializers.StringRelatedField(many=True, read_only=True)
    active_gms = serializers.StringRelatedField(many=True, read_only=True)
    personal_story_character = serializers.StringRelatedField(read_only=True)
    chapters_count = serializers.IntegerField(source="chapters.count", read_only=True)
    trust_requirements = serializers.SerializerMethodField()

    class Meta:
        model = Story
        fields = [
            "id",
            "title",
            "description",
            "status",
            "privacy",
            "owners",
            "active_gms",
            "trust_requirements",
            "is_personal_story",
            "personal_story_character",
            "chapters_count",
            "created_at",
            "updated_at",
            "completed_at",
        ]

    def get_trust_requirements(self, obj):
        """Get trust requirements for this story"""
        return obj.get_trust_requirements_summary()


class StoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating stories"""

    class Meta:
        model = Story
        fields = [
            "title",
            "description",
            "privacy",
            "is_personal_story",
            "personal_story_character",
        ]

    # Title validation constants
    MIN_TITLE_LENGTH = 3
    MAX_TITLE_LENGTH = 200

    # Comment validation constants
    MIN_COMMENT_LENGTH = 10

    def validate_title(self, value):
        """Ensure title is not empty and has reasonable length"""
        if len(value.strip()) < self.MIN_TITLE_LENGTH:
            msg = "Title must be at least 3 characters long"
            raise serializers.ValidationError(
                msg,
            )
        if len(value) > self.MAX_TITLE_LENGTH:
            msg = "Title cannot exceed 200 characters"
            raise serializers.ValidationError(msg)
        return value.strip()

    def validate(self, data):
        """Cross-field validation"""
        if data.get("is_personal_story") and not data.get("personal_story_character"):
            msg = "Personal stories must specify a character"
            raise serializers.ValidationError(
                msg,
            )

        if data.get("personal_story_character") and not data.get("is_personal_story"):
            msg = "Only personal stories can have a character specified"
            raise serializers.ValidationError(
                msg,
            )

        return data


class StoryParticipationSerializer(serializers.ModelSerializer):
    """Serializer for story participation"""

    story = serializers.StringRelatedField(read_only=True)
    character = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = StoryParticipation
        fields = [
            "id",
            "story",
            "character",
            "participation_level",
            "trusted_by_owner",
            "joined_at",
            "is_active",
        ]


class ChapterListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for chapter lists"""

    story = serializers.StringRelatedField(read_only=True)
    episodes_count = serializers.IntegerField(source="episodes.count", read_only=True)

    class Meta:
        model = Chapter
        fields = [
            "id",
            "story",
            "title",
            "order",
            "is_active",
            "episodes_count",
            "completed_at",
            "created_at",
        ]


class ChapterDetailSerializer(serializers.ModelSerializer):
    """Full serializer for chapter details"""

    story = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Chapter
        fields = [
            "id",
            "story",
            "title",
            "description",
            "order",
            "is_active",
            "summary",
            "consequences",
            "completed_at",
            "created_at",
            "updated_at",
        ]


class ChapterCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating chapters"""

    MIN_TITLE_LENGTH = StoryCreateSerializer.MIN_TITLE_LENGTH

    class Meta:
        model = Chapter
        fields = ["story", "title", "description", "order"]

    def validate_title(self, value):
        """Validate chapter title"""
        if len(value.strip()) < self.MIN_TITLE_LENGTH:
            msg = "Chapter title must be at least 3 characters"
            raise serializers.ValidationError(
                msg,
            )
        return value.strip()

    def validate(self, data):
        """Validate chapter order is unique within story"""
        story = data.get("story")
        order = data.get("order")

        if story and Chapter.objects.filter(story=story, order=order).exists():
            msg = f"Chapter with order {order} already exists for this story"
            raise serializers.ValidationError(
                msg,
            )

        return data


class EpisodeListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for episode lists"""

    chapter = serializers.StringRelatedField(read_only=True)
    scenes_count = serializers.IntegerField(
        source="episode_scenes.count",
        read_only=True,
    )

    class Meta:
        model = Episode
        fields = [
            "id",
            "chapter",
            "title",
            "order",
            "is_active",
            "connection_to_next",
            "scenes_count",
            "completed_at",
        ]


class EpisodeDetailSerializer(serializers.ModelSerializer):
    """Full serializer for episode details"""

    chapter = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Episode
        fields = [
            "id",
            "chapter",
            "title",
            "description",
            "order",
            "is_active",
            "summary",
            "consequences",
            "connection_to_next",
            "connection_summary",
            "completed_at",
            "created_at",
            "updated_at",
        ]


class EpisodeCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating episodes"""

    MIN_TITLE_LENGTH = StoryCreateSerializer.MIN_TITLE_LENGTH

    class Meta:
        model = Episode
        fields = [
            "chapter",
            "title",
            "description",
            "order",
            "connection_to_next",
            "connection_summary",
        ]

    def validate_title(self, value):
        """Validate episode title"""
        if len(value.strip()) < self.MIN_TITLE_LENGTH:
            msg = "Episode title must be at least 3 characters"
            raise serializers.ValidationError(
                msg,
            )
        return value.strip()

    def validate(self, data):
        """Validate episode order is unique within chapter"""
        chapter = data.get("chapter")
        order = data.get("order")

        if chapter and Episode.objects.filter(chapter=chapter, order=order).exists():
            msg = f"Episode with order {order} already exists for this chapter"
            raise serializers.ValidationError(
                msg,
            )

        return data


class EpisodeSceneSerializer(serializers.ModelSerializer):
    """Serializer for episode-scene connections"""

    episode = serializers.StringRelatedField(read_only=True)
    scene = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = EpisodeScene
        fields = [
            "id",
            "episode",
            "scene",
            "order",
            "connection_to_next",
            "connection_summary",
        ]


class PlayerTrustSerializer(serializers.ModelSerializer):
    """Serializer for player trust profiles"""

    account = serializers.StringRelatedField(read_only=True)
    total_positive_feedback = serializers.ReadOnlyField()
    total_negative_feedback = serializers.ReadOnlyField()

    class Meta:
        model = PlayerTrust
        fields = [
            "id",
            "account",
            "gm_trust_level",
            "total_positive_feedback",
            "total_negative_feedback",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "total_positive_feedback",
            "total_negative_feedback",
            "created_at",
            "updated_at",
        ]


class TrustCategorySerializer(serializers.ModelSerializer):
    """Serializer for trust categories"""

    class Meta:
        model = TrustCategory
        fields = [
            "id",
            "name",
            "display_name",
            "description",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class TrustCategoryFeedbackRatingSerializer(serializers.ModelSerializer):
    """Serializer for trust category feedback ratings"""

    trust_category = TrustCategorySerializer(read_only=True)

    class Meta:
        model = TrustCategoryFeedbackRating
        fields = ["id", "trust_category", "rating", "notes"]


class StoryFeedbackSerializer(serializers.ModelSerializer):
    """Serializer for story feedback"""

    story = serializers.StringRelatedField(read_only=True)
    reviewer = serializers.StringRelatedField(read_only=True)
    reviewed_player = serializers.StringRelatedField(read_only=True)
    category_ratings = TrustCategoryFeedbackRatingSerializer(many=True, read_only=True)
    average_rating = serializers.SerializerMethodField()
    is_overall_positive = serializers.SerializerMethodField()

    class Meta:
        model = StoryFeedback
        fields = [
            "id",
            "story",
            "reviewer",
            "reviewed_player",
            "category_ratings",
            "average_rating",
            "is_overall_positive",
            "is_gm_feedback",
            "comments",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_average_rating(self, obj):
        """Get average rating across all categories"""
        return obj.get_average_rating()

    def get_is_overall_positive(self, obj):
        """Get whether feedback is overall positive"""
        return obj.is_overall_positive()

    def validate_comments(self, value):
        """Ensure feedback has meaningful content"""
        if len(value.strip()) < self.MIN_COMMENT_LENGTH:
            msg = "Feedback comments must be at least 10 characters long"
            raise serializers.ValidationError(
                msg,
            )
        return value.strip()


class TrustCategoryFeedbackRatingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating trust category feedback ratings"""

    class Meta:
        model = TrustCategoryFeedbackRating
        fields = ["trust_category", "rating", "notes"]

    def validate_rating(self, value):
        """Validate rating is within range"""
        if value not in [-2, -1, 0, 1, 2]:
            msg = "Rating must be between -2 and 2"
            raise serializers.ValidationError(msg)
        return value


class StoryFeedbackCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating story feedback with category ratings"""

    category_ratings = TrustCategoryFeedbackRatingCreateSerializer(many=True)
    MIN_COMMENT_LENGTH = StoryCreateSerializer.MIN_COMMENT_LENGTH

    class Meta:
        model = StoryFeedback
        fields = [
            "story",
            "reviewed_player",
            "is_gm_feedback",
            "comments",
            "category_ratings",
        ]

    def create(self, validated_data):
        """Create feedback with category ratings"""
        category_ratings_data = validated_data.pop("category_ratings", [])
        feedback = StoryFeedback.objects.create(**validated_data)

        for rating_data in category_ratings_data:
            TrustCategoryFeedbackRating.objects.create(feedback=feedback, **rating_data)

        return feedback

    def validate_comments(self, value):
        """Ensure feedback has meaningful content"""
        if len(value.strip()) < self.MIN_COMMENT_LENGTH:
            msg = "Feedback comments must be at least 10 characters long"
            raise serializers.ValidationError(
                msg,
            )
        return value.strip()

    def validate(self, data):
        """Prevent self-feedback and duplicate feedback"""
        request = self.context.get("request")
        if request and request.user == data.get("reviewed_player"):
            msg = "You cannot provide feedback on yourself"
            raise serializers.ValidationError(msg)

        # Check for duplicate feedback
        story = data.get("story")
        reviewed_player = data.get("reviewed_player")
        if (
            request
            and StoryFeedback.objects.filter(
                story=story,
                reviewer=request.user,
                reviewed_player=reviewed_player,
            ).exists()
        ):
            msg = "You have already provided feedback for this player in this story"
            raise serializers.ValidationError(
                msg,
            )

        return data


# Trust Category Serializers


class TrustCategoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating trust categories"""

    class Meta:
        model = TrustCategory
        fields = ["name", "display_name", "description"]

    def validate_name(self, value):
        """Validate category name is slug-like"""
        if not value.replace("_", "").replace("-", "").isalnum():
            msg = "Category name should only contain letters, numbers, underscores, and hyphens"
            raise serializers.ValidationError(
                msg,
            )
        return value.lower()


class PlayerTrustLevelSerializer(serializers.ModelSerializer):
    """Serializer for individual trust levels"""

    player_trust = serializers.StringRelatedField(read_only=True)
    trust_category = TrustCategorySerializer(read_only=True)

    class Meta:
        model = PlayerTrustLevel
        fields = [
            "id",
            "player_trust",
            "trust_category",
            "trust_level",
            "positive_feedback_count",
            "negative_feedback_count",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "positive_feedback_count",
            "negative_feedback_count",
            "created_at",
            "updated_at",
        ]


class StoryTrustRequirementSerializer(serializers.ModelSerializer):
    """Serializer for story trust requirements"""

    trust_category = TrustCategorySerializer(read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = StoryTrustRequirement
        fields = [
            "id",
            "trust_category",
            "minimum_trust_level",
            "notes",
            "created_by",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class StoryTrustRequirementCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating story trust requirements"""

    class Meta:
        model = StoryTrustRequirement
        fields = ["story", "trust_category", "minimum_trust_level", "notes"]
