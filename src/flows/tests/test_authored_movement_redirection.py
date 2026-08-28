"""A working labyrinth, built entirely from authored rows (#3416).

This is the proof for the governing constraint on #3416: **no bespoke model,
field, or class per magical space.** Everything below is rows a builder could
create - `ConditionTemplate`, `ConditionStage`, `ConditionInstance`,
`FlowDefinition`, `FlowStepDefinition`, `TriggerDefinition`, `Trigger` - plus
the generic service-function verbs. Nothing in `src/` knows what a labyrinth
is, and if this test ever needs a Python class to express the maze, the
constraint has been violated.

The slimmed-down space:

        gate            (Labyrinth Layer, stage 3)
       /    \\
    l2a      l2b        (Labyrinth Layer, stage 2)
       \\    /
    l1a      l1b        (Labyrinth Layer, stage 1)
       \\    /
        outer           (the street - no layer)

Advance: whichever way you go, you land in a *random* room one layer deeper,
until you reach the gate. Retreat: heading back toward the street takes you
straight out, from any depth, in one move.
"""

import random

from django.test import TestCase, tag
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionInstance, ConditionTemplate

LAYER = "Labyrinth Layer"
LOST = "Lost in the Labyrinth"

ADVANCE_FN = "world.conditions.services.advance_condition_stage"
REDIRECT_RANDOM_FN = "flows.service_functions.movement.redirect_move_to_bearer_at_stage"
REMOVE_FN = "world.conditions.services.remove_condition_by_name"
REDIRECT_FN = "flows.service_functions.movement.redirect_move"


def _room(key: str) -> ObjectDB:
    return ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")


@tag("postgres")
class AuthoredLabyrinthTests(TestCase):
    """The labyrinth, as data. See module docstring.

    Postgres tier: applying a condition runs
    ``ConditionStage.objects.filter(...).distinct("condition_id")``
    (`world/conditions/services.py:560`), and DISTINCT ON is PG-only.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outer = _room("The Street")
        cls.l1a, cls.l1b = _room("Hedges I-A"), _room("Hedges I-B")
        cls.l2a, cls.l2b = _room("Hedges II-A"), _room("Hedges II-B")
        cls.gate = _room("The Gate")

        # --- Rooms are grouped by depth using a condition ON THE ROOM. --------
        # ConditionInstance.target accepts a room, so "every room at depth 2"
        # is an ordinary queryset over authored rows - no grouping model.
        layer_tpl = ConditionTemplateFactory(name=LAYER, has_progression=True)
        layer_stage = {
            n: ConditionStageFactory(
                condition=layer_tpl, stage_order=n, name=f"Layer {n}", rounds_to_next=None
            )
            for n in (1, 2, 3)
        }
        for room, depth in (
            (cls.l1a, 1),
            (cls.l1b, 1),
            (cls.l2a, 2),
            (cls.l2b, 2),
            (cls.gate, 3),
        ):
            ConditionInstanceFactory(
                target=room, condition=layer_tpl, current_stage=layer_stage[depth]
            )

        # --- The character's depth is a staged condition on the character. ----
        # current_stage IS the depth; rounds_to_next is the authored dwell
        # budget, so the arrival bound is data, not a Python rule.
        cls.lost_tpl = ConditionTemplateFactory(name=LOST, has_progression=True)
        for n in (1, 2, 3):
            ConditionStageFactory(
                condition=cls.lost_tpl,
                stage_order=n,
                name=f"Lost, depth {n}",
                rounds_to_next=1 if n < 3 else None,
            )

        # --- The maze's logic: two flows. -------------------------------------
        advance_flow = FlowDefinitionFactory()
        advance_root = FlowStepDefinitionFactory(
            flow=advance_flow,
            parent_id=None,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name=ADVANCE_FN,
            parameters={
                "payload": "@payload",
                "condition_name": LOST,
                "result_variable": "depth",
            },
        )
        FlowStepDefinitionFactory(
            flow=advance_flow,
            # parent_id, not parent: the factory declares `parent_id = None`, so
            # passing `parent=` sends both and the None wins - silently making
            # this a second ROOT step instead of a child.
            parent_id=advance_root.pk,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name=REDIRECT_RANDOM_FN,
            parameters={
                "payload": "@payload",
                "condition_name": LAYER,
                "stage_order": "@depth",
            },
        )

        retreat_flow = FlowDefinitionFactory()
        retreat_root = FlowStepDefinitionFactory(
            flow=retreat_flow,
            parent_id=None,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name=REMOVE_FN,
            parameters={"payload": "@payload", "condition_name": LOST},
        )
        FlowStepDefinitionFactory(
            flow=retreat_flow,
            parent_id=retreat_root.pk,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name=REDIRECT_FN,
            parameters={"payload": "@payload", "room_id": cls.outer.pk},
        )

        # --- Triggers, discriminated by an authored filter. --------------------
        # "Heading back toward the street" is the retreat; anything else is an
        # advance. Both are JSON on the Trigger row, not code.
        heading_out = {"path": "destination.id", "op": "==", "value": cls.outer.pk}
        advance_def = TriggerDefinitionFactory(
            event_name=EventName.MOVE_PRE_DEPART, flow_definition=advance_flow
        )
        retreat_def = TriggerDefinitionFactory(
            event_name=EventName.MOVE_PRE_DEPART, flow_definition=retreat_flow
        )
        for room in (cls.outer, cls.l1a, cls.l1b, cls.l2a, cls.l2b):
            TriggerFactory(
                trigger_definition=advance_def,
                obj=room,
                additional_filter_condition={"not": heading_out},
            )
            if room is not cls.outer:
                TriggerFactory(
                    trigger_definition=retreat_def,
                    obj=room,
                    additional_filter_condition=heading_out,
                )

        cls.layer_one = {cls.l1a.pk, cls.l1b.pk}
        cls.layer_two = {cls.l2a.pk, cls.l2b.pk}

    def setUp(self) -> None:
        super().setUp()
        random.seed(20260828)
        self.char = CharacterFactory()
        self.char.location = self.outer

    def _depth(self) -> int | None:
        instance = ConditionInstance.objects.filter(target=self.char, condition__name=LOST).first()
        if instance is None or instance.current_stage is None:
            return None
        return instance.current_stage.stage_order

    # -- advance ----------------------------------------------------------

    def test_walking_in_lands_in_a_layer_one_room(self) -> None:
        """Aiming at the gate from the street lands you in layer one instead."""
        self.char.move_to(self.gate, quiet=True)

        self.assertIn(
            self.char.location.pk,
            self.layer_one,
            "Expected the maze to redirect the move into a layer-one room",
        )
        self.assertEqual(self._depth(), 1)

    def test_every_direction_goes_deeper_and_arrives_at_the_gate(self) -> None:
        """Whichever way you aim, you sink one layer per move and reach the gate."""
        self.char.move_to(self.gate, quiet=True)
        self.assertIn(self.char.location.pk, self.layer_one)

        # Aim back at the street's neighbour rather than onward - still deeper.
        self.char.move_to(self.l1a, quiet=True)
        self.assertIn(
            self.char.location.pk,
            self.layer_two,
            "Aiming sideways should still take you a layer deeper",
        )
        self.assertEqual(self._depth(), 2)

        self.char.move_to(self.l2b, quiet=True)
        self.assertEqual(self.char.location.pk, self.gate.pk)
        self.assertEqual(self._depth(), 3)

    def test_arrival_is_bounded_by_the_authored_stage_count(self) -> None:
        """The bound is data: three stages, so never more than three moves."""
        moves = 0
        while self.char.location.pk != self.gate.pk and moves < 10:
            self.char.move_to(self.gate, quiet=True)
            moves += 1

        self.assertEqual(self.char.location.pk, self.gate.pk)
        self.assertLessEqual(
            moves, 3, "Arrival must be bounded by the authored stages, not by luck"
        )

    def test_the_room_you_land_in_is_random_within_the_layer(self) -> None:
        """Landing room varies across seeds; the depth never does."""
        landings = set()
        for seed in range(12):
            random.seed(seed)
            char = CharacterFactory()
            char.location = self.outer
            char.move_to(self.gate, quiet=True)
            landings.add(char.location.pk)

        self.assertEqual(
            landings,
            self.layer_one,
            "Expected both layer-one rooms to be reachable across seeds",
        )

    # -- retreat ----------------------------------------------------------

    def test_retreat_from_depth_one_exits_immediately(self) -> None:
        """Turning back on the entry layer puts you on the street in one move."""
        self.char.move_to(self.gate, quiet=True)
        self.assertIn(self.char.location.pk, self.layer_one)

        self.char.move_to(self.outer, quiet=True)

        self.assertEqual(self.char.location.pk, self.outer.pk)
        self.assertIsNone(self._depth(), "The condition should be gone once you are out")

    def test_retreat_from_the_deepest_layer_also_exits_immediately(self) -> None:
        """Retreat is one move out from ANY depth, not a walk back up."""
        self.char.move_to(self.gate, quiet=True)
        self.char.move_to(self.l1a, quiet=True)
        self.assertIn(self.char.location.pk, self.layer_two)
        self.assertEqual(self._depth(), 2)

        self.char.move_to(self.outer, quiet=True)

        self.assertEqual(self.char.location.pk, self.outer.pk)
        self.assertIsNone(self._depth())

    def test_re_entering_after_a_retreat_starts_over(self) -> None:
        """Leaving really ends it - walking back in begins at depth one again."""
        self.char.move_to(self.gate, quiet=True)
        self.char.move_to(self.outer, quiet=True)

        self.char.move_to(self.gate, quiet=True)

        self.assertIn(self.char.location.pk, self.layer_one)
        self.assertEqual(self._depth(), 1)

    # -- the constraint itself --------------------------------------------

    def test_the_whole_space_is_authored_rows(self) -> None:
        """Guard on #3416's governing constraint: no labyrinth model exists.

        If someone later adds one, this test should be deleted deliberately -
        not quietly updated.
        """
        self.assertTrue(ConditionTemplate.objects.filter(name=LAYER).exists())
        self.assertTrue(ConditionTemplate.objects.filter(name=LOST).exists())

        from django.apps import apps

        model_names = {m.__name__.lower() for m in apps.get_models()}
        for forbidden in ("labyrinth", "labyrinthlayer", "labyrinthroom", "labyrinthtransit"):
            self.assertNotIn(
                forbidden,
                model_names,
                f"A bespoke {forbidden!r} model was added - see #3416 decision 1",
            )
