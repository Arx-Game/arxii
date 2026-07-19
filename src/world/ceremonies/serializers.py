"""Serializers for the ceremonies API (#2289).

LEAK RULE (spec Decision 2/10): player-facing payloads carry
``presented_being`` ONLY — the true ``being`` is never serialized, so a
twisted rite's hidden recipient cannot leak through the API.
"""

from rest_framework import serializers

from world.ceremonies.models import (
    Ceremony,
    CeremonyHonoree,
    CeremonySpeech,
    SeanceManifestationOffer,
)


class CeremonyHonoreeSerializer(serializers.ModelSerializer):
    honoree_name = serializers.CharField(source="honoree_sheet.character.db_key", read_only=True)

    class Meta:
        model = CeremonyHonoree
        fields = ["id", "honoree_name", "prestige_awarded"]


class CeremonySpeechSerializer(serializers.ModelSerializer):
    speaker_name = serializers.CharField(source="speaker.name", read_only=True)

    class Meta:
        model = CeremonySpeech
        fields = ["id", "speaker_name", "success_level"]


class CeremonySerializer(serializers.ModelSerializer):
    ceremony_type_name = serializers.CharField(source="ceremony_type.name", read_only=True)
    ceremony_type_key = serializers.CharField(source="ceremony_type.key", read_only=True)
    officiant_name = serializers.CharField(source="officiant.name", read_only=True)
    presented_being_name = serializers.CharField(source="presented_being.name", read_only=True)
    honorees = CeremonyHonoreeSerializer(many=True, read_only=True)
    speeches = CeremonySpeechSerializer(many=True, read_only=True)
    offering_count = serializers.IntegerField(source="offerings.count", read_only=True)

    class Meta:
        model = Ceremony
        # NEVER add "being" here — presented_being is the only exposed recipient.
        fields = [
            "id",
            "ceremony_type_name",
            "ceremony_type_key",
            "officiant_name",
            "presented_being_name",
            "location",
            "status",
            "opened_at",
            "finished_at",
            "honorees",
            "speeches",
            "offering_count",
        ]


class SeanceManifestationOfferSerializer(serializers.ModelSerializer):
    honoree_name = serializers.CharField(
        source="ceremony_honoree.honoree_sheet.character.db_key", read_only=True
    )
    ceremony_location_name = serializers.CharField(
        source="ceremony_honoree.ceremony.location.objectdb.db_key", read_only=True
    )
    ceremony_id = serializers.IntegerField(source="ceremony_honoree.ceremony_id", read_only=True)

    class Meta:
        model = SeanceManifestationOffer
        fields = [
            "id",
            "honoree_name",
            "ceremony_location_name",
            "ceremony_id",
            "status",
            "created_at",
        ]
