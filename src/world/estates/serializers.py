"""DRF serializers for estates (#1985).

Validation mirrors ``Bequest.clean()`` — DRF never calls model ``clean()`` on
save, so the kind/target coherence rules live in both places deliberately.
Will edits freeze once a settlement window exists (``services.will_is_frozen``).
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from world.estates.constants import BequestKind
from world.estates.models import Bequest, EstateClaim, EstateSettlement, Will, WillExecutor
from world.estates.services import will_is_frozen

# Extracted to satisfy S1192.
_WILL_SEALED_MSG = "That will is sealed; its estate is being settled."


class WillExecutorSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = WillExecutor
        fields = ["id", "will", "persona", "persona_name"]

    def validate(self, attrs: dict) -> dict:
        will = attrs.get("will") or (self.instance.will if self.instance else None)
        if will is not None and will_is_frozen(will.character_sheet):
            raise serializers.ValidationError(_WILL_SEALED_MSG)
        return attrs


class BequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bequest
        fields = [
            "id",
            "will",
            "order",
            "kind",
            "item",
            "building",
            "business",
            "amount",
            "recipient_persona",
            "recipient_organization",
        ]

    _KIND_TARGET_FIELD = {
        BequestKind.SPECIFIC_ITEM: "item",
        BequestKind.BUILDING: "building",
        BequestKind.BUSINESS: "business",
    }
    _PERSONA_ONLY_KINDS = frozenset(
        {BequestKind.SPECIFIC_ITEM, BequestKind.BUSINESS, BequestKind.WRITINGS}
    )

    def validate(self, attrs: dict) -> dict:
        """Validate will is not frozen, then delegate to coherence helpers."""
        will = self._value(attrs, "will")
        if will is not None and will_is_frozen(will.character_sheet):
            raise serializers.ValidationError(_WILL_SEALED_MSG)
        self._validate_kind_target_coherence(attrs, will)
        return attrs

    def _value(self, attrs: dict, field: str) -> Any:
        """Read ``field`` from incoming attrs, falling back to the instance."""
        if field in attrs:
            return attrs[field]
        return getattr(self.instance, field) if self.instance else None

    def _validate_kind_target_coherence(self, attrs: dict, will: Any) -> None:
        """Enforce kind/target, amount, recipient, and ownership rules."""
        kind = self._value(attrs, "kind")
        target_field = self._KIND_TARGET_FIELD.get(kind)
        self._validate_target_fields(attrs, kind, target_field)
        self._validate_amount(kind, attrs)
        self._validate_recipient(kind, attrs, will)

    def _validate_target_fields(self, attrs: dict, kind: Any, target_field: str | None) -> None:
        """Each kind requires its target field set and all others unset."""
        for field in ("item", "building", "business"):
            value = self._value(attrs, field)
            if field == target_field and value is None:
                raise serializers.ValidationError({field: f"A {kind} bequest requires {field}."})
            if field != target_field and value is not None:
                raise serializers.ValidationError({field: f"A {kind} bequest may not set {field}."})

    def _validate_amount(self, kind: Any, attrs: dict) -> None:
        """Coin bequests require a positive amount; others carry none."""
        amount = self._value(attrs, "amount") or 0
        if kind == BequestKind.COIN_AMOUNT and amount == 0:
            raise serializers.ValidationError({"amount": "A coin bequest requires an amount."})
        if kind != BequestKind.COIN_AMOUNT and amount != 0:
            raise serializers.ValidationError({"amount": f"A {kind} bequest carries no amount."})

    def _validate_recipient(self, kind: Any, attrs: dict, will: Any) -> None:
        """Enforce exactly-one-recipient, persona-only kinds, and item ownership."""
        persona = self._value(attrs, "recipient_persona")
        org = self._value(attrs, "recipient_organization")
        if (persona is None) == (org is None):
            raise serializers.ValidationError("Exactly one recipient (character or organization).")  # noqa: EM101, TRY003
        if kind in self._PERSONA_ONLY_KINDS and org is not None:
            raise serializers.ValidationError(
                {"recipient_organization": f"A {kind} bequest needs a character recipient."}
            )
        if kind == BequestKind.SPECIFIC_ITEM:
            item = self._value(attrs, "item")
            if item is not None and item.holder_character_sheet_id != will.character_sheet_id:
                raise serializers.ValidationError({"item": "You can only bequeath what you own."})


class WillSerializer(serializers.ModelSerializer):
    bequests = BequestSerializer(many=True, read_only=True)
    executors = WillExecutorSerializer(many=True, read_only=True)
    is_frozen = serializers.SerializerMethodField()

    class Meta:
        model = Will
        fields = [
            "id",
            "character_sheet",
            "testament_text",
            "updated_at",
            "bequests",
            "executors",
            "is_frozen",
        ]
        read_only_fields = ["updated_at"]

    def get_is_frozen(self, obj: Any) -> bool:
        return will_is_frozen(obj.character_sheet)

    def validate(self, attrs: dict) -> dict:
        sheet = attrs.get("character_sheet") or (
            self.instance.character_sheet if self.instance else None
        )
        if sheet is not None and will_is_frozen(sheet):
            raise serializers.ValidationError(_WILL_SEALED_MSG)
        return attrs


class EstateClaimSerializer(serializers.ModelSerializer):
    item_name = serializers.SerializerMethodField()

    class Meta:
        model = EstateClaim
        fields = ["id", "settlement", "item", "item_name", "created_at"]

    def get_item_name(self, obj: Any) -> str:
        game_object = obj.item.game_object
        return game_object.db_key if game_object is not None else "a lost possession"


class EstateSettlementSerializer(serializers.ModelSerializer):
    deceased_name = serializers.SerializerMethodField()

    class Meta:
        model = EstateSettlement
        fields = [
            "id",
            "character_sheet",
            "deceased_name",
            "opened_at",
            "deadline",
            "status",
            "settled_via",
            "settled_at",
        ]

    def get_deceased_name(self, obj: Any) -> str:
        return str(obj.character_sheet)
