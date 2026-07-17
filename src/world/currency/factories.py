"""FactoryBoy factories for currency test data."""

import factory

from world.currency.models import FavorTokenDetails
from world.items.factories import ItemInstanceFactory
from world.societies.factories import OrganizationFactory


class FavorTokenDetailsFactory(factory.django.DjangoModelFactory):
    """Factory for FavorTokenDetails (Golden Hare favor tokens, #2428).

    Prefer the ``mint_favor_token`` service for tests that need a physical
    game_object too — this factory is for row-shape tests that don't.
    """

    class Meta:
        model = FavorTokenDetails

    item_instance = factory.SubFactory(ItemInstanceFactory)
    issuing_organization = factory.SubFactory(OrganizationFactory)
    provenance_note = factory.Sequence(lambda n: f"Deed {n}")
