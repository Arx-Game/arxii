"""FactoryBoy factories for positioning models.

Designed to double as integration-test setUp AND seed data.
"""

from __future__ import annotations

import factory
import factory.django

from world.areas.positioning.constants import PositionKind
from world.areas.positioning.models import (
    BlueprintEdge,
    BlueprintPosition,
    ObjectPosition,
    Position,
    PositionBlueprint,
    PositionEdge,
)


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


# ---------------------------------------------------------------------------
# Blueprint factories
# ---------------------------------------------------------------------------


class PositionBlueprintFactory(factory.django.DjangoModelFactory):
    """Factory for PositionBlueprint.

    ``name`` uses a Sequence to satisfy the unique constraint.
    Pass ``name=`` explicitly to create a named blueprint::

        bp = PositionBlueprintFactory(name="Tavern")
    """

    class Meta:
        model = PositionBlueprint

    name = factory.Sequence(lambda n: f"blueprint_{n}")
    description = ""


class BlueprintPositionFactory(factory.django.DjangoModelFactory):
    """Factory for BlueprintPosition.

    Creates a fresh blueprint unless one is supplied::

        bp = PositionBlueprintFactory()
        pos1 = BlueprintPositionFactory(blueprint=bp)
        pos2 = BlueprintPositionFactory(blueprint=bp)
    """

    class Meta:
        model = BlueprintPosition

    blueprint = factory.SubFactory(PositionBlueprintFactory)
    name = factory.Sequence(lambda n: f"bp_position_{n}")
    kind = PositionKind.FEATURE
    description = ""


class BlueprintEdgeFactory(factory.django.DjangoModelFactory):
    """Factory for BlueprintEdge.

    Creates two BlueprintPositions in a single shared blueprint, then orders
    them canonically so position_a.pk < position_b.pk (as the model requires).

    To supply your own positions::

        edge = BlueprintEdgeFactory(position_a=p1, position_b=p2)

    Note: if you pass position_a/position_b out of order the factory will swap
    them before saving. Alternatively, call
    services.connect_blueprint_positions() which handles ordering automatically.
    """

    class Meta:
        model = BlueprintEdge
        exclude = ["_shared_blueprint"]

    is_passable = True

    # A shared blueprint used only when both positions are auto-generated.
    @factory.lazy_attribute
    def _shared_blueprint(self) -> PositionBlueprint:
        return PositionBlueprintFactory()

    @factory.lazy_attribute
    def blueprint(self) -> PositionBlueprint:
        return self._shared_blueprint

    @factory.lazy_attribute
    def position_a(self) -> BlueprintPosition:
        return BlueprintPositionFactory(blueprint=self._shared_blueprint, name="bp_pos_a")

    @factory.lazy_attribute
    def position_b(self) -> BlueprintPosition:
        return BlueprintPositionFactory(blueprint=self._shared_blueprint, name="bp_pos_b")

    @classmethod
    def _create(cls, model_class: type, *args: object, **kwargs: object) -> BlueprintEdge:
        """Ensure canonical ordering and consistent blueprint FK before saving."""
        a = kwargs.get("position_a")
        b = kwargs.get("position_b")
        if a is not None and b is not None and a.pk > b.pk:
            kwargs["position_a"], kwargs["position_b"] = b, a
        # Keep blueprint FK consistent with the (possibly-swapped) position_a.
        if kwargs.get("position_a") is not None:
            kwargs["blueprint"] = kwargs["position_a"].blueprint
        return super()._create(model_class, *args, **kwargs)


# ---------------------------------------------------------------------------
# Worked-sample seed helper
# ---------------------------------------------------------------------------


def tavern_blueprint() -> PositionBlueprint:
    """Return the canonical Tavern blueprint, creating it if it doesn't exist yet.

    Builds a realistic 3-position layout via the Task-4 authoring services so
    canonical-edge ordering and blueprint-consistency constraints are exercised.
    This doubles as an integration-test fixture and staff seed data::

        bp = tavern_blueprint()
        positions = instantiate_blueprint(bp, some_room)

    Layout::

        Hearth ── Bar ── Doorway
    """
    from world.areas.positioning.services import (
        add_blueprint_position,
        connect_blueprint_positions,
        create_blueprint,
    )

    try:
        return PositionBlueprint.objects.get(name="Tavern")
    except PositionBlueprint.DoesNotExist:
        pass

    bp = create_blueprint("Tavern", description="A common-room layout: hearth, bar, and entrance.")
    hearth = add_blueprint_position(
        bp, "Hearth", kind=PositionKind.FEATURE, description="A warm stone hearth."
    )
    bar = add_blueprint_position(
        bp, "Bar", kind=PositionKind.FEATURE, description="The bar counter."
    )
    doorway = add_blueprint_position(
        bp, "Doorway", kind=PositionKind.FEATURE, description="The main entrance."
    )
    connect_blueprint_positions(hearth, bar)
    connect_blueprint_positions(bar, doorway)
    return bp
