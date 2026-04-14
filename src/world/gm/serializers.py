"""Serializers for the GM system."""

from __future__ import annotations

from rest_framework import serializers

from world.gm.constants import GMApplicationStatus
from world.gm.models import (
    GMApplication,
    GMProfile,
    GMRosterInvite,
    GMTable,
    GMTableMembership,
)
from world.roster.models.applications import RosterApplication


class GMApplicationCreateSerializer(serializers.ModelSerializer):
    """For players submitting a GM application."""

    application_text = serializers.CharField(
        min_length=50,
        max_length=10000,
        allow_blank=False,
    )

    class Meta:
        model = GMApplication
        fields = ["application_text"]

    def validate(self, attrs: dict) -> dict:
        account = self.context["request"].user
        if GMProfile.objects.filter(account=account).exists():
            msg = "This account is already an approved GM."
            raise serializers.ValidationError(msg)
        if GMApplication.objects.filter(
            account=account,
            status=GMApplicationStatus.PENDING,
        ).exists():
            msg = "You already have a pending GM application."
            raise serializers.ValidationError(msg)
        return attrs

    def create(self, validated_data: dict) -> GMApplication:
        validated_data["account"] = self.context["request"].user
        return super().create(validated_data)


class GMApplicationDetailSerializer(serializers.ModelSerializer):
    """For staff reviewing GM applications."""

    account_username = serializers.CharField(source="account.username", read_only=True)
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = GMApplication
        fields = [
            "id",
            "account",
            "account_username",
            "application_text",
            "staff_response",
            "status",
            "created_at",
            "updated_at",
            "reviewed_by",
            "reviewed_by_username",
        ]
        read_only_fields = ["id", "account", "created_at", "updated_at", "reviewed_by"]


class GMProfileSerializer(serializers.ModelSerializer):
    """Read-only serializer for GM profiles."""

    account_username = serializers.CharField(source="account.username", read_only=True)

    class Meta:
        model = GMProfile
        fields = [
            "id",
            "account",
            "account_username",
            "level",
            "approved_at",
        ]
        read_only_fields = fields


class GMTableSerializer(serializers.ModelSerializer):
    """Serializer for GM tables."""

    gm_username = serializers.CharField(source="gm.account.username", read_only=True)

    class Meta:
        model = GMTable
        fields = [
            "id",
            "gm",
            "gm_username",
            "name",
            "description",
            "status",
            "created_at",
            "archived_at",
        ]
        read_only_fields = ["id", "gm_username", "created_at", "archived_at", "status"]


class GMTableMembershipSerializer(serializers.ModelSerializer):
    """Serializer for persona memberships at GM tables."""

    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = GMTableMembership
        fields = ["id", "table", "persona", "persona_name", "joined_at", "left_at"]
        read_only_fields = ["id", "persona_name", "joined_at", "left_at"]


class GMRosterInviteSerializer(serializers.ModelSerializer):
    """For GM create/list operations on invites for their own characters."""

    claimed_username = serializers.CharField(
        source="claimed_by.username",
        read_only=True,
        allow_null=True,
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    invited_email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = GMRosterInvite
        fields = [
            "id",
            "roster_entry",
            "code",
            "created_by",
            "created_at",
            "expires_at",
            "is_public",
            "invited_email",
            "claimed_at",
            "claimed_by",
            "claimed_username",
        ]
        read_only_fields = [
            "id",
            "code",
            "created_by",
            "created_at",
            "claimed_at",
            "claimed_by",
            "claimed_username",
        ]

    def validate(self, attrs: dict) -> dict:
        """GM must oversee the roster_entry's character at an active table."""
        from world.gm.constants import GMTableStatus  # noqa: PLC0415
        from world.roster.models import RosterEntry  # noqa: PLC0415

        request = self.context.get("request")
        if request is None or not hasattr(request.user, "gm_profile"):
            msg = "GM profile required."
            raise serializers.ValidationError(msg)

        gm = request.user.gm_profile
        roster_entry = attrs["roster_entry"]
        oversees = RosterEntry.objects.filter(
            pk=roster_entry.pk,
            character_sheet__character__story_participations__is_active=True,
            character_sheet__character__story_participations__story__primary_table__gm=gm,
            character_sheet__character__story_participations__story__primary_table__status=(
                GMTableStatus.ACTIVE
            ),
        ).exists()
        if not oversees:
            raise serializers.ValidationError(
                {"roster_entry": "You do not oversee this character."},
            )
        return attrs

    def create(self, validated_data: dict) -> GMRosterInvite:
        """Delegate to the service. Validation already ran in ``validate()``."""
        from world.gm.services import create_invite  # noqa: PLC0415

        request = self.context["request"]
        return create_invite(
            gm=request.user.gm_profile,
            roster_entry=validated_data["roster_entry"],
            is_public=validated_data.get("is_public", False),
            invited_email=validated_data.get("invited_email", "").strip(),
            expires_at=validated_data.get("expires_at"),
        )


class GMInviteRevokeSerializer(serializers.Serializer):
    """Validate that the current GM (or staff) can revoke this invite."""

    def validate(self, attrs: dict) -> dict:
        invite = self.instance
        if invite.is_claimed:
            msg = "Claimed invites cannot be revoked."
            raise serializers.ValidationError(msg)
        request = self.context["request"]
        if request.user.is_staff:
            return attrs
        if invite.created_by.account != request.user:
            msg = "You did not create this invite."
            raise serializers.ValidationError(msg)
        return attrs

    def save(self, **kwargs: object) -> GMRosterInvite:  # noqa: ARG002
        from world.gm.services import revoke_invite  # noqa: PLC0415

        revoke_invite(self.instance)
        return self.instance


class GMInviteClaimSerializer(serializers.Serializer):
    """Claim a GM invite by code."""

    code = serializers.CharField(max_length=64)

    def validate_code(self, value: str) -> str:
        try:
            invite = GMRosterInvite.objects.select_for_update().get(code=value)
        except GMRosterInvite.DoesNotExist as exc:
            msg = "Invalid invite code."
            raise serializers.ValidationError(msg) from exc
        if invite.is_claimed:
            msg = "This invite has already been claimed."
            raise serializers.ValidationError(msg)
        if invite.is_expired:
            msg = "This invite has expired."
            raise serializers.ValidationError(msg)
        self.context["invite"] = invite
        return value

    def validate(self, attrs: dict) -> dict:
        from evennia_extensions.models import PlayerData  # noqa: PLC0415
        from world.roster.models.choices import ApplicationStatus  # noqa: PLC0415

        invite = self.context["invite"]
        request = self.context["request"]
        account = request.user
        if not invite.is_public and invite.invited_email:
            invited = invite.invited_email.strip().lower()
            account_email = (account.email or "").strip().lower()
            if not account_email or invited != account_email:
                msg = "This invite is private and does not match your account email."
                raise serializers.ValidationError(msg)

        # Reject if a finalized (non-pending) application already exists for
        # this (player_data, character). The service will reuse a PENDING one.
        try:
            player_data = PlayerData.objects.get(account=account)
        except PlayerData.DoesNotExist:
            player_data = None
        if player_data is not None:
            character = invite.roster_entry.character_sheet.character
            existing = RosterApplication.objects.filter(
                player_data=player_data,
                character=character,
            ).first()
            if existing is not None and existing.status != ApplicationStatus.PENDING:
                msg = (
                    "You already have a finalized application for this character. "
                    "Contact staff if you want to re-apply."
                )
                raise serializers.ValidationError(msg)
        return attrs

    def save(self, **kwargs: object) -> RosterApplication:  # noqa: ARG002
        from world.gm.services import claim_invite  # noqa: PLC0415

        invite: GMRosterInvite = self.context["invite"]
        account = self.context["request"].user
        return claim_invite(invite=invite, account=account)


class GMApplicationActionSerializer(serializers.Serializer):
    """Validate that the current GM can approve/deny the application."""

    APPROVE = "approve"
    DENY = "deny"

    action = serializers.ChoiceField(choices=[APPROVE, DENY])
    review_notes = serializers.CharField(required=False, default="", allow_blank=True)

    def validate(self, attrs: dict) -> dict:
        from world.gm.services import gm_application_queue  # noqa: PLC0415
        from world.roster.models.choices import ApplicationStatus  # noqa: PLC0415

        request = self.context["request"]
        application: RosterApplication = self.context["application"]
        gm = request.user.gm_profile

        if not gm_application_queue(gm).filter(pk=application.pk).exists():
            msg = "This application is not in your GM application queue."
            raise serializers.ValidationError(msg)

        # Bypass SMM identity map via values_list and acquire row lock.
        locked_status = (
            RosterApplication.objects.select_for_update()
            .filter(pk=application.pk)
            .values_list("status", flat=True)
            .first()
        )
        if locked_status != ApplicationStatus.PENDING:
            msg = "This application has already been processed."
            raise serializers.ValidationError(msg)
        application.refresh_from_db(fields=["status"])
        return attrs

    def save(self, **kwargs: object) -> RosterApplication:  # noqa: ARG002
        from world.gm.services import (  # noqa: PLC0415
            approve_application_as_gm,
            deny_application_as_gm,
        )

        application: RosterApplication = self.context["application"]
        gm = self.context["request"].user.gm_profile
        action = self.validated_data["action"]
        notes = self.validated_data.get("review_notes", "")

        if action == self.APPROVE:
            approve_application_as_gm(gm, application)
        else:
            deny_application_as_gm(gm, application, review_notes=notes)
        return application


class GMApplicationQueueSerializer(serializers.ModelSerializer):
    """Pending application surfaced to the overseeing GM."""

    character_key = serializers.CharField(source="character.db_key", read_only=True)
    applicant_username = serializers.CharField(
        source="player_data.account.username",
        read_only=True,
    )

    class Meta:
        model = RosterApplication
        fields = [
            "id",
            "character",
            "character_key",
            "applicant_username",
            "status",
            "applied_date",
            "application_text",
        ]
        read_only_fields = fields
