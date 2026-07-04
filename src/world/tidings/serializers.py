"""Serializers for the public-reaction tidings feed (#1450)."""

from rest_framework import serializers

from world.tidings.constants import FeedItemKind


class PublicFeedItemSerializer(serializers.Serializer):
    """One feed row — a deed or a scandal. Read-only; serializes a ``PublicFeedItem`` dataclass."""

    kind = serializers.ChoiceField(choices=FeedItemKind.choices)
    headline = serializers.CharField()
    subject = serializers.CharField()
    occurred_at = serializers.DateTimeField()
    # The authored scandal-category name ("Treacherous Scandal", #1806) when the
    # row's archetypes carry one — the player-legible type of the scandal.
    category = serializers.CharField(allow_null=True, required=False)
