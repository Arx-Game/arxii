"""Inputs for staff edit mode's row writes (#4221, #3988 piece B).

One serializer per family. Ids arrive as primary keys and leave as model rows;
validation here is shape only, the rules live in the services the views call.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from world.character_creation.models import Beginnings
from world.character_sheets.models import CharacterEnemy
from world.classes.models import Path
from world.distinctions.models import CharacterDistinction, Distinction
from world.forms.constants import MarkingKind
from world.forms.models import FormMarking, FormTrait, FormTraitOption
from world.goals.serializers import GoalInputSerializer
from world.items.constants import BodyRegion
from world.journals.constants import JournalKind
from world.skills.models import Skill, Specialization
from world.traits.models import Trait, TraitType
from world.worship.models import WorshippedBeing

#: The three Introductions a character may hold as journals (#3621).
INTRODUCTION_KINDS = (JournalKind.FIRST_JOURNAL, JournalKind.APPLICATION, JournalKind.WHISPERS)


def _rows_by_pk(queryset: Any, data: dict[str, int], label: str) -> dict[Any, int]:
    """``{"<pk>": value}`` to ``{row: value}``; an unknown pk is a validation error."""
    try:
        wanted = {int(pk): int(value) for pk, value in data.items()}
    except (TypeError, ValueError) as exc:
        msg = f"{label} must map ids to whole numbers."
        raise serializers.ValidationError(msg) from exc
    rows = {row.pk: row for row in queryset.filter(pk__in=list(wanted))}
    missing = sorted(wanted.keys() - rows.keys())
    if missing:
        msg = f"Unknown {label}: {', '.join(str(pk) for pk in missing)}."
        raise serializers.ValidationError(msg)
    return {rows[pk]: value for pk, value in wanted.items()}


def _tradition_queryset() -> Any:
    from world.magic.models import Tradition  # noqa: PLC0415

    return Tradition.objects.all()


def _gift_queryset() -> Any:
    from world.magic.models import Gift  # noqa: PLC0415

    return Gift.objects.all()


def _technique_queryset() -> Any:
    from world.magic.models import Technique  # noqa: PLC0415

    return Technique.objects.all()


def _resonance_queryset() -> Any:
    from world.magic.models import Resonance  # noqa: PLC0415

    return Resonance.objects.all()


class StaffStatsSerializer(serializers.Serializer):
    """``{"stats": {"<trait id>": <1 to 5>}}``."""

    stats = serializers.DictField(child=serializers.IntegerField())

    def validate_stats(self, value: dict[str, int]) -> dict[Trait, int]:
        return _rows_by_pk(Trait.objects.filter(trait_type=TraitType.STAT), value, "stats")


class StaffSkillsSerializer(serializers.Serializer):
    """``{"skills": {"<skill id>": n}, "specializations": {"<id>": n}}``."""

    skills = serializers.DictField(child=serializers.IntegerField(), required=False, default=dict)
    specializations = serializers.DictField(
        child=serializers.IntegerField(), required=False, default=dict
    )

    def validate_skills(self, value: dict[str, int]) -> dict[Skill, int]:
        return _rows_by_pk(Skill.objects.select_related("trait"), value, "skills")

    def validate_specializations(self, value: dict[str, int]) -> dict[Specialization, int]:
        return _rows_by_pk(Specialization.objects.all(), value, "specializations")


class StaffDistinctionAddSerializer(serializers.Serializer):
    distinction = serializers.PrimaryKeyRelatedField(queryset=Distinction.objects.all())
    rank = serializers.IntegerField(min_value=1, default=1)
    feature_trait = serializers.PrimaryKeyRelatedField(
        queryset=FormTrait.objects.all(), required=False, allow_null=True, default=None
    )
    feature_marking = serializers.PrimaryKeyRelatedField(
        queryset=FormMarking.objects.all(), required=False, allow_null=True, default=None
    )


class StaffDistinctionChangeSerializer(serializers.Serializer):
    """Re-rank (``rank``) or remove (no rank) one held distinction of this sheet."""

    character_distinction = serializers.PrimaryKeyRelatedField(
        queryset=CharacterDistinction.objects.select_related("distinction")
    )
    rank = serializers.IntegerField(min_value=1, required=False)

    def validate_character_distinction(self, value: CharacterDistinction) -> CharacterDistinction:
        if value.character_id != self.context["sheet"].pk:
            msg = "That distinction is not this character's."
            raise serializers.ValidationError(msg)
        return value


class StaffFormSerializer(serializers.Serializer):
    """``{"values": {"<form trait id>": <option id>}, "descriptors": {"<trait id>": text}}``."""

    values = serializers.DictField(child=serializers.IntegerField(), required=False, default=dict)
    descriptors = serializers.DictField(
        child=serializers.CharField(allow_blank=True), required=False, default=dict
    )

    def validate_values(self, value: dict[str, int]) -> dict[FormTrait, FormTraitOption]:
        traits = _rows_by_pk(FormTrait.objects.all(), value, "form traits")
        options = {
            row.pk: row for row in FormTraitOption.objects.filter(pk__in=list(traits.values()))
        }
        missing = sorted(set(traits.values()) - options.keys())
        if missing:
            msg = f"Unknown options: {', '.join(str(pk) for pk in missing)}."
            raise serializers.ValidationError(msg)
        return {trait: options[option_id] for trait, option_id in traits.items()}

    def validate_descriptors(self, value: dict[str, str]) -> dict[FormTrait, str]:
        traits = {row.pk: row for row in FormTrait.objects.filter(pk__in=[int(k) for k in value])}
        if len(traits) != len(value):
            msg = "Unknown form traits."
            raise serializers.ValidationError(msg)
        return {traits[int(pk)]: text for pk, text in value.items()}


class StaffBeginningsSerializer(serializers.Serializer):
    beginnings = serializers.PrimaryKeyRelatedField(queryset=Beginnings.objects.all())


class StaffPathSerializer(serializers.Serializer):
    """The first path (only when the sheet has none) and/or the primary class level."""

    path = serializers.PrimaryKeyRelatedField(
        queryset=Path.objects.all(), required=False, allow_null=True, default=None
    )
    level = serializers.IntegerField(min_value=1, max_value=30, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("path") is None and "level" not in attrs:  # noqa: STRING_LITERAL - the serializer's own field name
            msg = "Name a path or a level."
            raise serializers.ValidationError(msg)
        return attrs


class StaffGoalsSerializer(serializers.Serializer):
    goals = GoalInputSerializer(many=True)


class StaffWorshipSerializer(serializers.Serializer):
    public_being = serializers.PrimaryKeyRelatedField(
        queryset=WorshippedBeing.objects.all(), allow_null=True
    )
    secret_being = serializers.PrimaryKeyRelatedField(
        queryset=WorshippedBeing.objects.all(), allow_null=True
    )


class StaffMarkingAddSerializer(serializers.Serializer):
    body_region = serializers.ChoiceField(choices=BodyRegion.choices)
    kind = serializers.ChoiceField(choices=MarkingKind.choices)
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(allow_blank=True, required=False, default="")


class StaffMarkingRemoveSerializer(serializers.Serializer):
    marking = serializers.PrimaryKeyRelatedField(
        queryset=FormMarking.objects.select_related("form")
    )

    def validate_marking(self, value: FormMarking) -> FormMarking:
        if value.form.character_id != self.context["sheet"].pk:
            msg = "That marking is not this character's."
            raise serializers.ValidationError(msg)
        return value


class StaffEnemySerializer(serializers.ModelSerializer):
    """The Actor's Sheet enemy (#3621); ``id`` names a held one to change."""

    id = serializers.PrimaryKeyRelatedField(
        queryset=CharacterEnemy.objects.all(), required=False, allow_null=True, source="enemy"
    )

    class Meta:
        model = CharacterEnemy
        fields = [
            "id",
            "kind",
            "organization",
            "figure_name",
            "power_tier",
            "reach",
            "degree",
            "price",
            "why",
            "public_line",
            "status",
            "reason",
        ]

    def validate_id(self, value: CharacterEnemy | None) -> CharacterEnemy | None:
        if value is not None and value.character_id != self.context["sheet"].pk:
            msg = "That enemy is not this character's."
            raise serializers.ValidationError(msg)
        return value


class StaffIntroductionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[(k.value, k.label) for k in INTRODUCTION_KINDS])
    title = serializers.CharField(max_length=200)
    body = serializers.CharField()


class StaffOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class StaffFormTraitOptionsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    options = StaffOptionSerializer(many=True)


class StaffChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class StaffOptionsSerializer(serializers.Serializer):
    """What staff edit mode's row editors pick from, for one sheet (#4221)."""

    stats = StaffOptionSerializer(many=True)
    skills = StaffOptionSerializer(many=True)
    specializations = StaffOptionSerializer(many=True)
    distinctions = StaffOptionSerializer(many=True)
    form_traits = StaffFormTraitOptionsSerializer(many=True)
    beginnings = StaffOptionSerializer(many=True)
    paths = StaffOptionSerializer(many=True)
    beings = StaffOptionSerializer(many=True)
    marking_regions = StaffChoiceSerializer(many=True)
    marking_kinds = StaffChoiceSerializer(many=True)
    enemy_kinds = StaffChoiceSerializer(many=True)
    enemy_degrees = StaffChoiceSerializer(many=True)
    enemy_power_tiers = StaffChoiceSerializer(many=True)


class StaffMagicSerializer(serializers.Serializer):
    """Grant magic (#4224): the CG magic stage's picks, for a sheet with no gift."""

    tradition = serializers.PrimaryKeyRelatedField(queryset=_tradition_queryset())
    gift = serializers.PrimaryKeyRelatedField(queryset=_gift_queryset())
    techniques = serializers.PrimaryKeyRelatedField(queryset=_technique_queryset(), many=True)
    resonance = serializers.PrimaryKeyRelatedField(queryset=_resonance_queryset())
    anima_stat = serializers.PrimaryKeyRelatedField(
        queryset=Trait.objects.filter(trait_type=TraitType.STAT)
    )
    anima_skill = serializers.PrimaryKeyRelatedField(
        queryset=Skill.objects.filter(is_active=True).select_related("trait")
    )
    ritual_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    glimpse = serializers.CharField(required=False, allow_blank=True, default="")


class StaffMagicOptionsSerializer(serializers.Serializer):
    """What Grant magic picks from, narrowed by the tradition and gift picked so far."""

    traditions = StaffOptionSerializer(many=True)
    gifts = StaffOptionSerializer(many=True)
    techniques = StaffOptionSerializer(many=True)
    resonances = StaffOptionSerializer(many=True)
    stats = StaffOptionSerializer(many=True)
    skills = StaffOptionSerializer(many=True)
    technique_limit = serializers.IntegerField()


# --- Kinship, estate and reputation (#4226, #3988 piece D) ---------------------


def _kinsperson_queryset() -> Any:
    from world.roster.models import Kinsperson  # noqa: PLC0415

    return Kinsperson.objects.all()


def _family_queryset() -> Any:
    from world.roster.models import Family  # noqa: PLC0415

    return Family.objects.all()


def _room_profile_queryset() -> Any:
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    return RoomProfile.objects.all()


def _grant_profile_queryset() -> Any:
    from world.buildings.models import PropertyGrantProfile  # noqa: PLC0415

    return PropertyGrantProfile.objects.all()


def _house_claim_queryset() -> Any:
    """Approved claims riding a staff account's draft: a claim on a player's draft is
    that player's application, and materializing it here would take their house."""
    from world.societies.houses.constants import HouseClaimStatus  # noqa: PLC0415
    from world.societies.houses.models import HouseClaim  # noqa: PLC0415

    return HouseClaim.objects.filter(
        status=HouseClaimStatus.APPROVED, draft__account__is_staff=True
    )


def _vacancy_queryset() -> Any:
    from world.societies.models import Vacancy  # noqa: PLC0415

    return Vacancy.objects.all()


def _organization_queryset() -> Any:
    from world.societies.models import Organization  # noqa: PLC0415

    return Organization.objects.all()


class StaffKinshipSerializer(serializers.Serializer):
    """Claim an open position (``node``), or self-serve one in ``family`` (or none)."""

    node = serializers.PrimaryKeyRelatedField(
        queryset=_kinsperson_queryset(), required=False, allow_null=True, default=None
    )
    family = serializers.PrimaryKeyRelatedField(
        queryset=_family_queryset(), required=False, allow_null=True, default=None
    )


class StaffResidenceSerializer(serializers.Serializer):
    room_profile = serializers.PrimaryKeyRelatedField(queryset=_room_profile_queryset())


class StaffPropertySerializer(serializers.Serializer):
    """A grant profile; blank means the one the character's Beginnings carries."""

    profile = serializers.PrimaryKeyRelatedField(
        queryset=_grant_profile_queryset(), required=False, allow_null=True, default=None
    )


class StaffHouseClaimSerializer(serializers.Serializer):
    claim = serializers.PrimaryKeyRelatedField(queryset=_house_claim_queryset())


class StaffVacancySerializer(serializers.Serializer):
    vacancy = serializers.PrimaryKeyRelatedField(queryset=_vacancy_queryset())


class StaffReputationSerializer(serializers.Serializer):
    organization = serializers.PrimaryKeyRelatedField(queryset=_organization_queryset())
    value = serializers.IntegerField()


class StaffEstateOptionsSerializer(serializers.Serializer):
    """What the kin, estate and reputation editors pick from; rooms come by search."""

    open_positions = StaffOptionSerializer(many=True)
    families = StaffOptionSerializer(many=True)
    rooms = StaffOptionSerializer(many=True)
    grant_profiles = StaffOptionSerializer(many=True)
    house_claims = StaffOptionSerializer(many=True)
    vacancies = StaffOptionSerializer(many=True)
    organizations = StaffOptionSerializer(many=True)
