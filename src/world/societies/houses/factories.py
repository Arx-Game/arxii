"""FactoryBoy factories for houses test data (#2540 slice 2)."""

from __future__ import annotations

import factory
import factory.django

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.items.factories import MaterialCategoryFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.services import add_holding, create_domain


class HoldingKindFactory(factory.django.DjangoModelFactory):
    """Factory for HoldingKind — the authorable catalog of domain holdings."""

    class Meta:
        model = "arxii.HoldingKind"
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Holding Kind {n}")
    stream_kind = "domain_tax"
    base_gross = 1000


class DomainHoldingFactory(factory.django.DjangoModelFactory):
    """Factory for DomainHolding.

    Wires a real ``OrgIncomeStream`` via ``add_holding`` (the same helper the game's
    domain-management flow uses) rather than creating the row directly, so the stream
    stays consistent with production wiring.
    """

    class Meta:
        model = "arxii.DomainHolding"

    class Params:
        domain_name = factory.Sequence(lambda n: f"Domain {n}")
        owner_org = factory.SubFactory(OrganizationFactory)

    domain = factory.LazyAttribute(
        lambda o: create_domain(
            area=AreaFactory(level=AreaLevel.REGION),
            name=o.domain_name,
            owner_org=o.owner_org,
        )
    )
    kind = factory.SubFactory(HoldingKindFactory)
    name = factory.Sequence(lambda n: f"Holding {n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        return add_holding(domain=kwargs["domain"], kind=kwargs["kind"], name=kwargs["name"])


class HoldingMaterialSourceFactory(factory.django.DjangoModelFactory):
    """Factory for HoldingMaterialSource (#2540 slice 2)."""

    class Meta:
        model = "arxii.HoldingMaterialSource"
        django_get_or_create = ("holding", "material_category")

    holding = factory.SubFactory(DomainHoldingFactory)
    material_category = factory.SubFactory(MaterialCategoryFactory)
