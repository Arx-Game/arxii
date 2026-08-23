"""FactoryBoy factories for board models (#3286)."""

import factory
from factory.django import DjangoModelFactory

from evennia_extensions.factories import RoomProfileFactory
from world.boards.models import Board, BoardPost
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory


class LocationBoardFactory(DjangoModelFactory):
    """Factory for a LOCATION board anchored to a room."""

    class Meta:
        model = Board

    room_profile = factory.SubFactory(RoomProfileFactory)
    name = "Notice Board"


class OrgBoardFactory(DjangoModelFactory):
    """Factory for an ORG board anchored to an organization."""

    class Meta:
        model = Board

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.LazyAttribute(lambda obj: f"{obj.organization.name} Board")


class BoardPostFactory(DjangoModelFactory):
    """Factory for creating BoardPost instances."""

    class Meta:
        model = BoardPost

    board = factory.SubFactory(LocationBoardFactory)
    author_persona = factory.SubFactory(PersonaFactory)
    title = factory.Sequence(lambda n: f"Notice {n}")
    body = factory.Faker("paragraph")
