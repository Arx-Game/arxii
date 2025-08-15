"""Mail-related serializers for the roster system."""

from rest_framework import serializers

from world.roster.models import PlayerMail, RosterTenure


class PlayerMailSerializer(serializers.ModelSerializer):
    """Serialize player mail messages."""

    sender_account = serializers.CharField(
        source="sender_account.username", read_only=True
    )
    sender_character = serializers.CharField(
        source="sender_character.name", read_only=True, allow_null=True
    )
    recipient_tenure = serializers.PrimaryKeyRelatedField(
        queryset=RosterTenure.objects.all()
    )
    recipient_display = serializers.CharField(
        source="recipient_tenure.display_name", read_only=True
    )
    sender_tenure = serializers.SerializerMethodField()
    sender_display = serializers.SerializerMethodField()
    in_reply_to = serializers.PrimaryKeyRelatedField(
        queryset=PlayerMail.objects.all(), required=False, allow_null=True
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
            "sender_account",
            "sender_character",
            "sender_tenure",
            "sender_display",
        ]
        read_only_fields = [
            "sent_date",
            "read_date",
            "sender_account",
            "sender_character",
            "sender_tenure",
            "sender_display",
            "recipient_display",
        ]

    def get_sender_tenure(self, obj):
        """Return the sender's current roster tenure for their character."""
        if not obj.sender_character:
            return None
        tenure = RosterTenure.objects.filter(
            roster_entry__character=obj.sender_character, end_date__isnull=True
        ).first()
        return tenure.id if tenure else None

    def get_sender_display(self, obj):
        """Return display name for the sender's tenure if available."""
        if not obj.sender_character:
            return obj.sender_account.username
        tenure = RosterTenure.objects.filter(
            roster_entry__character=obj.sender_character, end_date__isnull=True
        ).first()
        return tenure.display_name if tenure else obj.sender_account.username
