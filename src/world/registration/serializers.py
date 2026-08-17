"""Serializers for invitation-gated account registration (#3054)."""

from rest_framework import serializers

from world.registration.models import AccountInvite


class AccountInviteSerializer(serializers.ModelSerializer):
    """Read shape for the staff invite list/detail — never returned on failure paths."""

    status = serializers.CharField(read_only=True)
    invited_by_username = serializers.CharField(source="invited_by.username", read_only=True)
    redeemed_by_username = serializers.CharField(
        source="redeemed_by.username", read_only=True, default=None
    )

    class Meta:
        model = AccountInvite
        fields = [
            "id",
            "email",
            "token",
            "status",
            "note",
            "created_at",
            "expires_at",
            "redeemed_at",
            "revoked_at",
            "invited_by",
            "invited_by_username",
            "redeemed_by",
            "redeemed_by_username",
        ]
        read_only_fields = [
            "id",
            "token",
            "status",
            "created_at",
            "redeemed_at",
            "revoked_at",
            "invited_by",
            "redeemed_by",
        ]


class VerificationLinkRequestSerializer(serializers.Serializer):
    """Input for the staff verification-link endpoint (#3193) — write-only."""

    email = serializers.EmailField()

    def create(self, validated_data):
        msg = "VerificationLinkRequestSerializer never persists — the view builds the link."
        raise NotImplementedError(msg)

    def update(self, instance, validated_data):
        msg = "VerificationLinkRequestSerializer never persists — the view builds the link."
        raise NotImplementedError(msg)


class IssueInviteSerializer(serializers.Serializer):
    """Input for issuing a new invite — write-only, not model-backed."""

    email = serializers.EmailField()
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def create(self, validated_data):
        msg = "IssueInviteSerializer never persists directly — the view calls issue_invite()."
        raise NotImplementedError(msg)

    def update(self, instance, validated_data):
        msg = "IssueInviteSerializer never persists directly — the view calls issue_invite()."
        raise NotImplementedError(msg)
