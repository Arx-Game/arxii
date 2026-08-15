"""Trade read serializers (#2990): the negotiation panel's payload.

Read-only — every mutation goes through the trade actions, never REST writes
(same convention as ``world.items.market.serializers``).
"""

from rest_framework import serializers

from world.items.trade.models import TradeItemStake, TradeSession


class TradeItemStakeSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item_instance.display_name", read_only=True)
    offered_by_name = serializers.CharField(source="offered_by_sheet.character.key", read_only=True)

    class Meta:
        model = TradeItemStake
        fields = [
            "id",
            "item_instance",
            "item_name",
            "offered_by_sheet",
            "offered_by_name",
            "staked_at",
        ]
        read_only_fields = fields


class TradeSessionSerializer(serializers.ModelSerializer):
    initiator_name = serializers.CharField(source="initiator_sheet.character.key", read_only=True)
    counterparty_name = serializers.CharField(
        source="counterparty_sheet.character.key", read_only=True
    )
    item_stakes = TradeItemStakeSerializer(many=True, read_only=True)

    class Meta:
        model = TradeSession
        fields = [
            "id",
            "initiator_sheet",
            "initiator_name",
            "counterparty_sheet",
            "counterparty_name",
            "status",
            "initiator_confirmed",
            "counterparty_confirmed",
            "initiator_coppers",
            "counterparty_coppers",
            "item_stakes",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = fields
