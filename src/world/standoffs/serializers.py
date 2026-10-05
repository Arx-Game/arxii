"""Serializers for the per-viewer standoff payload (see ``services/view.py``)."""

from rest_framework import serializers


class DriveViewSerializer(serializers.Serializer):
    label = serializers.CharField()
    strength = serializers.CharField()


class GroupViewSerializer(serializers.Serializer):
    group_id = serializers.IntegerField()
    name = serializers.CharField()
    member_count = serializers.IntegerField()
    state = serializers.CharField()
    terms_ease = serializers.IntegerField()
    cause = serializers.CharField(allow_null=True)
    cause_gloss = serializers.CharField(allow_null=True)
    hidden_count = serializers.IntegerField()
    drives = DriveViewSerializer(many=True)
    revealed_regard = serializers.ListField(child=serializers.CharField())
    read_check = serializers.CharField()
    read_grade = serializers.CharField()
    read_grade_label = serializers.CharField()


class LeverViewSerializer(serializers.Serializer):
    text = serializers.CharField()
    is_spark = serializers.BooleanField()


class ApproachViewSerializer(serializers.Serializer):
    approach_id = serializers.IntegerField()
    group_id = serializers.IntegerField()
    name = serializers.CharField()
    grade = serializers.CharField()
    grade_label = serializers.CharField()
    check_caption = serializers.CharField()
    levers = LeverViewSerializer(many=True)
    hits_revealed_drive = serializers.BooleanField()


class SparkViewSerializer(serializers.Serializer):
    group_id = serializers.IntegerField()
    regard_rule_id = serializers.IntegerField()
    text = serializers.CharField()
    shared = serializers.BooleanField()


class TermsViewSerializer(serializers.Serializer):
    terms_id = serializers.IntegerField()
    name = serializers.CharField()
    group_id = serializers.IntegerField()
    description = serializers.CharField(allow_blank=True)
    grade = serializers.CharField()
    grade_label = serializers.CharField()
    critical_label = serializers.CharField(allow_blank=True)


class StandoffViewSerializer(serializers.Serializer):
    place = serializers.CharField(allow_blank=True)
    groups = GroupViewSerializer(many=True)
    approaches = ApproachViewSerializer(many=True)
    terms = TermsViewSerializer(many=True)
    sparks = SparkViewSerializer(many=True)
    shared_sparks = SparkViewSerializer(many=True)
