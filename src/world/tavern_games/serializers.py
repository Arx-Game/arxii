"""Serializers for the tavern games API (#3292)."""

from __future__ import annotations

from rest_framework import serializers

from world.tavern_games.models import GameSeat, GameSession, TavernGame


class TavernGameSerializer(serializers.ModelSerializer):
    class Meta:
        model = TavernGame
        fields = [
            "id",
            "name",
            "rules_blurb",
            "min_ante",
            "max_ante",
            "resolution_kind",
            "is_active",
        ]
        read_only_fields = fields


class GameSeatSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = GameSeat
        fields = ["id", "persona", "persona_name", "ante_paid", "roll_result", "seated_at"]
        read_only_fields = fields


class GameSessionSerializer(serializers.ModelSerializer):
    game_name = serializers.CharField(source="game.name", read_only=True)
    place_name = serializers.CharField(source="place.name", read_only=True)
    seats = serializers.SerializerMethodField()

    def get_seats(self, obj: GameSession) -> list[dict]:
        """Read the ``Prefetch(..., to_attr="cached_seats")`` list.

        Every ``GameSession`` this serializer runs against comes from a
        queryset built with ``world.tavern_games.views._seats_prefetch()``
        (the viewset's own ``queryset``, or ``_fetch_session_with_seats``
        after a write) - so ``cached_seats`` is always present as a real
        instance attribute, never a literal-string ``getattr`` fallback.
        """
        return GameSeatSerializer(obj.cached_seats, many=True).data

    class Meta:
        model = GameSession
        fields = [
            "id",
            "place",
            "place_name",
            "game",
            "game_name",
            "state",
            "ante",
            "pot",
            "opened_by",
            "opened_at",
            "resolved_at",
            "seats",
        ]
        read_only_fields = fields
