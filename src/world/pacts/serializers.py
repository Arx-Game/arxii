"""Serializers for being pacts (#4341)."""

from rest_framework import serializers


class PactCommitmentLineSerializer(serializers.Serializer):
    """One commitment of an offer: FAVOR_EARNED (``amount`` per period) or CUSTOM (a
    promise in ``notes``, never checked)."""

    kind = serializers.CharField()
    amount = serializers.IntegerField()
    notes = serializers.CharField(allow_blank=True)


class PactStageLineSerializer(serializers.Serializer):
    """One stage of a pact's condition, best to worst, with the stage's own effects;
    ``is_last`` marks the stage whose arrival ends the pact."""

    name = serializers.CharField()
    threshold = serializers.IntegerField()
    effects = serializers.ListField(child=serializers.CharField())
    is_last = serializers.BooleanField()


class PactOfferSummarySerializer(serializers.Serializer):
    """The pact a pledge offers at its close, built from the offer's rows.
    ``condition_effects`` apply at every stage."""

    being_name = serializers.CharField()
    offer_name = serializers.CharField()
    offer_text = serializers.CharField()
    period_weeks = serializers.IntegerField()
    commitments = PactCommitmentLineSerializer(many=True)
    promises = serializers.ListField(child=serializers.CharField())
    condition_effects = serializers.ListField(child=serializers.CharField())
    stages = PactStageLineSerializer(many=True)
