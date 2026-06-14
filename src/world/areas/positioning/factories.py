"""FactoryBoy factories for positioning models.

Designed to double as integration-test setUp AND seed data.
"""

from __future__ import annotations

import factory
import factory.django

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.models import ObjectPosition, Position, PositionEdge


class PositionFactory(factory.django.DjangoModelFactory):
    """Factory for Position.

    By default creates a fresh Room for each position. For tests that need two
    positions in the same room, pass ``room=some_room`` explicitly:

        room = ObjectDB.objects.create(...)
        a = PositionFactory(room=room, name="ground")
        b = PositionFactory(room=room, name="balcony")
    """

    class Meta:
        model = Position

    name = factory.Sequence(lambda n: f"position_{n}")
    kind = PositionKind.FEATURE
    description = ""

    @factory.lazy_attribute
    def room(self) -> object:
        from evennia import create_object

        return create_object("typeclasses.rooms.Room", key="Test Room", nohome=True)


class PositionEdgeFactory(factory.django.DjangoModelFactory):
    """Factory for PositionEdge.

    Creates two positions in a single shared room, then orders them canonically
    so position_a.pk < position_b.pk (as the model requires).

    To supply your own positions::

        edge = PositionEdgeFactory(position_a=p1, position_b=p2)

    Note: if you pass position_a/position_b out of order the factory will swap
    them before saving. Alternatively, call services.connect_positions() which
    handles ordering automatically.
    """

    class Meta:
        model = PositionEdge
        exclude = ["_shared_room"]

    is_passable = True
    gating_challenge = None

    # A shared room used only when both positions are auto-generated.
    @factory.lazy_attribute
    def _shared_room(self) -> object:
        from evennia import create_object

        return create_object("typeclasses.rooms.Room", key="Shared Test Room", nohome=True)

    @factory.lazy_attribute
    def position_a(self) -> Position:
        return PositionFactory(room=self._shared_room, name="pos_a")

    @factory.lazy_attribute
    def position_b(self) -> Position:
        return PositionFactory(room=self._shared_room, name="pos_b")

    @classmethod
    def _create(cls, model_class: type, *args: object, **kwargs: object) -> PositionEdge:
        """Ensure canonical ordering before delegating to Django create."""
        a = kwargs.get("position_a")
        b = kwargs.get("position_b")
        if a is not None and b is not None and a.pk > b.pk:
            kwargs["position_a"], kwargs["position_b"] = b, a
        return super()._create(model_class, *args, **kwargs)


class ObjectPositionFactory(factory.django.DjangoModelFactory):
    """Factory for ObjectPosition.

    Creates a Position (and thus a Room) and a Character located in that room.
    """

    class Meta:
        model = ObjectPosition

    position = factory.SubFactory(PositionFactory)

    @factory.lazy_attribute
    def objectdb(self) -> object:
        from evennia import create_object

        return create_object(
            "typeclasses.characters.Character",
            key="TestOccupant",
            location=self.position.room,
            nohome=True,
        )
