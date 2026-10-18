"""Serializers for the per-viewer standoff payload (see ``services/view.py``) and placements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rest_framework import serializers

from world.mechanics.models import Property
from world.societies.models import Organization
from world.standoffs.constants import CauseEffect, DriveStrength, MoraleDirection
from world.standoffs.services.placement import (
    DriveEdit,
    draft_from_line,
    placement_errors,
    save_placement,
)

if TYPE_CHECKING:
    from world.standoffs.services.placement import OpponentLine


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
    refusal = serializers.CharField(allow_blank=True)


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
    levers = LeverViewSerializer(many=True)
    refusal = serializers.CharField(allow_blank=True)


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
    cause_effect = serializers.ChoiceField(choices=CauseEffect.choices)
    matched_by = serializers.ListField(child=serializers.CharField())
    revealed = serializers.BooleanField()
    source = serializers.CharField(allow_blank=True)
    why = serializers.ListField(child=serializers.CharField())


class GMMemberViewSerializer(serializers.Serializer):
    opponent_id = serializers.IntegerField()
    name = serializers.CharField()
    morale = serializers.IntegerField()
    morale_state = serializers.CharField()


class GMRegardViewSerializer(serializers.Serializer):
    participant = serializers.CharField()
    regard = serializers.IntegerField()
    label = serializers.CharField()
    bands = serializers.IntegerField()


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
    effective_margin_percent = serializers.IntegerField()
    cause_clock = serializers.CharField(allow_blank=True)
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
    is_named_npc = serializers.BooleanField()
    speaks = serializers.ListField(child=serializers.CharField())
    regards = GMRegardViewSerializer(many=True)


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


# --- Placements (#4361) -------------------------------------------------------------------


class OpponentLineDriveSerializer(serializers.Serializer):
    """One drive edit on a placement: a strength, or null to remove the template's drive."""

    property = serializers.PrimaryKeyRelatedField(queryset=Property.objects.all())
    property_name = serializers.CharField(read_only=True)
    strength = serializers.ChoiceField(choices=DriveStrength.choices, allow_null=True)


_TEMPLATE_FIELD = "creature_template"
_ORGANIZATION_FIELD = "organization"


class PlacementFieldsMixin(serializers.Serializer):
    """Placement edits on an opponent line serializer (beat or mission option line).

    Mixed into the two line ``ModelSerializer`` classes; their ``Meta.fields`` list the
    model fields ``cause_override``, ``cause_margin_override`` and ``organization``. The
    two list fields here are child rows written by ``save_placement`` once the parent
    serializer has saved the line (``pop_placement_rows`` / ``save_placement_rows``).
    """

    drive_edits = OpponentLineDriveSerializer(many=True, required=False)
    suppressed_faction_rules = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )
    organization_name = serializers.SerializerMethodField()

    def get_organization_name(self, instance: object) -> str:
        """The overriding affiliation's name, so an editor can show the pick (read only)."""
        organization = instance.organization
        return organization.name if organization is not None else ""

    def to_representation(self, instance: object) -> dict:
        data = super().to_representation(instance)
        data["drive_edits"] = [
            {
                "property": row.property_id,
                "property_name": row.property.name,
                "strength": row.strength,
            }
            for row in instance.drive_edits.select_related("property")
        ]
        data["suppressed_faction_rules"] = sorted(
            instance.faction_rule_suppressions.values_list("faction_rule_id", flat=True)
        )
        return data

    def validate(self, attrs: dict) -> dict:
        """Check the edits against what the line inherits (a nested line row carries its
        template and affiliation; a row that names no template has nothing to check)."""
        attrs = super().validate(attrs)
        template = attrs.get(_TEMPLATE_FIELD)
        if template is None:
            return attrs
        organization = attrs.get(_ORGANIZATION_FIELD)
        errors = placement_errors(
            template,
            organization,
            [DriveEdit(row["property"], row["strength"]) for row in attrs.get("drive_edits", [])],
            attrs.get("suppressed_faction_rules", []),
            persona=attrs.get("persona"),
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


@dataclass(frozen=True)
class PlacementRows:
    """The child rows one line payload carried, or None for a list it did not send."""

    drive_edits: list[DriveEdit] | None
    suppressed_rule_ids: list[int] | None


def pop_placement_rows(row: dict) -> PlacementRows:
    """Take the placement child lists off one validated line row before the line is saved."""
    drives = row.pop("drive_edits", None)
    suppressed = row.pop("suppressed_faction_rules", None)
    return PlacementRows(
        drive_edits=(
            None if drives is None else [DriveEdit(d["property"], d["strength"]) for d in drives]
        ),
        suppressed_rule_ids=suppressed,
    )


def save_placement_rows(line: OpponentLine, rows: PlacementRows) -> None:
    """Write a saved line's drive edits and suppressions (a list not sent is kept)."""
    current = draft_from_line(line)
    drive_edits = (
        rows.drive_edits
        if rows.drive_edits is not None
        else [
            DriveEdit(row.property, row.strength)
            for row in line.drive_edits.select_related("property")
        ]
    )
    save_placement(
        line,
        cause_override=line.cause_override,
        cause_margin_override=line.cause_margin_override,
        organization=line.organization,
        drive_edits=drive_edits,
        suppressed_rule_ids=(
            rows.suppressed_rule_ids
            if rows.suppressed_rule_ids is not None
            else sorted(current.suppressed_ids)
        ),
    )


class PlacementDriveContextSerializer(serializers.Serializer):
    property = serializers.IntegerField(source="property_id")
    name = serializers.CharField(source="property.name")
    strength = serializers.IntegerField()
    strength_label = serializers.CharField()


class PlacementRuleContextSerializer(serializers.Serializer):
    faction_rule_id = serializers.IntegerField(source="rule.pk")
    label = serializers.CharField()
    source = serializers.CharField()
    level = serializers.IntegerField()


class PlacementPickSerializer(serializers.Serializer):
    """One row of a placement editor's affiliation or drive picker."""

    id = serializers.IntegerField()
    name = serializers.CharField()


class PlacementContextQuerySerializer(serializers.Serializer):
    """The placement-context preview's one optional argument: an affiliation to try."""

    organization = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(), required=False, allow_null=True
    )


class PlacementContextSerializer(serializers.Serializer):
    """A creature template's standoff profile, for a placement editor's "template" column."""

    creature_template = serializers.IntegerField()
    name = serializers.CharField()
    cause = serializers.CharField()
    cause_label = serializers.CharField()
    cause_margin_percent = serializers.IntegerField()
    organization = serializers.IntegerField(allow_null=True)
    organization_name = serializers.CharField(allow_blank=True)
    drives = PlacementDriveContextSerializer(many=True)
    inherited_rules = PlacementRuleContextSerializer(many=True)
    language_name = serializers.CharField(allow_blank=True)
