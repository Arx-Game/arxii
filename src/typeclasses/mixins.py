from typing import TYPE_CHECKING, Self, Union

from django.utils.functional import cached_property

from core.descriptors import ReverseOneToOneOrNone
from flows.object_states.base_state import BaseState
from flows.scene_data_manager import SceneDataManager
from flows.trigger_handler import TriggerHandler

if TYPE_CHECKING:
    from evennia.objects.objects import DefaultObject

    from world.character_sheets.models import CharacterSheet

DEFAULT_GENDER = "neutral"


class ObjectParent:
    """
    This is a mixin that can be used to override *all* entities inheriting at
    some distance from DefaultObject (Objects, Exits, Characters and Rooms).

    Just add any method that exists on `DefaultObject` to this class. If one
    of the derived classes has itself defined that same hook already, that will
    take precedence.

    """

    state_class = BaseState

    @property
    def item_data(self: Union[Self, "DefaultObject"]):
        """Return a handler that provides unified data access for serialization."""
        from evennia_extensions.data_handlers import ObjectItemDataHandler

        return ObjectItemDataHandler(self)

    def get_object_state(
        self: Union[Self, "DefaultObject"],
        context: "SceneDataManager",
    ) -> BaseState:
        return self.state_class(obj=self, context=context)

    @cached_property
    def trigger_handler(self: Union[Self, "DefaultObject"]) -> TriggerHandler:
        """Populate-once cache of active triggers for this object."""
        return TriggerHandler(owner=self)

    @cached_property
    def conditions(self: Union[Self, "DefaultObject"]):
        """Populate-once cache of active ConditionInstance rows for this object.

        Returns a ConditionHandler that loads the owner's active conditions on
        first access and serves subsequent reads query-free.  Character overrides
        this with CharacterConditionHandler (adds resistance_modifier).

        Invalidated by condition mutation services (apply_condition, etc.).
        """
        from world.conditions.handlers import ConditionHandler

        return ConditionHandler(self)

    @property
    def character_sheet(self: Union[Self, "DefaultObject"]) -> "CharacterSheet | None":
        """This object's CharacterSheet, or None for anything that isn't a character.

        The safe, explicit replacement for ``obj.character_sheet``:
        ``sheet_data`` is the reverse OneToOne from ``CharacterSheet.character`` and
        raises on sheetless objects — the getattr idiom only "worked" because Django's
        RelatedObjectDoesNotExist subclasses AttributeError, which also swallowed
        genuine attribute bugs. Use this on maybe-not-a-character objects; use
        ``obj.sheet_data`` directly where a missing sheet is a hard bug.
        """
        from world.character_sheets.models import CharacterSheet

        try:
            return self.sheet_data
        except CharacterSheet.DoesNotExist:
            return None

    # Reverse-OneToOne safe accessors (the *_or_none family, #2386): missing row
    # → None; genuine attribute bugs still raise. Use the raw accessor where a
    # missing row is a hard bug; use world.areas.services.get_room_profile when
    # you want get-or-create.
    room_profile_or_none = ReverseOneToOneOrNone("room_profile")
    item_instance_or_none = ReverseOneToOneOrNone("item_instance")

    @cached_property
    def positions_cached(self: Union[Self, "DefaultObject"]) -> list:
        """This object's tactical positions — the Prefetch/query shared interface.

        Lives on ObjectParent (not Room) because ``Position.room`` is an FK to
        bare ObjectDB: any object may be asked for its positions and answers
        with an empty list rather than AttributeError. Combat's encounter
        queryset pre-fills this name via ``Prefetch(..., to_attr=
        "positions_cached")`` (world/combat/views.py); independent callers get
        the same shape — nested ``passable_edges_as_a`` / ``passable_edges_as_b``
        / ``all_edges_as_a`` attrs and the rampart join — from this lazy query
        (4 bounded queries, no per-position N+1). Invalidated by
        Position/PositionEdge save/delete and the bulk positioning services via
        ``world.areas.positioning.models.invalidate_position_graph_caches``.
        """
        from django.db.models import Prefetch

        from world.areas.positioning.models import PositionEdge

        passable = PositionEdge.objects.filter(is_passable=True).only(
            "position_a_id", "position_b_id"
        )
        return list(
            self.positions.select_related("rampart__element_profile").prefetch_related(
                Prefetch("edges_as_a", queryset=passable, to_attr="passable_edges_as_a"),
                Prefetch("edges_as_b", queryset=passable, to_attr="passable_edges_as_b"),
                Prefetch(
                    "edges_as_a",
                    queryset=PositionEdge.objects.select_related("gating_challenge__template"),
                    to_attr="all_edges_as_a",
                ),
            )
        )

    @property
    def scene_data(self: Union[Self, "DefaultObject"]):
        """Return the SceneDataManager from our containing location."""
        if self.location:
            return self.location.scene_data
        return None

    @property
    def scene_state(self: Union[Self, "DefaultObject"]) -> BaseState | None:
        """Return the state object representing this entity in the scene."""
        scene_data = self.scene_data
        if scene_data:
            return scene_data.get_state_by_pk(self.pk)
        return None

    @property
    def gender(self: Union[Self, "DefaultObject"]) -> str:
        """Gender used by funcparser pronoun helpers."""
        return DEFAULT_GENDER

    def get_display_name(
        self: Union[Self, "DefaultObject"],
        looker=None,
        **kwargs,
    ) -> str:
        """Return the display name using state data when available."""
        state = self.scene_state
        if state:
            looker_state = looker.scene_state if looker else None
            return state.get_display_name(looker_state, **kwargs)
        return super().get_display_name(looker, **kwargs)
