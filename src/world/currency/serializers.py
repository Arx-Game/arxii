"""DRF serializers for the currency player API (#1446)."""

from __future__ import annotations

from rest_framework import serializers

from world.currency.models import CharacterPurse
from world.items.org_vault_models import OrgVaultEvent


class CharacterPurseSerializer(serializers.ModelSerializer):
    """The viewer's own coin purse — a single coppers balance (the client formats g/s/c)."""

    class Meta:
        model = CharacterPurse
        fields = ["balance"]


class OrgVaultEventSerializer(serializers.ModelSerializer):
    """One append-only item-vault audit row (#2540) — the ``LedgerRowSerializer`` analogue
    for the item vault. Read-only; how embezzlement gets discovered later.

    ``item_instance`` and ``actor_persona`` are SET_NULL on delete, so both display
    fields fall back to None rather than raising — a deleted item or persona still
    leaves a legible (if anonymized) audit row.
    """

    item_name = serializers.SerializerMethodField()
    actor_persona_name = serializers.SerializerMethodField()

    class Meta:
        model = OrgVaultEvent
        fields = ["id", "kind", "item_name", "actor_persona_name", "created_at"]
        read_only_fields = fields

    def get_item_name(self, obj: OrgVaultEvent) -> str | None:
        return obj.item_instance.display_name if obj.item_instance_id else None

    def get_actor_persona_name(self, obj: OrgVaultEvent) -> str | None:
        return obj.actor_persona.name if obj.actor_persona_id else None
