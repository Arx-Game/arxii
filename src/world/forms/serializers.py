from rest_framework import serializers

from world.forms.models import (
    AlternateSelf,
    Build,
    CharacterForm,
    CharacterFormValue,
    FormTrait,
    FormTraitOption,
    HeightBand,
)


class FormTraitOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormTraitOption
        fields = ["id", "name", "display_name", "sort_order"]


class FormTraitSerializer(serializers.ModelSerializer):
    options = FormTraitOptionSerializer(many=True, read_only=True)

    class Meta:
        model = FormTrait
        fields = ["id", "name", "display_name", "trait_type", "options"]


class FormTraitWithOptionsSerializer(serializers.Serializer):
    """Serializer for CG form options response."""

    trait = FormTraitSerializer()
    options = FormTraitOptionSerializer(many=True)


class CharacterFormValueSerializer(serializers.ModelSerializer):
    trait = FormTraitSerializer(read_only=True)
    option = FormTraitOptionSerializer(read_only=True)
    trait_id = serializers.PrimaryKeyRelatedField(
        queryset=FormTrait.objects.all(), source="trait", write_only=True
    )
    option_id = serializers.PrimaryKeyRelatedField(
        queryset=FormTraitOption.objects.all(), source="option", write_only=True
    )

    class Meta:
        model = CharacterFormValue
        fields = ["id", "trait", "option", "trait_id", "option_id"]


class CharacterFormSerializer(serializers.ModelSerializer):
    values = CharacterFormValueSerializer(source="cached_values", many=True, read_only=True)

    class Meta:
        model = CharacterForm
        fields = ["id", "name", "form_type", "is_player_created", "created_at", "values"]


class ApparentFormSerializer(serializers.Serializer):
    """Serializer for apparent form display."""

    traits = serializers.SerializerMethodField()

    def get_traits(self, apparent_form: dict):
        """Convert trait->option dict to list of trait/option pairs."""
        return [
            {
                "trait": FormTraitSerializer(trait).data,
                "option": FormTraitOptionSerializer(option).data,
            }
            for trait, option in apparent_form.items()
        ]


class HeightBandSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeightBand
        fields = ["id", "name", "display_name", "min_inches", "max_inches", "is_cg_selectable"]


class BuildSerializer(serializers.ModelSerializer):
    class Meta:
        model = Build
        fields = ["id", "name", "display_name", "is_cg_selectable"]


class AlternateSelfSerializer(serializers.ModelSerializer):
    """Read shape for the alternate-self switcher (#1111 slice 4).

    Includes the active alt-self flag for the played character so the switcher can
    highlight the currently-assumed form without a second round-trip.
    """

    persona_name = serializers.SerializerMethodField()
    form_name = serializers.SerializerMethodField()
    has_combat_profile = serializers.SerializerMethodField()
    has_techniques = serializers.SerializerMethodField()
    resonance_name = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = AlternateSelf
        fields = [
            "id",
            "display_name",
            "persona_name",
            "form_name",
            "has_combat_profile",
            "has_techniques",
            "resonance_name",
            "is_active",
        ]

    def get_persona_name(self, obj: AlternateSelf) -> str | None:
        return obj.persona.name if obj.persona_id is not None else None

    def get_form_name(self, obj: AlternateSelf) -> str | None:
        return obj.form.name or None if obj.form_id is not None else None

    def get_has_combat_profile(self, obj: AlternateSelf) -> bool:
        return obj.combat_profile_id is not None

    def get_has_techniques(self, obj: AlternateSelf) -> bool:
        return obj.techniques.exists()

    def get_resonance_name(self, obj: AlternateSelf) -> str | None:
        return obj.resonance.name if obj.resonance_id is not None else None

    def get_is_active(self, obj: AlternateSelf) -> bool:
        if not hasattr(self, "_active_alternate_self_id"):
            request = self.context.get("request")
            user = getattr(request, "user", None)  # noqa: GETATTR_LITERAL
            puppet = getattr(user, "puppet", None)  # noqa: GETATTR_LITERAL
            sheet = puppet.character_sheet
            active = (
                getattr(sheet, "active_alternate_self", None)  # noqa: GETATTR_LITERAL
                if sheet is not None
                else None
            )
            self._active_alternate_self_id = (
                active.alternate_self_id if active is not None else None
            )
        return self._active_alternate_self_id == obj.pk


class ShiftFormRequestSerializer(serializers.Serializer):
    """POST body for the alternate-self shift endpoint."""

    alternate_self_id = serializers.IntegerField(min_value=1)


class ActiveAlternateSelfResultSerializer(serializers.Serializer):
    """Result of a successful shift or revert — the now-active alternate-self id."""

    active_alternate_self_id = serializers.IntegerField(allow_null=True)
