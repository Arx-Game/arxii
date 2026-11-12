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


class PactSourceLineSerializer(serializers.Serializer):
    """Favor credited toward the open period from one kind of source."""

    label = serializers.CharField()
    favor = serializers.IntegerField()


class PactCardSerializer(serializers.Serializer):
    """A character's pact as her card shows it. Read by her own player and staff only:
    a pact with a secret faith is hers alone.

    ``earned``/``required``/``time_limit`` describe the open period; after the pact
    ended (``is_active`` false) that is an ease-out period, whose condition eases by
    ``severity_per_miss`` when it ends."""

    id = serializers.IntegerField(source="pact.pk")
    character_sheet = serializers.IntegerField(source="pact.character_sheet_id")
    being_id = serializers.IntegerField(source="pact.offer.being_id")
    being_name = serializers.CharField()
    offer_name = serializers.CharField()
    period_weeks = serializers.IntegerField()
    severity_per_miss = serializers.IntegerField(source="pact.offer.severity_per_miss")
    earned = serializers.IntegerField()
    required = serializers.IntegerField()
    time_limit = serializers.DateTimeField(allow_null=True)
    sources = PactSourceLineSerializer(many=True)
    stage_name = serializers.CharField(allow_blank=True)
    severity = serializers.IntegerField()
    next_stage_threshold = serializers.IntegerField(allow_null=True)
    promises = serializers.ListField(child=serializers.CharField())
    condition_effects = serializers.ListField(child=serializers.CharField())
    stages = PactStageLineSerializer(many=True)
    is_active = serializers.BooleanField()
    dissolution_reason = serializers.CharField(allow_blank=True)
