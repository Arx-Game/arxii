"""FactoryBoy factories for room_features models."""

import factory
from factory.django import DjangoModelFactory

from world.room_features.constants import (
    RoomFeatureInstallMechanism,
    RoomFeatureOwnerType,
    RoomFeatureServiceStrategy,
)
from world.room_features.models import (
    RoomFeatureInstance,
    RoomFeatureKind,
    RoomFeatureKindInstallRitual,
    RoomFeatureKindOwnerType,
    RoomFeatureProgressionDetails,
)


class RoomFeatureKindFactory(DjangoModelFactory):
    class Meta:
        model = RoomFeatureKind
        django_get_or_create = ("service_strategy",)

    name = factory.Sequence(lambda n: f"room-feature-kind-{n}")
    description = ""
    max_level = 5
    service_strategy = RoomFeatureServiceStrategy.SANCTUM
    install_mechanism = RoomFeatureInstallMechanism.RITUAL


class RoomFeatureKindInstallRitualFactory(DjangoModelFactory):
    class Meta:
        model = RoomFeatureKindInstallRitual
        django_get_or_create = ("feature_kind", "ritual")

    feature_kind = factory.SubFactory(RoomFeatureKindFactory)
    ritual = factory.SubFactory("world.magic.factories.RitualFactory")
    variant_label = ""


class RoomFeatureKindOwnerTypeFactory(DjangoModelFactory):
    class Meta:
        model = RoomFeatureKindOwnerType
        django_get_or_create = ("feature_kind", "owner_type")

    feature_kind = factory.SubFactory(RoomFeatureKindFactory)
    owner_type = RoomFeatureOwnerType.PERSONA


class RoomFeatureInstanceFactory(DjangoModelFactory):
    class Meta:
        model = RoomFeatureInstance

    room_profile = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")
    feature_kind = factory.SubFactory(RoomFeatureKindFactory)
    level = 1


class RoomFeatureProgressionDetailsFactory(DjangoModelFactory):
    class Meta:
        model = RoomFeatureProgressionDetails

    project = factory.SubFactory("world.projects.factories.ProjectFactory")
    target_room_profile = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")
    target_feature_kind = factory.SubFactory(RoomFeatureKindFactory)
    target_level = 1
