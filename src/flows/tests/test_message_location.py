from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowExecutionFactory,
    FlowStepDefinitionFactory,
)
from flows.service_functions.communication import message_location
from world.scenes.factories import SceneFactory
from world.scenes.models import Persona, SceneMessage, SceneParticipation


class TestMessageLocation(TestCase):
    def test_names_vary_by_looker(self):
        room = ObjectDBFactory(
            db_key="Hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        bystander = ObjectDBFactory(
            db_key="Charlie",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        flow_def = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow_def,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="message_location",
            parameters={
                "caller": "@caller",
                "target": "@target",
                "text": "$You() $conj(greet) $you(target).",
            },
        )

        fx = FlowExecutionFactory(
            flow_definition=flow_def,
            variable_mapping={"caller": caller, "target": target.pk},
        )
        for obj in (room, caller, target, bystander):
            fx.context.initialize_state_for_object(obj)

        target_state = fx.context.get_state_by_pk(target.pk)

        target_state.fake_name = "Mysterious figure"
        fx.context.add_to_context_list(
            key=target.pk, attribute="real_name_viewers", value=caller.pk
        )

        with (
            patch.object(caller, "msg") as caller_msg,
            patch.object(target, "msg") as target_msg,
            patch.object(bystander, "msg") as by_msg,
        ):
            fx.flow_stack.execute_flow(fx)

            self.assertEqual(caller_msg.call_args.kwargs["text"][0], "You greet Bob.")
            self.assertEqual(
                target_msg.call_args.kwargs["text"][0], "Alice greets you."
            )
            self.assertEqual(
                by_msg.call_args.kwargs["text"][0], "Alice greets Mysterious figure."
            )

    def test_modify_fake_name_for_viewer(self):
        room = ObjectDBFactory(
            db_key="Hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        bystander = ObjectDBFactory(
            db_key="Charlie",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        flow_def = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow_def,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="message_location",
            parameters={
                "caller": "@caller",
                "target": "@target",
                "text": "$You() $conj(glare) at $you(target).",
            },
        )

        fx = FlowExecutionFactory(
            flow_definition=flow_def,
            variable_mapping={"caller": caller, "target": target.pk},
        )
        for obj in (room, caller, target, bystander):
            fx.context.initialize_state_for_object(obj)

        target_state = fx.context.get_state_by_pk(target.pk)

        target_state.fake_name = "Masked stranger"
        fx.context.add_to_context_list(
            key=target.pk, attribute="real_name_viewers", value=caller.pk
        )
        fx.context.set_context_dict_value(
            key=target.pk,
            attribute="name_suffix_map",
            dict_key=bystander.pk,
            value=" (Evil)",
        )

        with (
            patch.object(caller, "msg") as caller_msg,
            patch.object(target, "msg") as target_msg,
            patch.object(bystander, "msg") as by_msg,
        ):
            fx.flow_stack.execute_flow(fx)

            self.assertEqual(
                caller_msg.call_args.kwargs["text"][0], "You glare at Bob."
            )
            self.assertEqual(
                target_msg.call_args.kwargs["text"][0], "Alice glares at you."
            )
            self.assertEqual(
                by_msg.call_args.kwargs["text"][0],
                "Alice glares at Masked stranger (Evil).",
            )

    def test_flowsteps_fake_name_and_suffix(self):
        room = ObjectDBFactory(
            db_key="Hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        target = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )
        bystander = ObjectDBFactory(
            db_key="Charlie",
            db_typeclass_path="typeclasses.characters.Character",
            location=room,
        )

        flow_def = FlowDefinitionFactory()
        step1 = FlowStepDefinitionFactory(
            flow=flow_def,
            action=FlowActionChoices.SET_CONTEXT_VALUE,
            variable_name="target",
            parameters={"attribute": "fake_name", "value": "Masked stranger"},
        )
        step2 = FlowStepDefinitionFactory(
            flow=flow_def,
            parent_id=step1.id,
            action=FlowActionChoices.ADD_CONTEXT_LIST_VALUE,
            variable_name="target",
            parameters={"attribute": "real_name_viewers", "value": "@caller.pk"},
        )
        step3 = FlowStepDefinitionFactory(
            flow=flow_def,
            parent_id=step2.id,
            action=FlowActionChoices.SET_CONTEXT_DICT_VALUE,
            variable_name="target",
            parameters={
                "attribute": "name_suffix_map",
                "key": "@bystander.pk",
                "value": " (Evil)",
            },
        )
        FlowStepDefinitionFactory(
            flow=flow_def,
            parent_id=step3.id,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="message_location",
            parameters={
                "caller": "@caller",
                "target": "@target",
                "text": "$You() $conj(glare) at $you(target).",
            },
        )

        fx = FlowExecutionFactory(
            flow_definition=flow_def,
            variable_mapping={
                "caller": caller,
                "target": target.pk,
                "bystander": bystander,
            },
        )
        for obj in (room, caller, target, bystander):
            fx.context.initialize_state_for_object(obj)

        with (
            patch.object(caller, "msg") as caller_msg,
            patch.object(target, "msg") as target_msg,
            patch.object(bystander, "msg") as by_msg,
        ):
            fx.flow_stack.execute_flow(fx)

            self.assertEqual(
                caller_msg.call_args.kwargs["text"][0], "You glare at Bob."
            )
            self.assertEqual(
                target_msg.call_args.kwargs["text"][0], "Alice glares at you."
            )
            self.assertEqual(
                by_msg.call_args.kwargs["text"][0],
                "Alice glares at Masked stranger (Evil).",
            )

    def test_message_location_records_scene_message(self):
        room = ObjectDBFactory(
            db_key="Hall", db_typeclass_path="typeclasses.rooms.Room"
        )
        caller = CharacterFactory(location=room)
        caller.account = AccountFactory()
        scene = SceneFactory(location=room)
        room.active_scene = scene
        fx = FlowExecutionFactory(variable_mapping={"caller": caller})
        fx.context.initialize_state_for_object(caller)
        fx.context.initialize_state_for_object(room)
        with patch.object(room, "msg_contents"):
            message_location(fx, "@caller", "waves.")
        self.assertEqual(SceneMessage.objects.filter(scene=scene).count(), 1)
        participation = SceneParticipation.objects.get(
            scene=scene, account=caller.account
        )
        Persona.objects.get(participation=participation, character=caller)
