"""Read-only traversal checks and authoritative hook compatibility."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.utils import timezone
from evennia.objects.models import ObjectDB

from actions.base import Action
from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from behaviors.traversal_inspection import INSPECTION_UNAVAILABLE, inspect_exit_traversal
from commands.exceptions import CommandError
from evennia_extensions.factories import ObjectDBFactory
from flows.object_states.base_state import BaseState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.movement import check_exit_traversal
from flows.service_functions.serializers.room_state import exit_hidden_from_viewer
from world.character_sheets.factories import CharacterSheetFactory
from world.fatigue.models import FatiguePool
from world.fatigue.services import get_fatigue_zone, get_fatigue_zone_readonly
from world.gm.factories import GMProfileFactory
from world.instances.models import InstancedRoom
from world.instances.services import spawn_instanced_room
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.services.encumbrance import OVERLOADED_EXHAUSTED_MSG, carry_capacity
from world.missions.factories import MissionInstanceFactory, MissionParticipantFactory
from world.scenes.place_models import Place


def write_on_initialize(state: BaseState, pkg: BehaviorPackageInstance) -> None:
    Place.objects.create(room_id=pkg.get_from_data("room_id"), name="Initialization control")
    state.set_attribute("key_id", "silver")


def write_on_traverse(state: BaseState, pkg: BehaviorPackageInstance, actor: BaseState) -> bool:
    Place.objects.create(room=state.obj.location.room_profile, name="Traversal control")
    return True


def false_traverse(state: BaseState, pkg: BehaviorPackageInstance, actor: BaseState) -> bool:
    return False


def record_legacy_traverse(
    state: BaseState, pkg: BehaviorPackageInstance, actor: BaseState
) -> object:
    state.traversal_calls.append(pkg.get_from_data("label"))
    return pkg.get_from_data("result")


def fail_if_legacy_traverse_reached(
    state: BaseState, pkg: BehaviorPackageInstance, actor: BaseState
) -> None:
    message = "Hook after a terminating result was called"
    raise AssertionError(message)


@contextmanager
def forbid_read_effects() -> Iterator[None]:
    def readonly_sql(
        execute: object, sql: str, params: object, many: bool, context: dict
    ) -> object:
        operation = sql.lstrip().upper()
        assert operation.startswith(("SELECT", "EXPLAIN")), sql
        assert "FOR UPDATE" not in operation, sql
        assert "FOR SHARE" not in operation, sql
        return execute(sql, params, many, context)

    with ExitStack() as stack:
        stack.enter_context(connection.execute_wrapper(readonly_sql))
        stack.enter_context(
            patch("flows.emit.emit_event", side_effect=AssertionError("Read emitted an event"))
        )
        stack.enter_context(
            patch(
                "behaviors.models.import_module",
                side_effect=AssertionError("Read imported an authored hook"),
            )
        )
        for owner, name in (
            (SceneDataManager, "initialize_state_for_object"),
            (SceneDataManager, "get_state_by_pk"),
            (BaseState, "__init__"),
            (BaseState, "initialize_state"),
            (BaseState, "_run_package_hook"),
            (BehaviorPackageDefinition, "get_service_function"),
            (BehaviorPackageInstance, "get_hook"),
            (Action, "run"),
            (Action, "execute"),
            (Action, "_emit_intent"),
            (Action, "_emit_result"),
        ):
            stack.enter_context(
                patch.object(
                    owner, name, side_effect=AssertionError(f"Read called {owner.__name__}.{name}")
                )
            )
        yield


class TraversalInspectionTests(TestCase):
    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.dest = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.dest.room_profile.published_at = timezone.now()
        self.dest.room_profile.save(update_fields=["published_at"])
        self.sheet = CharacterSheetFactory()
        self.actor = self.sheet.character
        self.actor.location = self.room
        self.exit = ObjectDBFactory(
            db_typeclass_path="typeclasses.exits.Exit", location=self.room, destination=self.dest
        )
        self.key = ObjectDBFactory(location=self.actor)
        self.manager = SceneDataManager()
        self.lock = self.attach(
            self.exit,
            "can_traverse",
            "behaviors.matching_value_package.require_matching_value",
            {"attribute": "key_id", "value": "silver", "error": "Bring the silver key."},
        )
        self.values = self.attach(
            self.key,
            "initialize_state",
            "behaviors.state_values_package.initialize_state",
            {"values": {"key_id": "silver"}},
        )

    def attach(
        self, obj: ObjectDB, hook: str, path: str, data: dict | None = None
    ) -> BehaviorPackageInstance:
        definition = BehaviorPackageDefinition.objects.create(
            name=f"inspection-{BehaviorPackageDefinition.objects.count()}",
            service_function_path=path,
        )
        return BehaviorPackageInstance.objects.create(
            definition=definition, obj=obj, hook=hook, data=data
        )

    def read(
        self,
        *,
        actor: ObjectDB | None = None,
        exit_obj: ObjectDB | None = None,
        manager: SceneDataManager | None = None,
    ) -> None:
        before = dict(self.manager.states)
        attributes = {pk: dict(state.__dict__) for pk, state in self.manager.states.items()}
        with forbid_read_effects():
            inspect_exit_traversal(
                self.actor if actor is None else actor,
                self.exit if exit_obj is None else exit_obj,
                scene_data=manager,
            )
        self.assertEqual(self.manager.states, before)
        for pk, values in attributes.items():
            self.assertEqual(self.manager.states[pk].__dict__, values)

    def refuse(self, reason: str, **kwargs: object) -> None:
        with self.assertRaisesMessage(CommandError, reason):
            self.read(**kwargs)

    def test_keyed_exit_cold_ground_carried_and_authored_null(self) -> None:
        self.read()
        self.assertEqual(self.manager.states, {})
        self.key.location = self.room
        self.refuse("Bring the silver key.")
        self.key.location = self.actor
        for data in ({"key_id": "silver"}, {"values": None, "key_id": "silver"}):
            self.values.data = data
            self.values.save(update_fields=["data"])
            self.read()
        for data in (None, {"values": []}, {"values": {"key_id": None}}):
            self.values.data = data
            self.values.save(update_fields=["data"])
            self.refuse("Bring the silver key.")

    def test_initialized_ephemeral_override_and_deletion_are_current(self) -> None:
        state = self.manager.initialize_state_for_object(self.key)
        self.read(manager=self.manager)
        for value in ("copper", None, False, 0):
            state.set_attribute("key_id", value)
            self.refuse("Bring the silver key.", manager=self.manager)
        state.set_attribute("key_id", "silver")
        self.read(manager=self.manager)
        self.values.data = {"values": {"key_id": "copper"}}
        self.values.save(update_fields=["data"])
        self.read(manager=self.manager)
        self.refuse("Bring the silver key.")
        del state.__dict__["key_id"]
        self.refuse("Bring the silver key.", manager=self.manager)

    def test_shared_comparison_matches_real_execution(self) -> None:
        caller = self.manager.initialize_state_for_object(self.actor)
        exit_state = self.manager.initialize_state_for_object(self.exit)
        self.read(manager=self.manager)
        check_exit_traversal(caller, exit_state)
        self.key.location = self.room
        self.refuse("Bring the silver key.", manager=self.manager)
        with self.assertRaisesMessage(CommandError, "Bring the silver key."):
            check_exit_traversal(caller, exit_state)
        self.lock.data = {"attribute": "key_id", "value": None}
        self.lock.save(update_fields=["data"])
        self.refuse("Lock is misconfigured.")
        with forbid_read_effects(), self.assertRaisesMessage(CommandError, "No actor provided."):
            inspect_exit_traversal(None, self.exit)

    def test_null_actor_without_authored_requirement_is_refused_without_effects(self) -> None:
        self.lock.delete()
        before = dict(self.manager.states)
        count = Place.objects.count()
        with (
            forbid_read_effects(),
            self.assertRaisesMessage(CommandError, "You cannot go that way."),
        ):
            inspect_exit_traversal(None, self.exit)
        self.assertEqual(self.manager.states, before)
        self.assertEqual(Place.objects.count(), count)

    def test_actual_initialize_writes_positive_control_never_run_on_read(self) -> None:
        self.attach(
            self.key,
            "initialize_state",
            "behaviors.tests.test_traversal_inspection.write_on_initialize",
            {"room_id": self.room.room_profile.pk},
        )
        count = Place.objects.count()
        self.refuse(INSPECTION_UNAVAILABLE)
        self.assertEqual(Place.objects.count(), count)
        state = self.manager.initialize_state_for_object(self.key)
        self.assertEqual(Place.objects.count(), count + 1)
        self.assertEqual(state.get_attribute("key_id"), "silver")
        self.refuse(INSPECTION_UNAVAILABLE, manager=self.manager)
        self.assertEqual(Place.objects.count(), count + 1)

    def test_unrelated_initialize_hooks_do_not_disable_builtin_inspection(self) -> None:
        self.lock.delete()
        for obj in (self.actor, self.exit, self.key):
            self.attach(
                obj,
                "initialize_state",
                "behaviors.tests.test_traversal_inspection.write_on_initialize",
            )
        count = Place.objects.count()
        self.read()
        self.read(manager=self.manager)
        self.assertEqual(Place.objects.count(), count)

    def test_unsupported_hook_unavailable_but_legacy_execution_unchanged(self) -> None:
        self.lock.delete()
        self.attach(
            self.exit, "can_traverse", "behaviors.tests.test_traversal_inspection.write_on_traverse"
        )
        count = Place.objects.count()
        self.refuse(INSPECTION_UNAVAILABLE)
        caller = self.manager.initialize_state_for_object(self.actor)
        exit_state = self.manager.initialize_state_for_object(self.exit)
        self.refuse(INSPECTION_UNAVAILABLE, manager=self.manager)
        check_exit_traversal(caller, exit_state)
        self.assertEqual(Place.objects.count(), count + 1)

    def test_real_arbitrary_hooks_preserve_loaded_order_and_first_non_none(self) -> None:
        self.lock.delete()
        path = "behaviors.tests.test_traversal_inspection.record_legacy_traverse"
        first = self.attach(self.exit, "can_traverse", path, {"label": "first", "result": None})
        second = self.attach(self.exit, "can_traverse", path, {"label": "second", "result": None})
        terminal = self.attach(
            self.exit, "can_traverse", path, {"label": "terminal", "result": False}
        )
        after = self.attach(
            self.exit,
            "can_traverse",
            "behaviors.tests.test_traversal_inspection.fail_if_legacy_traverse_reached",
        )
        caller = self.manager.initialize_state_for_object(self.actor)
        exit_state = self.manager.initialize_state_for_object(self.exit)
        # Test loaded order without promising a database ordering the loader does not have.
        exit_state.packages = [second, first, terminal, after]
        for result in (False, True):
            terminal.data = {"label": "terminal", "result": result}
            terminal.save(update_fields=["data"])
            exit_state.traversal_calls = []
            self.refuse(INSPECTION_UNAVAILABLE)
            self.refuse(INSPECTION_UNAVAILABLE, manager=self.manager)
            self.assertEqual(exit_state.traversal_calls, [])
            self.assertIs(exit_state.can_traverse(caller), result)
            self.assertEqual(exit_state.traversal_calls, ["second", "first", "terminal"])
            exit_state.traversal_calls = []
            if result:
                check_exit_traversal(caller, exit_state)
            else:
                with self.assertRaisesMessage(CommandError, "You cannot go that way."):
                    check_exit_traversal(caller, exit_state)
            self.assertEqual(exit_state.traversal_calls, ["second", "first", "terminal"])
        exit_state.packages = [second, first]
        exit_state.traversal_calls = []
        self.assertIs(exit_state.can_traverse(caller), True)
        self.assertEqual(exit_state.traversal_calls, ["second", "first"])

    def test_real_action_intent_cancel_prevents_traversal_execute_and_costs(self) -> None:
        from actions.definitions.movement import TraverseExitAction
        from flows.constants import EventName
        from flows.consts import FlowActionChoices
        from flows.factories import (
            FlowDefinitionFactory,
            FlowStepDefinitionFactory,
            TriggerDefinitionFactory,
            TriggerFactory,
        )

        self.lock.delete()
        self.attach(
            self.exit, "can_traverse", "behaviors.tests.test_traversal_inspection.write_on_traverse"
        )
        flow = FlowDefinitionFactory()
        root = FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "cancel_message", "op": "set", "value": "Halt at the door."},
        )
        FlowStepDefinitionFactory(
            flow=flow, parent_id=root.pk, action=FlowActionChoices.CANCEL_EVENT, parameters={}
        )
        definition = TriggerDefinitionFactory(
            event_name=EventName.ACTION_INTENT, flow_definition=flow
        )
        trigger = TriggerFactory(trigger_definition=definition, obj=self.room)
        action = TraverseExitAction(ap_cost=10_000_000)
        count = Place.objects.count()
        original_location = self.actor.location
        with ExitStack() as stack:
            for owner, name in (
                (TraverseExitAction, "execute"),
                (Action, "check_availability"),
                (Action, "_charge_costs"),
                (Action, "_emit_result"),
            ):
                stack.enter_context(
                    patch.object(
                        owner, name, side_effect=AssertionError(f"Cancelled action called {name}")
                    )
                )
            stack.enter_context(
                patch(
                    "actions.definitions.movement.traverse_exit",
                    side_effect=AssertionError("Cancelled action moved"),
                )
            )
            result = action.run(self.actor, target=self.exit)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "Halt at the door.")
        self.assertEqual(self.room.trigger_handler.fire_count(trigger.pk), 1)
        self.assertEqual(self.actor.location, original_location)
        self.assertEqual(Place.objects.count(), count)
        check_exit_traversal(
            self.manager.initialize_state_for_object(self.actor),
            self.manager.initialize_state_for_object(self.exit),
        )
        self.assertEqual(Place.objects.count(), count + 1)

    def test_exact_path_not_definition_name_and_property_not_invoked(self) -> None:
        self.lock.definition.name = "instance_entrance"
        self.lock.definition.save(update_fields=["name"])
        self.read()
        self.lock.data = {"attribute": "contents", "value": "silver"}
        self.lock.save(update_fields=["data"])
        self.refuse(INSPECTION_UNAVAILABLE)
        self.manager.initialize_state_for_object(self.actor)
        self.refuse(INSPECTION_UNAVAILABLE, manager=self.manager)

    def test_cached_custom_equality_and_cycles_are_never_evaluated(self) -> None:
        class DangerousValue:
            __hash__ = None

            def __eq__(self, other: object) -> bool:
                message = "Read invoked arbitrary equality"
                raise AssertionError(message)

        state = self.manager.initialize_state_for_object(self.key)
        state.set_attribute("key_id", DangerousValue())
        self.refuse(INSPECTION_UNAVAILABLE, manager=self.manager)
        cycle = []
        cycle.append(cycle)
        state.set_attribute("key_id", cycle)
        self.refuse(INSPECTION_UNAVAILABLE, manager=self.manager)

    def test_actor_match_short_circuits_unsupported_carried_initialization(self) -> None:
        self.attach(
            self.actor,
            "initialize_state",
            "behaviors.state_values_package.initialize_state",
            {"key_id": "silver"},
        )
        self.attach(
            self.key,
            "initialize_state",
            "behaviors.tests.test_traversal_inspection.write_on_initialize",
        )
        self.read()

    def test_multiple_none_matching_hooks_continue_to_unsupported(self) -> None:
        self.attach(
            self.exit,
            "can_traverse",
            "behaviors.matching_value_package.require_matching_value",
            {"attribute": "key_id", "value": "silver"},
        )
        self.read()
        self.attach(
            self.exit, "can_traverse", "behaviors.tests.test_traversal_inspection.false_traverse"
        )
        self.refuse(INSPECTION_UNAVAILABLE)
        self.assertFalse(
            self.manager.initialize_state_for_object(self.exit).can_traverse(
                self.manager.initialize_state_for_object(self.actor)
            )
        )

    def test_publication_lock_and_destination_order_uses_shared_builtins(self) -> None:
        self.lock.delete()
        caller = self.manager.initialize_state_for_object(self.actor)
        exit_state = self.manager.initialize_state_for_object(self.exit)
        original_location = self.actor.location
        self.dest.room_profile.published_at = None
        self.dest.room_profile.save(update_fields=["published_at"])
        self.assertTrue(exit_hidden_from_viewer(self.exit, self.actor))
        self.refuse("You cannot go that way.")
        self.assertIs(exit_state.can_traverse(caller), False)
        with self.assertRaisesMessage(CommandError, "You cannot go that way."):
            check_exit_traversal(caller, exit_state)
        self.dest.room_profile.published_at = timezone.now()
        self.dest.room_profile.save(update_fields=["published_at"])
        self.assertFalse(exit_hidden_from_viewer(self.exit, self.actor))
        self.read()
        check_exit_traversal(caller, exit_state)
        self.exit.db.locked = True
        self.refuse("You cannot go that way.")
        self.assertIs(exit_state.can_traverse(caller), False)
        with self.assertRaisesMessage(CommandError, "You cannot go that way."):
            check_exit_traversal(caller, exit_state)
        self.exit.db.locked = False
        self.exit.destination = None
        self.refuse("That exit doesn't lead anywhere.")
        self.assertIs(exit_state.can_traverse(caller), True)
        with self.assertRaisesMessage(CommandError, "That exit doesn't lead anywhere."):
            check_exit_traversal(caller, exit_state)
        self.assertEqual(self.actor.location, original_location)

    def overload(self) -> None:
        self.lock.delete()
        ItemInstanceFactory(
            template=ItemTemplateFactory(weight=carry_capacity(self.actor) * 3),
            holder_character_sheet=self.sheet,
            game_object=self.key,
        )
        self.actor.carried_items.invalidate()
        FatiguePool.objects.filter(character_sheet=self.sheet).delete()

    def test_overload_missing_pool_and_zero_capacity_do_not_create(self) -> None:
        self.overload()
        with patch("world.fatigue.services.get_fatigue_capacity", return_value=0):
            self.read()
            with forbid_read_effects():
                self.assertEqual(get_fatigue_zone_readonly(self.sheet, "physical"), "fresh")
        self.assertFalse(FatiguePool.objects.filter(character_sheet=self.sheet).exists())
        self.read()
        self.assertFalse(FatiguePool.objects.filter(character_sheet=self.sheet).exists())
        pool = FatiguePool.objects.create(character_sheet=self.sheet, physical_current=10000)
        self.refuse(OVERLOADED_EXHAUSTED_MSG)
        with self.assertRaisesMessage(CommandError, OVERLOADED_EXHAUSTED_MSG):
            check_exit_traversal(
                self.manager.initialize_state_for_object(self.actor),
                self.manager.initialize_state_for_object(self.exit),
            )
        pool.physical_current = 0
        pool.save(update_fields=["physical_current"])
        self.read()

    def test_read_zone_matches_execution_zone_with_existing_pool(self) -> None:
        pool = FatiguePool.objects.create(character_sheet=self.sheet)
        for rested in (False, True):
            for current in (0, 1, 10000):
                pool.physical_current = current
                pool.well_rested = rested
                pool.save(update_fields=["physical_current", "well_rested"])
                with forbid_read_effects():
                    actual = get_fatigue_zone_readonly(self.sheet, "physical")
                self.assertEqual(actual, get_fatigue_zone(self.sheet, "physical"))

    def test_execution_missing_pool_still_creates(self) -> None:
        self.overload()
        self.read()
        self.assertFalse(FatiguePool.objects.filter(character_sheet=self.sheet).exists())
        check_exit_traversal(
            self.manager.initialize_state_for_object(self.actor),
            self.manager.initialize_state_for_object(self.exit),
        )
        self.assertTrue(FatiguePool.objects.filter(character_sheet=self.sheet).exists())

    def test_instance_admission_owner_participant_bystander_and_termination(self) -> None:
        self.lock.delete()
        spawned = spawn_instanced_room(
            name="Inspection room",
            description="",
            owner=self.sheet,
            return_location=self.room,
            source_key="test:inspection",
            anchor_room=self.room,
        )
        spawned.room_profile.published_at = timezone.now()
        spawned.room_profile.save(update_fields=["published_at"])
        entrance = ObjectDB.objects.get(
            db_typeclass_path="typeclasses.exits.Exit",
            db_location=self.room,
            db_destination=spawned,
        )
        participant = CharacterSheetFactory().character
        participant.location = self.room
        bystander = CharacterSheetFactory().character
        bystander.location = self.room
        mission = MissionInstanceFactory(spawned_room_id=spawned.pk)
        MissionParticipantFactory(instance=mission, character=participant.character_sheet)
        self.attach(
            entrance, "can_traverse", "behaviors.tests.test_traversal_inspection.write_on_traverse"
        )
        count = Place.objects.count()
        for actor in (self.actor, participant):
            self.assertFalse(exit_hidden_from_viewer(entrance, actor))
            self.read(actor=actor, exit_obj=entrance)
            caller = self.manager.initialize_state_for_object(actor)
            exit_state = self.manager.initialize_state_for_object(entrance)
            self.assertIs(exit_state.can_traverse(caller), True)
            check_exit_traversal(caller, exit_state)
            self.assertEqual(actor.location, self.room)
        self.assertEqual(Place.objects.count(), count)
        self.assertTrue(exit_hidden_from_viewer(entrance, bystander))
        self.refuse("You cannot go that way.", actor=bystander, exit_obj=entrance)
        caller = self.manager.initialize_state_for_object(bystander)
        exit_state = self.manager.get_state_by_pk(entrance.pk)
        self.assertIs(exit_state.can_traverse(caller), False)
        with self.assertRaisesMessage(CommandError, "You cannot go that way."):
            check_exit_traversal(caller, exit_state)
        self.assertEqual(bystander.location, self.room)
        self.assertEqual(Place.objects.count(), count)

    def test_gm_account_admission_and_defunct_attached_gate(self) -> None:
        self.lock.delete()
        gm = GMProfileFactory()
        self.actor.db_account = gm.account
        self.actor.save(update_fields=["db_account"])
        spawned = spawn_instanced_room(
            name="GM inspection",
            description="",
            owner=None,
            return_location=self.room,
            source_key="test:gm-inspection",
            gm_owner=gm,
            anchor_room=self.room,
        )
        spawned.room_profile.published_at = timezone.now()
        spawned.room_profile.save(update_fields=["published_at"])
        entrance = ObjectDB.objects.get(
            db_typeclass_path="typeclasses.exits.Exit",
            db_location=self.room,
            db_destination=spawned,
        )
        self.assertFalse(exit_hidden_from_viewer(entrance, self.actor))
        self.read(exit_obj=entrance)
        caller = self.manager.initialize_state_for_object(self.actor)
        exit_state = self.manager.initialize_state_for_object(entrance)
        self.assertIs(exit_state.can_traverse(caller), True)
        check_exit_traversal(caller, exit_state)
        instance = InstancedRoom.objects.get(room_id=spawned.pk)
        instance.gm_owner = None
        instance.save(update_fields=["gm_owner"])
        self.assertTrue(exit_hidden_from_viewer(entrance, self.actor))
        self.refuse("You cannot go that way.", exit_obj=entrance)
        self.assertIs(exit_state.can_traverse(caller), False)
        with self.assertRaisesMessage(CommandError, "You cannot go that way."):
            check_exit_traversal(caller, exit_state)
        self.attach(
            self.exit, "can_traverse", "behaviors.instance_entrance_package.restrict_to_run"
        )
        self.refuse("You cannot go that way.")
        defunct = self.manager.initialize_state_for_object(self.exit)
        self.assertIs(defunct.can_traverse(caller), False)
        with self.assertRaisesMessage(CommandError, "You cannot go that way."):
            check_exit_traversal(caller, defunct)
        self.assertEqual(self.actor.location, self.room)
