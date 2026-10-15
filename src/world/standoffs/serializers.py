"""Serializers for the per-viewer standoff payload (see ``services/view.py``)."""

from rest_framework import serializers

from world.standoffs.constants import MoraleDirection


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
    emboldened = serializers.BooleanField()


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


class GMDriveViewSerializer(serializers.Serializer):
    label = serializers.CharField()
    strength = serializers.CharField()
    revealed = serializers.BooleanField()
    edited = serializers.BooleanField()


class GMFactionRuleViewSerializer(serializers.Serializer):
    faction_rule_id = serializers.IntegerField()
    label = serializers.CharField()
    angle_text = serializers.CharField(allow_blank=True)
    difficulty_shift_bands = serializers.IntegerField()
    suppresses_cause = serializers.BooleanField()
    matched_by = serializers.ListField(child=serializers.CharField())
    revealed = serializers.BooleanField()
    source = serializers.CharField(allow_blank=True)


class GMMemberViewSerializer(serializers.Serializer):
    opponent_id = serializers.IntegerField()
    name = serializers.CharField()
    morale = serializers.IntegerField()
    morale_state = serializers.CharField()


class GMGroupViewSerializer(serializers.Serializer):
    group_id = serializers.IntegerField()
    name = serializers.CharField()
    state = serializers.CharField()
    member_count = serializers.IntegerField()
    cause = serializers.CharField()
    cause_revealed = serializers.BooleanField()
    cause_fires = serializers.BooleanField()
    cause_reason = serializers.CharField(allow_blank=True)
    cause_margin_percent = serializers.IntegerField()
    proposal_reason = serializers.CharField(allow_blank=True)
    pending_prompt_id = serializers.IntegerField(allow_null=True)
    last_decision = serializers.CharField(allow_blank=True)
    override_standing = serializers.BooleanField()
    emboldened_bands = serializers.IntegerField()
    terms_ease = serializers.IntegerField()
    has_morale = serializers.BooleanField()
    morale_state = serializers.CharField()
    party_force = serializers.FloatField()
    effective_party_force = serializers.FloatField()
    group_force = serializers.FloatField()
    affiliation = serializers.CharField(allow_blank=True)
    cause_edited = serializers.BooleanField()
    affiliation_edited = serializers.BooleanField()
    drives = GMDriveViewSerializer(many=True)
    faction_rules = GMFactionRuleViewSerializer(many=True)
    members = GMMemberViewSerializer(many=True)


class GMStandoffViewSerializer(serializers.Serializer):
    """Everything a GM sees of a standoff (``services/gm_view.py``). GM and staff only."""

    place = serializers.CharField(allow_blank=True)
    participants = serializers.ListField(child=serializers.CharField())
    groups = GMGroupViewSerializer(many=True)


class SummaryGroupViewSerializer(serializers.Serializer):
    group_id = serializers.IntegerField()
    name = serializers.CharField()
    member_count = serializers.IntegerField()
    state = serializers.CharField()
    morale_state = serializers.CharField()
    emboldened = serializers.BooleanField()


class StandoffSummarySerializer(serializers.Serializer):
    """The public standoff summary an onlooker sees (``services/gm_view.py``)."""

    place = serializers.CharField(allow_blank=True)
    participants = serializers.ListField(child=serializers.CharField())
    groups = SummaryGroupViewSerializer(many=True)


class StandoffMoraleRequestSerializer(serializers.Serializer):
    """Body for the GM morale control (#4354): which group, which way, and why."""

    group_id = serializers.IntegerField()
    direction = serializers.ChoiceField(choices=MoraleDirection.choices)
    reason = serializers.CharField(max_length=500, trim_whitespace=True)
