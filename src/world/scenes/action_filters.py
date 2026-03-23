"""Filters for scene action requests."""

import django_filters

from world.scenes.action_models import SceneActionRequest


class SceneActionRequestFilter(django_filters.FilterSet):
    scene = django_filters.NumberFilter(field_name="scene_id")
    status = django_filters.CharFilter(field_name="status")
    initiator = django_filters.NumberFilter(field_name="initiator_persona_id")
    target = django_filters.NumberFilter(field_name="target_persona_id")

    class Meta:
        model = SceneActionRequest
        fields = ["scene", "status", "initiator", "target"]
