"""Serializers for the public-reaction news feed (#1450)."""

from rest_framework import serializers

from world.news.constants import FeedItemKind


class PublicFeedItemSerializer(serializers.Serializer):
    """One feed row — a deed or a scandal. Read-only; serializes a ``PublicFeedItem`` dataclass."""

    kind = serializers.ChoiceField(choices=FeedItemKind.choices)
    headline = serializers.CharField()
    subject = serializers.CharField()
    occurred_at = serializers.DateTimeField()
