import django_filters

from world.scenes.models import Persona, Scene, SceneMessage


class SceneFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()
    is_public = django_filters.BooleanFilter()
    location = django_filters.NumberFilter(field_name="location__id")
    participant = django_filters.NumberFilter(field_name="participants__id")

    class Meta:
        model = Scene
        fields = ["is_active", "is_public", "location", "participant"]


class PersonaFilter(django_filters.FilterSet):
    scene = django_filters.NumberFilter(field_name="scene__id")
    account = django_filters.NumberFilter(field_name="account__id")
    character = django_filters.NumberFilter(field_name="character__id")

    class Meta:
        model = Persona
        fields = ["scene", "account", "character"]


class SceneMessageFilter(django_filters.FilterSet):
    scene = django_filters.NumberFilter(field_name="scene__id")
    persona = django_filters.NumberFilter(field_name="persona__id")
    context = django_filters.CharFilter(field_name="context")
    mode = django_filters.CharFilter(field_name="mode")

    class Meta:
        model = SceneMessage
        fields = ["scene", "persona", "context", "mode"]
