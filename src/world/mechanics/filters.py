"""FilterSet classes for mechanics API views."""

import django_filters

from world.mechanics.models import (
    ChallengeInstance,
    ChallengeTemplate,
    CharacterModifier,
    ModifierTarget,
    SituationInstance,
    SituationTemplate,
)


class ModifierTargetFilter(django_filters.FilterSet):
    """Filter for ModifierTarget list views."""

    category = django_filters.CharFilter(field_name="category__name", lookup_expr="iexact")

    class Meta:
        model = ModifierTarget
        fields = ["category", "is_active"]


class CharacterModifierFilter(django_filters.FilterSet):
    """Filter for CharacterModifier list views."""

    class Meta:
        model = CharacterModifier
        fields = ["character", "target"]


class ChallengeTemplateFilter(django_filters.FilterSet):
    """Filter for ChallengeTemplate list views."""

    category = django_filters.CharFilter(field_name="category__name", lookup_expr="iexact")

    class Meta:
        model = ChallengeTemplate
        fields = ["category", "challenge_type", "severity", "discovery_type"]


class ChallengeInstanceFilter(django_filters.FilterSet):
    """Filter for ChallengeInstance list views."""

    class Meta:
        model = ChallengeInstance
        fields = ["location", "is_active", "is_revealed", "template", "situation_instance"]


class SituationTemplateFilter(django_filters.FilterSet):
    """Filter for SituationTemplate list views."""

    category = django_filters.CharFilter(field_name="category__name", lookup_expr="iexact")

    class Meta:
        model = SituationTemplate
        fields = ["category"]


class SituationInstanceFilter(django_filters.FilterSet):
    """Filter for SituationInstance list views."""

    class Meta:
        model = SituationInstance
        fields = ["location", "is_active", "created_by"]
