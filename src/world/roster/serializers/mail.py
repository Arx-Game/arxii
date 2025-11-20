"""Mail-related serializers for the roster system."""

from rest_framework import serializers

from world.roster.models import PlayerMail, RosterTenure


class PlayerMailSerializer(serializers.ModelSerializer):
    """Serialize player mail messages."""

    recipient_tenure = serializers.PrimaryKeyRelatedField(
        queryset=RosterTenure.objects.all(),
    )
    recipient_display = serializers.CharField(
        source="recipient_tenure.display_name",
        read_only=True,
    )
    sender_tenure = serializers.PrimaryKeyRelatedField(
        queryset=RosterTenure.objects.all(),
    )
    sender_display = serializers.CharField(
        source="sender_tenure.display_name",
        read_only=True,
    )
    in_reply_to = serializers.PrimaryKeyRelatedField(
        queryset=PlayerMail.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = PlayerMail
        fields = [
            "id",
            "recipient_tenure",
            "recipient_display",
            "subject",
            "message",
            "in_reply_to",
            "sent_date",
            "read_date",
            "sender_tenure",
            "sender_display",
        ]
        read_only_fields = [
            "sent_date",
            "read_date",
            "sender_display",
            "recipient_display",
        ]
