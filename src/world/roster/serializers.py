"""
DRF Serializers for the roster system.
These provide structured validation and error handling for the web API.
"""

from evennia.objects.models import ObjectDB
from rest_framework import serializers

from world.roster.models import (
    ApplicationStatus,
    Roster,
    RosterApplication,
    RosterEntry,
    RosterTenure,
    TenureMedia,
    ValidationErrorCodes,
    ValidationMessages,
)
from world.roster.selectors import TrustEvaluator, get_visible_roster_entries_for_player


class CharacterGallerySerializer(serializers.Serializer):
    """Serialize a single gallery entry for a character."""

    name = serializers.CharField()
    url = serializers.CharField()


class CharacterSerializer(serializers.ModelSerializer):
    """Serialize character data for roster entry views."""

    name = serializers.CharField(source="db_key")
    background = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    char_class = serializers.SerializerMethodField()
    level = serializers.SerializerMethodField()
    stats = serializers.DictField(child=serializers.IntegerField(), default=dict)
    relationships = serializers.ListField(child=serializers.CharField(), default=list)
    galleries = CharacterGallerySerializer(many=True, default=list)

    class Meta:
        model = ObjectDB
        fields = (
            "id",
            "name",
            "background",
            "gender",
            "char_class",
            "level",
            "stats",
            "relationships",
            "galleries",
        )
        read_only_fields = fields

    def get_background(self, obj):
        """Return the character's background from Evennia attributes."""
        return getattr(obj.db, "background", "")

    def get_gender(self, obj):
        """Return the character's gender from Evennia attributes."""
        return getattr(obj.db, "gender", None)

    def get_char_class(self, obj):
        """Return the character's class from Evennia attributes."""
        return getattr(obj.db, "class", None)

    def get_level(self, obj):
        """Return the character's level from Evennia attributes."""
        return getattr(obj.db, "level", None)


class TenureMediaSerializer(serializers.ModelSerializer):
    """Serialize media associated with a roster tenure."""

    class Meta:
        model = TenureMedia
        fields = (
            "id",
            "cloudinary_public_id",
            "cloudinary_url",
            "media_type",
            "title",
            "description",
            "sort_order",
            "is_public",
            "uploaded_date",
            "updated_date",
        )
        read_only_fields = fields


class RosterTenureSerializer(serializers.ModelSerializer):
    """Serialize roster tenure information with nested media."""

    media = TenureMediaSerializer(many=True, read_only=True)

    class Meta:
        model = RosterTenure
        fields = (
            "id",
            "player_number",
            "start_date",
            "end_date",
            "applied_date",
            "approved_date",
            "approved_by",
            "tenure_notes",
            "photo_folder",
            "media",
        )
        read_only_fields = fields


class RosterEntrySerializer(serializers.ModelSerializer):
    """Serialize roster entry data with nested character info."""

    character = CharacterSerializer(read_only=True)
    profile_picture = TenureMediaSerializer(read_only=True)
    tenures = RosterTenureSerializer(many=True, read_only=True)
    can_apply = serializers.SerializerMethodField()

    class Meta:
        model = RosterEntry
        fields = ("id", "character", "profile_picture", "tenures", "can_apply")
        read_only_fields = fields

    def get_can_apply(self, obj):
        """Return whether the requester may apply to play this character."""

        request = self.context.get("request")
        return bool(request and request.user.is_authenticated)


class MyRosterEntrySerializer(serializers.ModelSerializer):
    """Serialize a summary of a roster entry for account menus."""

    name = serializers.CharField(source="character.db_key")

    class Meta:
        model = RosterEntry
        fields = ("id", "name")
        read_only_fields = fields


class RosterApplicationSerializer(serializers.Serializer):
    """Validate a roster application message."""

    message = serializers.CharField()


class RosterApplicationCreateSerializer(serializers.Serializer):
    """
    Serializer for creating roster applications.
    Handles validation and provides structured error responses.
    """

    character_id = serializers.IntegerField()
    application_text = serializers.CharField(max_length=2000, min_length=50)

    def validate_character_id(self, value):
        """Validate that character exists and is valid for applications"""
        try:
            character = ObjectDB.objects.get(pk=value)
        except ObjectDB.DoesNotExist:
            raise serializers.ValidationError(
                {"code": "character_not_found", "message": "Character not found"}
            )

        return character

    def validate(self, attrs):
        """Perform full application validation"""
        character = attrs["character_id"]
        request = self.context["request"]
        player_data = request.user.player_data

        # Basic validation checks - moved from model
        self._validate_basic_eligibility(player_data, character)

        # Check policy issues (warnings, not blocking)
        from world.roster.policy_service import RosterPolicyService

        policy_issues = RosterPolicyService.get_policy_issues(player_data, character)

        attrs["character"] = character
        attrs["player_data"] = player_data
        attrs["policy_issues"] = policy_issues

        return attrs

    def _validate_basic_eligibility(self, player_data, character):
        """Basic validation checks that prevent application creation entirely"""

        # 1. Character must be on roster
        if not hasattr(character, "roster_entry"):
            raise serializers.ValidationError(
                {
                    "code": ValidationErrorCodes.CHARACTER_NOT_ON_ROSTER,
                    "message": ValidationMessages.CHARACTER_NOT_ON_ROSTER,
                }
            )

        # 2. Player cannot already be playing this character
        if character.roster_entry.tenures.filter(
            player_data=player_data, end_date__isnull=True
        ).exists():
            raise serializers.ValidationError(
                {
                    "code": ValidationErrorCodes.ALREADY_PLAYING_CHARACTER,
                    "message": ValidationMessages.ALREADY_PLAYING_CHARACTER,
                }
            )

        # 3. Character cannot already have an active player
        current_tenure = character.roster_entry.tenures.filter(
            end_date__isnull=True
        ).first()
        if current_tenure:
            raise serializers.ValidationError(
                {
                    "code": ValidationErrorCodes.CHARACTER_ALREADY_PLAYED,
                    "message": ValidationMessages.CHARACTER_ALREADY_PLAYED,
                }
            )

        # 4. Player cannot have duplicate pending applications
        existing_app = RosterApplication.objects.filter(
            player_data=player_data,
            character=character,
            status=ApplicationStatus.PENDING,
        ).first()
        if existing_app:
            raise serializers.ValidationError(
                {
                    "code": ValidationErrorCodes.DUPLICATE_PENDING_APPLICATION,
                    "message": ValidationMessages.DUPLICATE_PENDING_APPLICATION,
                }
            )

    def _get_policy_issues(self, player_data, character):
        """Get policy issues that would affect approval (but not creation)"""
        from world.roster.policy_service import RosterPolicyService

        return RosterPolicyService.get_policy_issues(player_data, character)

    def create(self, validated_data):
        """Create the application"""
        # Remove extra fields before creating
        policy_issues = validated_data.pop("policy_issues", [])

        application = RosterApplication.objects.create(
            player_data=validated_data["player_data"],
            character=validated_data["character"],
            application_text=validated_data["application_text"],
        )

        # Store policy issues for response
        application._policy_issues = policy_issues

        # Send email notifications explicitly (no signals used)
        from world.roster.email_service import RosterEmailService

        RosterEmailService.handle_new_application(application)

        return application

    def to_representation(self, instance):
        """Return structured response"""
        return {
            "id": instance.id,
            "status": instance.status,
            "character_name": instance.character.db_key,
            "applied_date": instance.applied_date,
            "policy_issues": getattr(instance, "_policy_issues", []),
            "requires_staff_review": bool(getattr(instance, "_policy_issues", [])),
        }


class RosterApplicationDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for retrieving application details.
    """

    character_name = serializers.CharField(source="character.db_key", read_only=True)
    player_username = serializers.CharField(
        source="player_data.account.username", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    policy_review_info = serializers.SerializerMethodField()

    class Meta:
        model = RosterApplication
        fields = [
            "id",
            "character_name",
            "player_username",
            "status",
            "status_display",
            "application_text",
            "review_notes",
            "applied_date",
            "reviewed_date",
            "policy_review_info",
        ]
        read_only_fields = ["applied_date", "reviewed_date"]

    def get_policy_review_info(self, obj):
        """Get policy review information for staff"""
        request = self.context.get("request")
        if request and request.user.player_data.can_approve_applications():
            return obj.get_policy_review_info()
        return None


class RosterApplicationApprovalSerializer(serializers.Serializer):
    """
    Serializer for approving/denying applications.
    """

    action = serializers.ChoiceField(choices=["approve", "deny"])
    review_notes = serializers.CharField(
        max_length=1000, required=False, allow_blank=True
    )

    def validate(self, attrs):
        """Validate that user can perform this action"""
        request = self.context["request"]
        application = self.context["application"]

        # Check if user can approve applications
        if not request.user.player_data.can_approve_applications():
            raise serializers.ValidationError(
                {
                    "code": "permission_denied",
                    "message": "You do not have permission to review applications",
                }
            )

        # Check application is still pending
        if application.status != ApplicationStatus.PENDING:
            raise serializers.ValidationError(
                {
                    "code": "invalid_status",
                    "message": f"Application is already {application.status}",
                }
            )

        return attrs

    def save(self):
        """Perform the approval/denial action"""
        application = self.context["application"]
        request = self.context["request"]
        action = self.validated_data["action"]
        review_notes = self.validated_data.get("review_notes", "")

        if action == "approve":
            result = application.approve(request.user.player_data)
            return {"action": "approved", "tenure_created": bool(result)}
        else:
            result = application.deny(request.user.player_data, review_notes)
            return {"action": "denied", "success": result}


# Example of how validation errors would be structured:
class RosterEntryListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing available roster entries to apply for.
    Automatically filters based on player permissions and eligibility.
    """

    character_name = serializers.CharField(source="character.db_key", read_only=True)
    character_id = serializers.IntegerField(source="character.id", read_only=True)
    roster_name = serializers.CharField(source="roster.name", read_only=True)
    roster_description = serializers.CharField(
        source="roster.description", read_only=True
    )
    is_available = serializers.SerializerMethodField()
    trust_evaluation = serializers.SerializerMethodField()

    class Meta:
        model = RosterEntry
        fields = [
            "id",
            "character_id",
            "character_name",
            "roster_name",
            "roster_description",
            "is_available",
            "trust_evaluation",
            "joined_roster",
        ]

    def get_is_available(self, obj):
        """Check if character is available for application."""
        # Character is available if no current tenure exists
        return not obj.character.roster_entry.tenures.filter(
            end_date__isnull=True
        ).exists()

    def get_trust_evaluation(self, obj):
        """Get trust evaluation for this player/character combination."""
        request = self.context.get("request")
        if not request or not hasattr(request.user, "player_data"):
            return None

        return TrustEvaluator.evaluate_player_for_character(
            request.user.player_data, obj.character
        )


class RosterListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing rosters with character counts.
    """

    available_count = serializers.SerializerMethodField()

    class Meta:
        model = Roster
        fields = ["id", "name", "description", "is_active", "available_count"]

    def get_available_count(self, obj):
        """Get count of available characters in this roster for the requesting player."""
        request = self.context.get("request")
        if not request or not hasattr(request.user, "player_data"):
            return 0

        # Filter roster entries for this roster and player permissions
        visible_entries = get_visible_roster_entries_for_player(
            request.user.player_data, obj.entries.all()
        )
        return visible_entries.count()


class RosterApplicationEligibilitySerializer(serializers.Serializer):
    """
    Check eligibility for a character application without creating one.
    Used for frontend validation and UI display.
    """

    character_id = serializers.IntegerField()

    def validate_character_id(self, value):
        """Validate character exists."""
        try:
            return ObjectDB.objects.get(pk=value)
        except ObjectDB.DoesNotExist:
            raise serializers.ValidationError(
                {"code": "character_not_found", "message": "Character not found"}
            )

    def validate(self, attrs):
        """Check full eligibility."""
        character = attrs["character_id"]
        request = self.context["request"]
        player_data = request.user.player_data

        # Use the same validation as application creation
        try:
            app_serializer = RosterApplicationCreateSerializer(context=self.context)
            app_serializer._validate_basic_eligibility(player_data, character)
            policy_issues = app_serializer._get_policy_issues(player_data, character)

            attrs["eligible"] = True
            attrs["policy_issues"] = policy_issues
            attrs["trust_evaluation"] = TrustEvaluator.evaluate_player_for_character(
                player_data, character
            )
        except serializers.ValidationError as e:
            attrs["eligible"] = False
            attrs["error"] = e.detail
            attrs["policy_issues"] = []
            attrs["trust_evaluation"] = None

        return attrs

    def to_representation(self, instance):
        """Return eligibility information."""
        return {
            "character_id": instance["character_id"].id,
            "character_name": instance["character_id"].db_key,
            "eligible": instance["eligible"],
            "error": instance.get("error"),
            "policy_issues": instance["policy_issues"],
            "trust_evaluation": instance["trust_evaluation"],
            "can_auto_approve": instance.get("trust_evaluation", {}).get(
                "auto_approvable", False
            ),
        }


# Example API Response Documentation:
"""
Example Roster Listing Response:
{
    "rosters": [
        {
            "id": 1,
            "name": "Active",
            "description": "Currently active characters",
            "is_active": true,
            "available_count": 5
        },
        {
            "id": 2,
            "name": "Available",
            "description": "Characters available for play",
            "is_active": true,
            "available_count": 12
        }
    ],
    "characters": [
        {
            "id": 101,
            "character_id": 301,
            "character_name": "Ariel",
            "roster_name": "Available",
            "roster_description": "Characters available for play",
            "is_available": true,
            "trust_evaluation": {
                "eligible": true,
                "trust_level": "basic",
                "requirements": [],
                "warnings": [],
                "auto_approvable": true
            }
        }
    ]
}

Example Eligibility Check Response:
{
    "character_id": 301,
    "character_name": "Ariel",
    "eligible": true,
    "error": null,
    "policy_issues": [],
    "trust_evaluation": {
        "eligible": true,
        "trust_level": "basic",
        "requirements": [],
        "warnings": [],
        "auto_approvable": true
    },
    "can_auto_approve": true
}
"""
