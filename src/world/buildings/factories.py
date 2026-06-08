"""FactoryBoy factories for the buildings system."""

import factory
from factory.django import DjangoModelFactory

from world.buildings.models import (
    Building,
    BuildingConstructionDetails,
    BuildingKind,
    BuildingMaterial,
    BuildingPermitDetails,
    MaterialLoreEffect,
)

# Factory-path string for the Persona sub-factory, referenced by multiple
# factories below. Centralized to avoid the duplicated-literal SonarCloud
# smell (python:S1192).
_PERSONA_FACTORY = "world.scenes.factories.PersonaFactory"


class BuildingKindFactory(DjangoModelFactory):
    class Meta:
        model = BuildingKind
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"building-kind-{n}")
    description = ""
    rooms_per_size_tier = 20
    is_residential = True
    is_commercial = False
    is_fortified = False
    is_occult = False
    is_maritime = False
    is_agrarian = False
    is_aerial = False
    is_subterranean = False
    is_secret = False


class BuildingFactory(DjangoModelFactory):
    class Meta:
        model = Building

    area = factory.SubFactory("world.areas.factories.AreaFactory", level=10)  # BUILDING level
    kind = factory.SubFactory(BuildingKindFactory)
    target_size = 5
    target_grandeur = 5
    max_rooms = factory.LazyAttribute(lambda obj: obj.kind.rooms_per_size_tier * obj.target_size)
    constructed_by_persona = factory.SubFactory(_PERSONA_FACTORY)
    source_project = None


class BuildingMaterialFactory(DjangoModelFactory):
    class Meta:
        model = BuildingMaterial

    building = factory.SubFactory(BuildingFactory)
    item_template = factory.SubFactory("world.items.factories.ItemTemplateFactory")
    item_instance_pk = None
    units = 1
    quality_tier = None
    lore_value = 0
    contributed_by_persona = factory.SubFactory(_PERSONA_FACTORY)


class MaterialLoreEffectFactory(DjangoModelFactory):
    class Meta:
        model = MaterialLoreEffect

    template = factory.SubFactory("world.items.factories.ItemTemplateFactory")
    target_stat = "resonance_amp"
    units_per_tier = 5
    magnitude_per_tier = 1
    max_tiers = None


class BuildingPermitDetailsFactory(DjangoModelFactory):
    class Meta:
        model = BuildingPermitDetails

    item_instance = factory.SubFactory("world.items.factories.ItemInstanceFactory")
    building_kind = factory.SubFactory(BuildingKindFactory)
    max_target_size = 10
    cost_modifier = 1
    issued_by_role = None
    notes_text = ""
    consumed_at = None
    consumed_by_persona = None


class BuildingConstructionDetailsFactory(DjangoModelFactory):
    class Meta:
        model = BuildingConstructionDetails

    project = factory.SubFactory("world.projects.factories.ProjectFactory")
    permit_details = factory.SubFactory(BuildingPermitDetailsFactory)
    ward = factory.SubFactory("world.areas.factories.AreaFactory", level=30)  # WARD
    target_size = 5
    target_grandeur = 5
    constructed_by_persona = factory.SubFactory(_PERSONA_FACTORY)
