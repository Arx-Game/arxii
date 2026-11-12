"""Read-only serializer for the missives API (#3289).

Privacy boundary: a row names the counterpart only as the reader knows them
(``world.messengers.display``) and carries no persona id, sheet, character or account of
the other side, and nothing that tells a sender a block suppressed the letter
(``undeliverable``, the recipient's ``read_at``).

Context: ``viewer_sheet`` (the reading character's sheet), ``attachments_by_missive``
(missive pk -> its attachments) and ``names`` (``display.display_map_for`` over the page),
both loaded once per page by the view.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.currency.constants import format_coppers
from world.game_clock.services import format_ic_date
from world.messengers.constants import AttachmentKind, MissiveDirection
from world.messengers.display import missive_correspondents
from world.messengers.models import Missive, MissiveAttachment
from world.messengers.services import sent_by

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.scenes.models import Persona


class MissiveAttachmentSerializer(serializers.Serializer):
    """One item or sum of coin riding on a missive."""

    id = serializers.IntegerField(read_only=True)
    kind = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()
    resolution = serializers.CharField(read_only=True)

    def get_kind(self, obj: MissiveAttachment) -> str:
        return AttachmentKind.COIN if obj.coin_amount else AttachmentKind.ITEM

    def get_label(self, obj: MissiveAttachment) -> str:
        if obj.coin_amount:
            return format_coppers(obj.coin_amount)
        return obj.item.display_name


class MissiveSerializer(serializers.ModelSerializer):
    """One missive as the reading character sees it."""

    direction = serializers.SerializerMethodField()
    counterpart_name = serializers.SerializerMethodField()
    own_persona_id = serializers.SerializerMethodField()
    own_persona_name = serializers.SerializerMethodField()
    method_name = serializers.CharField(source="method.name", read_only=True)
    ic_date = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()
    in_reply_to = serializers.IntegerField(source="in_reply_to_id", read_only=True)
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = Missive
        fields = [
            "id",
            "direction",
            "counterpart_name",
            "own_persona_id",
            "own_persona_name",
            "method_name",
            "body",
            "ic_date",
            "sent_at",
            "is_read",
            "in_reply_to",
            "attachments",
        ]
        read_only_fields = fields

    @property
    def _viewer_sheet(self) -> CharacterSheet:
        return self.context["viewer_sheet"]

    def _is_sent(self, obj: Missive) -> bool:
        return sent_by(self._viewer_sheet, obj)

    def _own_persona(self, obj: Missive) -> Persona:
        return obj.sender_persona if self._is_sent(obj) else obj.recipient_persona

    def get_direction(self, obj: Missive) -> str:
        return MissiveDirection.SENT if self._is_sent(obj) else MissiveDirection.RECEIVED

    def get_counterpart_name(self, obj: Missive) -> str:
        from_name, to_name = missive_correspondents(
            self._viewer_sheet, obj, self.context.get("names")
        )
        return to_name if self._is_sent(obj) else from_name

    def get_own_persona_id(self, obj: Missive) -> int:
        return self._own_persona(obj).pk

    def get_own_persona_name(self, obj: Missive) -> str:
        return self._own_persona(obj).name

    def get_ic_date(self, obj: Missive) -> str:
        return format_ic_date(obj.ic_sent_at) if obj.ic_sent_at is not None else ""

    def get_is_read(self, obj: Missive) -> bool:
        # A sender never learns whether the letter was read (or delivered at all).
        return True if self._is_sent(obj) else obj.read_at is not None

    @extend_schema_field(MissiveAttachmentSerializer(many=True))
    def get_attachments(self, obj: Missive) -> list[dict[str, Any]]:
        by_missive: dict[int, list[MissiveAttachment]] = self.context["attachments_by_missive"]
        return MissiveAttachmentSerializer(by_missive.get(obj.pk, []), many=True).data
