from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.factories import FlowExecutionFactory, SceneDataManagerFactory
from flows.flow_stack import FlowStack
from flows.models import FlowDefinition


class LookFlowEventTests(TestCase):
    def test_look_flow_emits_events_for_target_and_contents(self):
        room = ObjectDBFactory(
            db_key="Hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        viewer = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(db_key="Rock", location=room)
        item1 = ObjectDBFactory(db_key="pebble", location=target)
        item2 = ObjectDBFactory(db_key="stone", location=target)

        look_flow = FlowDefinition.objects.get(name="look")

        context = SceneDataManagerFactory()
        stack = FlowStack(trigger_registry=room.trigger_registry)
        for obj in (room, viewer, target, item1, item2):
            context.initialize_state_for_object(obj)

        fx = FlowExecutionFactory(
            flow_definition=look_flow,
            context=context,
            flow_stack=stack,
            origin=viewer,
            variable_mapping={"caller": viewer, "target": target, "mode": "look"},
        )
        stack.execute_flow(fx)

        self.assertIn("look_at_target", context.flow_events)
        self.assertIn("look_at_contents_0", context.flow_events)
        self.assertIn("look_at_contents_1", context.flow_events)
        targets = {
            context.flow_events["look_at_target"].data["target"],
            context.flow_events["look_at_contents_0"].data["target"],
            context.flow_events["look_at_contents_1"].data["target"],
        }
        self.assertEqual({target, item1, item2}, targets)
