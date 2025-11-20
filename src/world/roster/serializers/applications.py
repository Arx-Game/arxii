"""
Application-related serializers for the roster system.
"""

from evennia.objects.models import ObjectDB
from rest_framework import serializers

from world.roster.models import (
    ApplicationStatus,
    RosterApplication,
    ValidationErrorCodes,
    ValidationMessages,
)


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
                {"code": "character_not_found", "message": "Character not found"},
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
                },
            )

        # 2. Player cannot already be playing this character
        if character.roster_entry.tenures.filter(
            player_data=player_data,
            end_date__isnull=True,
        ).exists():
            raise serializers.ValidationError(
                {
                    "code": ValidationErrorCodes.ALREADY_PLAYING_CHARACTER,
                    "message": ValidationMessages.ALREADY_PLAYING_CHARACTER,
                },
            )

        # 3. Character must be accepting applications
        if not character.roster_entry.accepts_applications:
            if character.roster_entry.current_tenure:
                code = ValidationErrorCodes.CHARACTER_ALREADY_PLAYED
                message = ValidationMessages.CHARACTER_ALREADY_PLAYED
            else:
                code = ValidationErrorCodes.ROSTER_PERMISSION_DENIED
                message = ValidationMessages.ROSTER_PERMISSION_DENIED
            raise serializers.ValidationError({"code": code, "message": message})

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
                },
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
        source="player_data.account.username",
        read_only=True,
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
        max_length=1000,
        required=False,
        allow_blank=True,
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
                },
            )

        # Check application is still pending
        if application.status != ApplicationStatus.PENDING:
            raise serializers.ValidationError(
                {
                    "code": "invalid_status",
                    "message": f"Application is already {application.status}",
                },
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
        result = application.deny(request.user.player_data, review_notes)
        return {"action": "denied", "success": result}


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
                {"code": "character_not_found", "message": "Character not found"},
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
            # TODO: Implement trust evaluation when trust system is ready
            # attrs["trust_evaluation"] = TrustEvaluator.evaluate_player_for_character(
            #     player_data, character
            # )
            attrs["trust_evaluation"] = None
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
                "auto_approvable",
                False,
            ),
        }
