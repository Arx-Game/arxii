from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.factories import FlowExecutionFactory
from flows.service_functions.communication import message_location


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

        fx = FlowExecutionFactory(variable_mapping={"caller": caller, "target": target})
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
            message_location(
                fx,
                "$caller",
                target="$target",
                caller_message="You greet {target}.",
                target_message="{caller} greets you.",
                bystander_message="{caller} greets {target}.",
            )

            caller_msg.assert_called_with("You greet Bob.")
            target_msg.assert_called_with("Alice greets you.")
            by_msg.assert_called_with("Alice greets Mysterious figure.")

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

        fx = FlowExecutionFactory(variable_mapping={"caller": caller, "target": target})
        for obj in (room, caller, target, bystander):
            fx.context.initialize_state_for_object(obj)

        target_state = fx.context.get_state_by_pk(target.pk)
        bystander_state = fx.context.get_state_by_pk(bystander.pk)

        target_state.fake_name = "Masked stranger"
        fx.context.add_to_context_list(
            key=target.pk, attribute="real_name_viewers", value=caller.pk
        )
        fx.context.modify_context_dict_value(
            key=target.pk,
            attribute="display_name_map",
            dict_key=bystander.pk,
            modifier=lambda name: (
                f"{target_state.get_display_name(bystander_state)} (Evil)"
                if name is None
                else f"{name} (Evil)"
            ),
        )

        with (
            patch.object(caller, "msg") as caller_msg,
            patch.object(target, "msg") as target_msg,
            patch.object(bystander, "msg") as by_msg,
        ):
            message_location(
                fx,
                "$caller",
                target="$target",
                caller_message="You glare at {target}.",
                target_message="{caller} glares at you.",
                bystander_message="{caller} glares at {target}.",
            )

            caller_msg.assert_called_with("You glare at Bob.")
            target_msg.assert_called_with("Alice glares at you.")
            by_msg.assert_called_with("Alice glares at Masked stranger (Evil).")
