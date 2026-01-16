from rest_framework import serializers

from world.forms.models import (
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
    values = CharacterFormValueSerializer(many=True, read_only=True)

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
