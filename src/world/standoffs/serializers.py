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
    revealed_faction_rules = serializers.ListField(child=serializers.CharField())
    read_check = serializers.CharField()
    read_grade = serializers.CharField()
    read_grade_label = serializers.CharField()
    morale_state = serializers.CharField()
    terms_morale_ease = serializers.IntegerField()


class LeverViewSerializer(serializers.Serializer):
    text = serializers.CharField()
    is_angle = serializers.BooleanField()


class ApproachViewSerializer(serializers.Serializer):
    approach_id = serializers.IntegerField()
    group_id = serializers.IntegerField()
    name = serializers.CharField()
    grade = serializers.CharField()
    grade_label = serializers.CharField()
    check_caption = serializers.CharField()
    levers = LeverViewSerializer(many=True)
    hits_revealed_drive = serializers.BooleanField()
    casts_technique = serializers.BooleanField()


class AngleViewSerializer(serializers.Serializer):
    group_id = serializers.IntegerField()
    faction_rule_id = serializers.IntegerField()
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


class DisplayTechniqueSerializer(serializers.Serializer):
    technique_id = serializers.IntegerField()
    name = serializers.CharField()


class StandoffViewSerializer(serializers.Serializer):
    place = serializers.CharField(allow_blank=True)
    groups = GroupViewSerializer(many=True)
    approaches = ApproachViewSerializer(many=True)
    terms = TermsViewSerializer(many=True)
    angles = AngleViewSerializer(many=True)
    shared_angles = AngleViewSerializer(many=True)
    display_techniques = DisplayTechniqueSerializer(many=True)
