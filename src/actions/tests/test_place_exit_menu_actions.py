"""Typed room-target journeys through registry REST and current shared gates."""
# Loop callbacks run synchronously before the next fixture mutation; compound
# assertions keep each observed journey outcome together.
# ruff: noqa: B023, PT018, PLR0915

import re
from unittest.mock import DEFAULT, patch
import uuid

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from actions.constants import EnhancementSourceType
from actions.definitions.movement import TravelAction, TraverseExitAction
from actions.definitions.perception import LookAction
from actions.definitions.places import JoinPlaceAction, LeavePlaceAction
from actions.definitions.room_target_helpers import (
    UNAVAILABLE,
    apply_room_enhancements,
    emit_room_intent,
)
from actions.models import ActionEnhancement, ModifyKwargsConfig
from actions.types import ActionContext
from behaviors.models import BehaviorPackageDefinition, BehaviorPackageInstance
from behaviors.tests.test_traversal_inspection import forbid_read_effects
from behaviors.traversal_inspection import INSPECTION_UNAVAILABLE
from evennia_extensions.constants import ExitKind
from evennia_extensions.factories import AccountFactory, ObjectDBFactory, RoomProfileFactory
from evennia_extensions.models import ExitProfile, ObjectDisplayData
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.emit import emit_event
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from flows.scene_data_manager import SceneDataManager
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import register_detection
from world.fatigue.models import FatiguePool
from world.instances.models import InstancedRoom
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.services.encumbrance import carry_capacity, charge_move_fatigue
from world.locations.constants import LocationRole
from world.locations.services import grant_tenancy
from world.mechanics.constants import ChallengeType
from world.mechanics.factories import ChallengeTemplateFactory
from world.mechanics.models import ChallengeInstance
from world.missions.factories import MissionInstanceFactory, MissionParticipantFactory
from world.npc_services.models import ExpulsionBar
from world.room_features.models import ExitBarsDetails
from world.room_features.services import react_to_unauthorized_entry
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import PlaceStatus
from world.scenes.factories import PersonaFactory, PlaceFactory
from world.scenes.models import Scene
from world.scenes.place_models import Place, PlacePresence


def write_on_initialize(state, pkg):
    PlaceFactory(
        room=state.obj.location.room_profile, name=f"initialize sentinel {Place.objects.count()}"
    )


def read_sql_only(execute, sql, params, many, context):
    words = set(re.findall(r"[A-Z_]+", sql.upper()))
    assert not words.intersection(
        {
            "INSERT",
            "UPDATE",
            "DELETE",
            "REPLACE",
            "MERGE",
            "CREATE",
            "ALTER",
            "DROP",
            "TRUNCATE",
            "VACUUM",
            "PRAGMA",
            "LOCK",
        }
    ), sql
    assert sql.lstrip().upper().startswith(("SELECT", "WITH")), sql
    assert not re.search(r"FOR\s+(UPDATE|SHARE|NO\s+KEY|KEY\s+SHARE)", sql.upper()), sql
    return execute(sql, params, many, context)


class PlaceExitMenuActionTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.profile = RoomProfileFactory(objectdb=self.room, published_at=timezone.now())
        self.destination = RoomProfileFactory(objectdb=self.remote, published_at=timezone.now())
        entry = RosterEntryFactory()
        self.sheet = entry.character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        self.account = AccountFactory(is_staff=False)
        RosterTenureFactory(
            roster_entry=entry, player_data=PlayerDataFactory(account=self.account), end_date=None
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.place = PlaceFactory(room=self.profile)
        self.other_place = PlaceFactory(room=self.profile)
        self.exit = ObjectDBFactory(
            db_typeclass_path="typeclasses.exits.Exit", location=self.room, destination=self.remote
        )
        self.obj = ObjectDBFactory(location=self.room)
        self.join, self.leave = JoinPlaceAction(), LeavePlaceAction()
        self.go, self.look = TraverseExitAction(), LookAction()

    def wire(self, kind, obj):
        return {"menu_target": {"kind": kind, "target_id": obj.pk}}

    def read(self, action, values):
        return action.check_availability(self.actor, context={"kwargs": values})

    def post(self, key, values):
        response = self.client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {"ref": {"backend": "registry", "registry_key": key}, "kwargs": values},
            format="json",
        )
        assert response.status_code == 200, response.data
        return response.data

    def pure(self, function):
        counts = (
            Place.objects.count(),
            Scene.objects.count(),
            PlacePresence.objects.count(),
            FatiguePool.objects.count(),
        )
        with (
            connection.execute_wrapper(read_sql_only),
            forbid_read_effects(),
            CaptureQueriesContext(connection),
        ):
            result = function()
        assert counts == (
            Place.objects.count(),
            Scene.objects.count(),
            PlacePresence.objects.count(),
            FatiguePool.objects.count(),
        )
        return result

    def attach(self, obj, hook, path, data=None):
        definition = BehaviorPackageDefinition.objects.create(
            name=f"action-inspection-{BehaviorPackageDefinition.objects.count()}",
            service_function_path=path,
        )
        return BehaviorPackageInstance.objects.create(
            definition=definition, obj=obj, hook=hook, data=data
        )

    def trigger(self, key, *, event=EventName.ACTION_INTENT, steps=(), room=None):
        flow = FlowDefinitionFactory()
        parent = None
        for action, parameters, variable in steps:
            step = FlowStepDefinitionFactory(
                flow=flow,
                parent_id=parent,
                action=action,
                parameters=parameters,
                variable_name=variable,
            )
            parent = step.pk
        definition = TriggerDefinitionFactory(
            event_name=event,
            flow_definition=flow,
            base_filter_condition={"path": "action_key", "op": "==", "value": key},
        )
        location = room or self.room
        trigger = TriggerFactory(trigger_definition=definition, obj=location)
        location.trigger_handler.refresh()
        return trigger

    def remove_trigger(self, trigger, room=None):
        trigger.delete()
        (room or self.room).trigger_handler.refresh()

    def target_change(self, key, target, *, service=False):
        steps = (
            (
                (
                    FlowActionChoices.CALL_SERVICE_FUNCTION,
                    {"payload": "@payload", "object_id": target.pk},
                    "flows.service_functions.actions.redirect_action_target",
                ),
            )
            if service
            else (
                (
                    FlowActionChoices.MODIFY_PAYLOAD,
                    {"field": "target", "op": "set", "value": target.pk},
                    "",
                ),
            )
        )
        return self.trigger(key, steps=steps)

    def conceal(self, target):
        return ConditionInstanceFactory(
            target=target,
            condition=ConditionTemplateFactory(
                category=ConditionCategoryFactory(conceals_from_perception=True)
            ),
        )

    def deny_current(self, action, key, values, reason=None):
        availability = self.pure(lambda: self.read(action, values))
        assert not availability.available
        data = self.post(key, values)
        assert not data["success"]
        assert data["message"] == "; ".join(availability.reasons)
        if reason is not None:
            assert data["message"] == reason
        assert data["data"] is None
        assert self.actor.location == self.room
        return data

    def load(self, weight):
        obj = ObjectDBFactory(location=self.actor)
        item = ItemInstanceFactory(
            game_object=obj,
            holder_character_sheet=self.sheet,
            template=ItemTemplateFactory(weight=weight),
        )
        self.actor.carried_items.invalidate()
        return item

    def admitted_mission(self):
        instance = InstancedRoom.objects.create(
            room=self.destination, owner=RosterEntryFactory().character_sheet
        )
        mission = MissionInstanceFactory(spawned_room_id=self.remote.pk)
        participant = MissionParticipantFactory(instance=mission, character=self.sheet)
        self.attach(
            self.exit, "can_traverse", "behaviors.instance_entrance_package.restrict_to_run"
        )
        return instance, participant

    def test_real_rest_join_switch_leave_without_scene_or_capacity(self):
        values = self.wire("places", self.place)
        assert self.pure(lambda: self.join.is_applicable(self.actor, kwargs=values))
        assert not self.pure(lambda: self.leave.is_applicable(self.actor, kwargs=values))
        assert self.pure(lambda: self.read(self.join, values)).available
        scenes = Scene.objects.count()
        joined = self.post("join_place", values)
        assert joined["success"]
        assert (
            joined["data"]["presence_id"]
            == PlacePresence.objects.get(place=self.place, persona=self.sheet.primary_persona).pk
        )
        assert not self.read(self.join, values).available
        assert not self.post("join_place", values)["success"]
        assert self.read(self.leave, values).available
        for _index in range(25):
            PlacePresence.objects.create(place=self.other_place, persona=PersonaFactory())
        assert self.post("join_place", self.wire("places", self.other_place))["success"]
        assert not PlacePresence.objects.filter(
            place=self.place, persona=self.sheet.primary_persona
        ).exists()
        assert not self.post("leave_place", values)["success"]
        assert self.post("leave_place", self.wire("places", self.other_place))["success"]
        assert Scene.objects.count() == scenes
        assert self.join.run(self.actor, place=self.place).success
        assert self.join.run(self.actor, place=self.place).success

    def test_wrong_domains_malformed_values_and_collisions(self):
        for action, kind, obj in (
            (self.join, "places", self.place),
            (self.leave, "places", self.place),
            (self.go, "exits", self.exit),
            (self.look, "objects", self.obj),
        ):
            for value in (None, True, False, "1", 0, -1, [], {}):
                values = {"menu_target": {"kind": kind, "target_id": value}}
                assert not self.pure(lambda: self.read(action, values)).available
                assert self.post(action.key, values)["message"] == UNAVAILABLE
            for extra in (
                "target",
                "target_id",
                "place",
                "place_id",
                "item",
                "item_id",
                "item_instance_id",
                "target_persona_id",
                "owner_persona_id",
                "container_item_id",
                "pending_inputs",
            ):
                values = {**self.wire(kind, obj), extra: obj.pk}
                assert not self.read(action, values).available
                assert not self.post(action.key, values)["success"]
            for extra in ("owner_persona_id", "container_item_id", "label"):
                values = self.wire(kind, obj)
                values["menu_target"][extra] = obj.pk
                assert not self.read(action, values).available
        assert not self.read(self.go, self.wire("objects", self.exit)).available
        assert not self.read(self.join, self.wire("objects", self.obj)).available
        assert not self.read(self.look, self.wire("places", self.place)).available
        collision = PlaceFactory(pk=self.obj.pk, room=self.profile)
        assert self.join.is_applicable(self.actor, kwargs=self.wire("places", collision))
        assert self.look.is_applicable(self.actor, kwargs=self.wire("objects", self.obj))
        assert not self.go.is_applicable(self.actor, kwargs=self.wire("exits", collision))

    def test_locked_dangling_hidden_and_real_go(self):
        values = self.wire("exits", self.exit)
        self.exit.db.locked = True
        assert self.go.is_applicable(self.actor, kwargs=values)
        self.deny_current(self.go, self.go.key, values, "You cannot go that way.")
        self.exit.db.locked = False
        self.exit.destination = None
        self.deny_current(self.go, self.go.key, values, "That exit doesn't lead anywhere.")
        self.exit.destination = self.remote
        self.destination.published_at = None
        self.destination.save(update_fields=["published_at"])
        assert not self.go.is_applicable(self.actor, kwargs=values)
        assert self.post(self.go.key, values)["message"] == UNAVAILABLE
        self.destination.published_at = timezone.now()
        self.destination.save(update_fields=["published_at"])
        assert self.pure(lambda: self.read(self.go, values)).available
        with patch.object(self.actor, "move_to", wraps=self.actor.move_to) as moved:
            assert self.post(self.go.key, values)["success"]
        moved.assert_called()
        assert self.actor.location == self.remote

    def test_active_persona_membership_and_stale_place_scope(self):
        values = self.wire("places", self.place)
        old = self.sheet.primary_persona
        PlacePresence.objects.create(place=self.place, persona=old)
        assert self.leave.is_applicable(self.actor, kwargs=values)
        self.sheet.active_persona = PersonaFactory(character_sheet=self.sheet)
        self.sheet.save(update_fields=["active_persona"])
        assert self.join.is_applicable(self.actor, kwargs=values)
        assert not self.leave.is_applicable(self.actor, kwargs=values)
        assert not self.post(self.leave.key, values)["success"]
        assert PlacePresence.objects.filter(place=self.place, persona=old).exists()
        for status in (PlaceStatus.HIDDEN, PlaceStatus.REMOVED):
            self.place.status = status
            self.place.save(update_fields=["status"])
            assert not self.read(self.join, values).available
            assert self.post(self.join.key, values)["message"] == UNAVAILABLE
        self.place.status = PlaceStatus.ACTIVE
        self.place.room = self.destination
        self.place.save(update_fields=["status", "room"])
        assert self.post(self.join.key, values)["message"] == UNAVAILABLE

    def test_instance_admission_changes_without_authority_cache(self):
        other = RosterEntryFactory().character_sheet
        instance = InstancedRoom.objects.create(room=self.destination, owner=other)
        values = self.wire("exits", self.exit)
        assert not self.go.is_applicable(self.actor, kwargs=values)
        assert self.post(self.go.key, values)["message"] == UNAVAILABLE
        instance.owner = self.sheet
        instance.save(update_fields=["owner"])
        self.attach(
            self.exit, "can_traverse", "behaviors.instance_entrance_package.restrict_to_run"
        )
        assert self.pure(lambda: self.read(self.go, values)).available
        instance.owner = other
        instance.save(update_fields=["owner"])
        assert not self.read(self.go, values).available
        assert self.post(self.go.key, values)["message"] == UNAVAILABLE

    def test_initializer_writes_never_run_on_cold_or_warm_reads(self):
        for obj in (self.actor, self.obj, self.exit):
            self.attach(
                obj,
                "initialize_state",
                "actions.tests.test_place_exit_menu_actions.write_on_initialize",
            )
        for warm in (False, True):
            if warm:
                before = Place.objects.count()
                manager = SceneDataManager()
                for obj in (self.actor, self.obj, self.exit):
                    manager.initialize_state_for_object(obj)
                assert Place.objects.count() == before + 3
                self.room.scene_data = manager
            for action, kind, target in (
                (self.join, "places", self.place),
                (self.look, "objects", self.obj),
                (self.look, "exits", self.exit),
                (self.go, "exits", self.exit),
            ):
                values = self.wire(kind, target)
                assert self.pure(lambda: action.is_applicable(self.actor, kwargs=values))
                assert self.pure(lambda: self.read(action, values)).available

    def test_typed_look_existing_renderer_and_routes(self):
        ObjectDisplayData.objects.update_or_create(
            object=self.obj, defaults={"permanent_description": "A carved stone."}
        )
        self.attach(
            self.obj,
            "initialize_state",
            "behaviors.state_values_package.initialize_state",
            {"values": {"description": "A carved stone."}},
        )
        typed = self.post("look", self.wire("objects", self.obj))
        existing = self.post("look", {"target": self.obj.pk})
        assert typed["success"] and existing["success"]
        assert typed["message"] == existing["message"]
        assert "A carved stone." in typed["message"]
        assert self.post("look", self.wire("exits", self.exit))["success"]
        self.obj.location = self.remote
        assert self.post("look", self.wire("objects", self.obj))["message"] == UNAVAILABLE

    def test_authored_cancel_all_four_verbs_single_intent_before_cost(self):
        for action, kind, target in (
            (self.join, "places", self.place),
            (self.leave, "places", self.place),
            (self.go, "exits", self.exit),
            (self.look, "objects", self.obj),
        ):
            if action == self.leave:
                PlacePresence.objects.get_or_create(
                    place=self.place, persona=self.sheet.primary_persona
                )
            trigger = self.trigger(
                action.key,
                steps=(
                    (
                        FlowActionChoices.MODIFY_PAYLOAD,
                        {"field": "cancel_message", "op": "set", "value": "The wards refuse."},
                        "",
                    ),
                    (FlowActionChoices.CANCEL_EVENT, {}, ""),
                ),
            )
            before = list(PlacePresence.objects.order_by("pk").values_list("pk", flat=True))
            with (
                patch.object(action, "_charge_costs", side_effect=AssertionError("cancel charged")),
                patch("flows.emit.emit_event", wraps=emit_event) as events,
            ):
                result = action.run(self.actor, **self.wire(kind, target))
            assert not result.success and result.message == "The wards refuse."
            assert [call.args[0] for call in events.call_args_list].count(
                EventName.ACTION_INTENT
            ) == 1
            assert EventName.ACTION_RESULT not in [call.args[0] for call in events.call_args_list]
            with patch(
                "actions.base.Action._charge_costs",
                side_effect=AssertionError("REST cancel charged"),
            ):
                data = self.post(action.key, self.wire(kind, target))
            assert not data["success"] and data["message"] == result.message
            assert self.room.trigger_handler.fire_count(trigger.pk) == 2
            assert before == list(PlacePresence.objects.order_by("pk").values_list("pk", flat=True))
            assert self.actor.location == self.room
            self.remove_trigger(trigger)

    def test_authored_place_integer_redirect_and_object_domain_refusal(self):
        captured = []

        def observe(event, payload, **kwargs):
            if event == EventName.ACTION_INTENT:
                captured.append(payload.target)
            return emit_event(event, payload, **kwargs)

        trigger = self.target_change("join_place", self.other_place)
        with patch("flows.emit.emit_event", side_effect=observe):
            assert self.post("join_place", self.wire("places", self.place))["success"]
        assert captured == [self.place] and isinstance(captured[0], Place)
        assert PlacePresence.objects.filter(
            place=self.other_place, persona=self.sheet.primary_persona
        ).exists()
        assert not PlacePresence.objects.filter(
            place=self.place, persona=self.sheet.primary_persona
        ).exists()
        self.remove_trigger(trigger)
        trigger = self.target_change("join_place", self.obj, service=True)
        assert self.post("join_place", self.wire("places", self.place))["message"] == UNAVAILABLE
        self.remove_trigger(trigger)

    def test_exit_and_look_redirects_revalidate_original_domain(self):
        values = self.wire("exits", self.exit)
        second = ObjectDBFactory(
            db_typeclass_path="typeclasses.exits.Exit", location=self.room, destination=self.remote
        )
        second.db.locked = True
        for service in (False, True):
            trigger = self.target_change(self.go.key, second, service=service)
            assert self.post(self.go.key, values)["message"] == "You cannot go that way."
            self.remove_trigger(trigger)
        for target in (self.obj, second):
            target.location = self.remote
            trigger = self.target_change(self.go.key, target, service=True)
            assert self.post(self.go.key, values)["message"] == UNAVAILABLE
            self.remove_trigger(trigger)
            target.location = self.room
        condition = self.conceal(second)
        trigger = self.target_change(self.go.key, second, service=True)
        assert self.post(self.go.key, values)["message"] == UNAVAILABLE
        self.remove_trigger(trigger)
        condition.delete()
        for target, success in ((self.exit, False), (self.obj, True)):
            trigger = self.target_change("look", target, service=True)
            data = self.post("look", self.wire("objects", self.obj))
            assert data["success"] is success
            if not success:
                assert data["message"] == UNAVAILABLE
            self.remove_trigger(trigger)

    def test_real_enhancement_transform_reaches_strict_gate(self):
        condition = ConditionTemplateFactory()
        for action, kind, target in (
            (self.join, "places", self.place),
            (self.leave, "places", self.place),
            (self.go, "exits", self.exit),
            (self.look, "objects", self.obj),
        ):
            enhancement = ActionEnhancement.objects.create(
                base_action_key=action.key,
                variant_name=f"typed-{action.key}",
                source_type=EnhancementSourceType.CONDITION,
                condition=condition,
            )
            ModifyKwargsConfig.objects.create(
                enhancement=enhancement,
                kwarg_name="menu_target",
                transform="uppercase",
                execution_order=0,
            )
            with patch.object(
                type(enhancement), "apply", autospec=True, side_effect=type(enhancement).apply
            ) as applied:
                result = action.run(self.actor, enhancements=[enhancement], menu_target="places")
            assert not result.success and result.message == UNAVAILABLE
            assert applied.call_count == 1
            if action == self.leave:
                PlacePresence.objects.get_or_create(
                    place=self.place, persona=self.sheet.primary_persona
                )
            assert action.run(
                self.actor, enhancements=[enhancement], **self.wire(kind, target)
            ).success
            self.actor.location = self.room

    def test_adapter_instance_domain_wire_changes_and_enhancement_binding(self):
        def context(action, values):
            return ActionContext(
                action=action,
                actor=self.actor,
                target=None,
                kwargs=values,
                scene_data=SceneDataManager(),
            )

        ctx = context(self.join, self.wire("places", self.place))

        def redirect(ctx, actor):
            assert ctx.kwargs["target"] == self.place
            ctx.kwargs["target"] = self.other_place

        assert emit_room_intent(ctx, self.actor, redirect, self.join.menu_kinds) is None
        assert ctx.kwargs == self.wire("places", self.other_place)
        for redirected in (self.obj, self.sheet.primary_persona, True, None):
            ctx = context(self.join, self.wire("places", self.place))

            def invalid(ctx, actor):
                ctx.kwargs["target"] = redirected

            emit_room_intent(ctx, self.actor, invalid, self.join.menu_kinds)
            assert ctx.kwargs["menu_target"] is None and "target" not in ctx.kwargs
        for conflict in (False, True):
            ctx = context(self.join, self.wire("places", self.place))

            def edit(ctx, actor):
                ctx.kwargs["menu_target"] = self.wire("places", self.other_place)["menu_target"]
                if conflict:
                    ctx.kwargs["target"] = self.other_place

            emit_room_intent(ctx, self.actor, edit, self.join.menu_kinds)
            assert (
                ctx.kwargs["menu_target"] is None
                if conflict
                else ctx.kwargs == self.wire("places", self.other_place)
            )
        for original in (self.wire("objects", self.obj), {"menu_target": None}, {}):
            ctx = context(self.look, original)

            def changed(ctx, actor, enhancements):
                ctx.kwargs["menu_target"] = self.wire("exits", self.exit)["menu_target"]

            apply_room_enhancements(ctx, self.actor, [], changed, self.look.menu_kinds)
            assert ctx.kwargs["menu_target"] is None
            assert not self.read(self.look, ctx.kwargs).available

    def test_concealment_absence_remote_equivalence_and_detection(self):
        for action, kind, target in (
            (self.go, "exits", self.exit),
            (self.look, "objects", self.obj),
        ):
            values = self.wire(kind, target)
            condition = self.conceal(target)
            concealed = self.deny_current(action, action.key, values, UNAVAILABLE)
            absent = self.deny_current(
                action,
                action.key,
                {"menu_target": {"kind": kind, "target_id": 999999999}},
                UNAVAILABLE,
            )
            assert concealed == absent
            register_detection(self.sheet, target)
            assert self.pure(lambda: self.read(action, values)).available
            condition.delete()
            target.location = self.remote
            assert self.deny_current(action, action.key, values, UNAVAILABLE) == absent
            target.location = self.room

    def test_stale_actor_exit_publication_and_membership_dispatch(self):
        values = self.wire("places", self.place)
        assert self.read(self.join, values).available
        self.actor.location = self.remote
        assert self.post(self.join.key, values)["message"] == UNAVAILABLE
        self.actor.location = self.room
        PlacePresence.objects.create(place=self.place, persona=self.sheet.primary_persona)
        assert self.post(self.join.key, values)["message"] == UNAVAILABLE
        assert self.read(self.leave, values).available
        PlacePresence.objects.filter(place=self.place, persona=self.sheet.primary_persona).delete()
        assert self.post(self.leave.key, values)["message"] == UNAVAILABLE
        values = self.wire("exits", self.exit)
        assert self.read(self.go, values).available
        self.exit.location = self.remote
        assert self.post(self.go.key, values)["message"] == UNAVAILABLE
        self.exit.location = self.room
        self.destination.published_at = None
        self.destination.save(update_fields=["published_at"])
        assert self.post(self.go.key, values)["message"] == UNAVAILABLE

    def test_window_bars_tenancy_expulsion_and_inhibitors(self):
        values = self.wire("exits", self.exit)
        profile = ExitProfile.get_or_create_for_exit(self.exit)
        profile.exit_kind, profile.is_open = ExitKind.WINDOW, False
        profile.save()
        self.deny_current(self.go, self.go.key, values, "You cannot go that way.")
        profile.is_open = True
        profile.save()
        assert self.pure(lambda: self.read(self.go, values)).available
        bars = ExitBarsDetails.objects.create(exit_profile=profile, level=1)
        self.deny_current(self.go, self.go.key, values, "You cannot go that way.")
        grant_tenancy(
            kind=LocationRole.TENANT,
            room_profile=self.profile,
            tenant_persona=self.sheet.primary_persona,
        )
        assert self.pure(lambda: self.read(self.go, values)).available
        bars.delete()
        bar = ExpulsionBar.objects.create(
            room=self.destination, barred_sheet=self.sheet, imposed_by=PersonaFactory()
        )
        self.deny_current(self.go, self.go.key, values, "You are barred from entering there.")
        bar.lifted_at = timezone.now()
        bar.save(update_fields=["lifted_at"])
        challenge = ChallengeInstance.objects.create(
            template=ChallengeTemplateFactory(challenge_type=ChallengeType.INHIBITOR),
            location=self.exit,
            target_object=self.exit,
            is_active=True,
            is_revealed=False,
        )
        assert self.pure(lambda: self.read(self.go, values)).available
        challenge.is_revealed = True
        challenge.save(update_fields=["is_revealed"])
        self.deny_current(self.go, self.go.key, values, "The way is blocked.")
        challenge.is_active = False
        challenge.save(update_fields=["is_active"])
        assert self.pure(lambda: self.read(self.go, values)).available

    def test_overload_missing_pool_pure_reads_and_exhaustion(self):
        self.load(carry_capacity(self.actor) * 3)
        FatiguePool.objects.filter(character_sheet=self.sheet).delete()
        values = self.wire("exits", self.exit)
        assert self.pure(lambda: self.read(self.go, values)).available
        assert not FatiguePool.objects.filter(character_sheet=self.sheet).exists()
        pool = FatiguePool.objects.create(character_sheet=self.sheet, physical_current=1_000_000)
        refusal = self.deny_current(self.go, self.go.key, values)
        assert "Drop something" in refusal["message"]
        assert pool.physical_current == 1_000_000

    def test_private_published_arrival_effects_broadcast_and_place_scope(self):
        from actions.definitions import movement

        self.destination.is_public = False
        self.destination.save(update_fields=["is_public"])
        self.load(carry_capacity(self.actor) + 1)
        pool, _ = FatiguePool.objects.get_or_create(character_sheet=self.sheet)
        PlacePresence.objects.create(place=self.place, persona=self.sheet.primary_persona)
        intent = self.trigger(self.go.key)
        result_trigger = self.trigger(self.go.key, event=EventName.ACTION_RESULT, room=self.remote)
        with (
            patch(
                "actions.definitions.movement.traverse_exit", wraps=movement.traverse_exit
            ) as travel,
            patch(
                "actions.definitions.movement.send_room_state", wraps=movement.send_room_state
            ) as broadcast,
            patch.object(self.exit, "at_traverse", wraps=self.exit.at_traverse) as hook,
            patch(
                "world.items.services.encumbrance.charge_move_fatigue", wraps=charge_move_fatigue
            ) as fatigue,
            patch(
                "world.room_features.services.react_to_unauthorized_entry",
                wraps=react_to_unauthorized_entry,
            ) as wards,
        ):
            assert self.post(self.go.key, self.wire("exits", self.exit))["success"]
        travel.assert_called_once()
        hook.assert_called_once()
        fatigue.assert_called_once()
        wards.assert_called_once_with(self.actor, self.remote)
        broadcast.assert_called_once()
        assert self.actor.location == self.remote and pool.physical_current > 0
        assert PlacePresence.objects.filter(
            place=self.place, persona=self.sheet.primary_persona
        ).exists()
        for action in (self.join, self.leave):
            values = self.wire("places", self.place)
            assert not action.is_applicable(self.actor, kwargs=values)
            assert not self.read(action, values).available
            assert not self.post(action.key, values)["success"]
        current = PlaceFactory(room=self.destination)
        for action in (self.join, self.leave):
            values = self.wire("places", current)
            assert self.read(action, values).available
            assert self.post(action.key, values)["success"]
        assert PlacePresence.objects.filter(
            place=self.place, persona=self.sheet.primary_persona
        ).exists()
        assert not PlacePresence.objects.filter(
            place=current, persona=self.sheet.primary_persona
        ).exists()
        assert self.room.trigger_handler.fire_count(intent.pk) == 1
        assert self.remote.trigger_handler.fire_count(result_trigger.pk) == 1

    def test_real_mutators_broadcast_and_renderer_extras(self):
        from actions.definitions import examine_extras, perception, places

        with (
            patch("actions.definitions.places.join_place", wraps=places.join_place) as join,
            patch("actions.definitions.places.leave_place", wraps=places.leave_place) as leave,
            patch.object(
                self.room, "_broadcast_room_state", wraps=self.room._broadcast_room_state
            ) as broadcast,
        ):
            assert self.post(self.join.key, self.wire("places", self.place))["success"]
            assert self.post(self.leave.key, self.wire("places", self.place))["success"]
        join.assert_called_once()
        leave.assert_called_once()
        assert broadcast.call_count >= 2
        with (
            patch(
                "actions.definitions.perception._render_physical_look",
                wraps=perception._render_physical_look,
            ) as renderer,
            patch(
                "actions.definitions.examine_extras.gather_examine_extras",
                wraps=examine_extras.gather_examine_extras,
            ) as extras,
        ):
            assert self.post("look", self.wire("objects", self.obj))["success"]
        renderer.assert_called_once()
        extras.assert_called_once_with(self.actor, self.obj)

    def test_initializer_mutations_stop_before_services_and_examine(self):
        original = SceneDataManager.initialize_state_for_object
        for key, kind, target in (
            (self.go.key, "exits", self.exit),
            ("look", "objects", self.obj),
            (self.join.key, "places", self.place),
            (self.leave.key, "places", self.place),
        ):
            PlacePresence.objects.filter(
                place=self.place, persona=self.sheet.primary_persona
            ).delete()
            if key == self.leave.key:
                PlacePresence.objects.create(place=self.place, persona=self.sheet.primary_persona)

            def initialize(manager, obj, *args, **kwargs):
                state = original(manager, obj, *args, **kwargs)
                if kind == "places" and obj == self.actor:
                    if key == self.join.key:
                        PlacePresence.objects.get_or_create(
                            place=self.place, persona=self.sheet.primary_persona
                        )
                    else:
                        PlacePresence.objects.filter(
                            place=self.place, persona=self.sheet.primary_persona
                        ).delete()
                elif obj == target:
                    obj.location = self.remote
                return state

            with (
                patch.object(SceneDataManager, "initialize_state_for_object", new=initialize),
                patch("actions.definitions.movement.traverse_exit") as travel,
                patch("actions.definitions.places.join_place") as join,
                patch("actions.definitions.places.leave_place") as leave,
                patch("actions.definitions.examine_extras.gather_examine_extras") as extras,
            ):
                result = self.post(key, self.wire(kind, target))
            assert not result["success"] and result["message"] == UNAVAILABLE
            for mock in (travel, join, leave, extras):
                mock.assert_not_called()
            if kind != "places":
                target.location = self.room

    def test_mission_participant_removal_refuses_stale_rest(self):
        instance, participant = self.admitted_mission()
        values = self.wire("exits", self.exit)
        assert self.pure(lambda: self.read(self.go, values)).available
        participant.delete()
        assert not self.pure(lambda: self.go.is_applicable(self.actor, kwargs=values))
        with patch("actions.definitions.movement.traverse_exit") as travel:
            assert self.post(self.go.key, values)["message"] == UNAVAILABLE
        travel.assert_not_called()
        assert self.actor.location == self.room and instance.owner != self.sheet

    def test_positive_visible_redirect_arrivals_integer_and_object(self):
        second = ObjectDBFactory(
            db_typeclass_path="typeclasses.exits.Exit", location=self.room, destination=self.remote
        )
        for service in (False, True):
            self.actor.location = self.room
            trigger = self.target_change(self.go.key, second, service=service)
            with (
                patch.object(second, "at_traverse", wraps=second.at_traverse) as chosen,
                patch.object(self.exit, "at_traverse", wraps=self.exit.at_traverse) as original,
            ):
                assert self.post(self.go.key, self.wire("exits", self.exit))["success"]
            assert self.actor.location == self.remote
            chosen.assert_called_once()
            original.assert_not_called()
            self.remove_trigger(trigger)

    def test_admission_removed_after_authored_redirect(self):
        _instance, participant = self.admitted_mission()
        second = ObjectDBFactory(
            db_typeclass_path="typeclasses.exits.Exit", location=self.room, destination=self.remote
        )
        trigger = self.target_change(self.go.key, second, service=True)

        def emit(event, payload, **kwargs):
            stack = emit_event(event, payload, **kwargs)
            if event == EventName.ACTION_INTENT:
                assert payload.target == second
                participant.delete()
            return stack

        with (
            patch("flows.emit.emit_event", side_effect=emit),
            patch("actions.definitions.movement.traverse_exit") as travel,
        ):
            result = self.post(self.go.key, self.wire("exits", self.exit))
        assert not result["success"] and result["message"] == UNAVAILABLE
        travel.assert_not_called()
        assert self.actor.location == self.room
        self.remove_trigger(trigger)

    def test_destination_initialization_repeats_destination_publication_admission(self):
        original = SceneDataManager.initialize_state_for_object
        third = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        RoomProfileFactory(objectdb=third, published_at=timezone.now())
        for mutation in ("destination", "publication", "admission"):
            self.exit.destination = self.remote
            self.destination.published_at = timezone.now()
            self.destination.save(update_fields=["published_at"])
            instance = InstancedRoom.objects.create(room=self.destination, owner=self.sheet)
            touched = []

            def initialize(manager, obj, *args, **kwargs):
                state = original(manager, obj, *args, **kwargs)
                if obj == self.remote:
                    touched.append(obj)
                    if mutation == "destination":
                        self.exit.destination = third
                    elif mutation == "publication":
                        self.destination.published_at = None
                        self.destination.save(update_fields=["published_at"])
                    else:
                        instance.owner = RosterEntryFactory().character_sheet
                        instance.save(update_fields=["owner"])
                return state

            with (
                patch.object(SceneDataManager, "initialize_state_for_object", new=initialize),
                patch("actions.definitions.movement.traverse_exit") as travel,
            ):
                result = self.post(self.go.key, self.wire("exits", self.exit))
            assert touched
            assert not result["success"] and result["message"] == UNAVAILABLE
            travel.assert_not_called()
            assert self.actor.location == self.room
            instance.delete()

    def test_admission_repeats_after_final_real_permission_gate(self):
        from actions.definitions import movement

        _instance, participant = self.admitted_mission()
        real_check = movement.check_exit_traversal
        calls = []

        def check(caller, exit_state):
            real_check(caller, exit_state)
            calls.append(exit_state)
            if len(calls) == 2:
                participant.delete()

        with (
            patch("actions.definitions.movement.check_exit_traversal", side_effect=check),
            patch("actions.definitions.movement.traverse_exit") as travel,
        ):
            result = self.post(self.go.key, self.wire("exits", self.exit))
        assert len(calls) == 2
        assert not result["success"] and result["message"] == UNAVAILABLE
        travel.assert_not_called()
        assert self.actor.location == self.room

    def test_keyed_exit_rest_and_cold_warm_inputs(self):
        values = self.wire("exits", self.exit)
        key = ObjectDBFactory(location=self.actor)
        self.attach(
            self.exit,
            "can_traverse",
            "behaviors.matching_value_package.require_matching_value",
            {"attribute": "key_id", "value": "silver", "error": "Bring the silver key."},
        )
        self.attach(
            key,
            "initialize_state",
            "behaviors.state_values_package.initialize_state",
            {"values": {"key_id": "silver"}},
        )
        manager = SceneDataManager()
        state = manager.initialize_state_for_object(key)
        for supplied in (None, manager):
            with forbid_read_effects():
                assert self.go.is_applicable(self.actor, kwargs=values)
                assert self.go.check_availability(
                    self.actor, context={"kwargs": values, "scene_data": supplied}
                ).available
        state.set_attribute("key_id", "copper")
        with forbid_read_effects():
            refusal = self.go.check_availability(
                self.actor, context={"kwargs": values, "scene_data": manager}
            )
        assert refusal.reasons == ["Bring the silver key."]
        key.location = self.room
        self.deny_current(self.go, self.go.key, values, "Bring the silver key.")
        key.location = self.actor
        assert self.post(self.go.key, values)["success"] and self.actor.location == self.remote

    def test_unsupported_inspection_disabled_existing_hook_executes(self):
        values = self.wire("exits", self.exit)
        self.attach(
            self.exit, "can_traverse", "behaviors.tests.test_traversal_inspection.write_on_traverse"
        )
        before = Place.objects.count()
        with forbid_read_effects():
            assert self.go.is_applicable(self.actor, kwargs=values)
            assert self.read(self.go, values).reasons == [INSPECTION_UNAVAILABLE]
        assert self.post(self.go.key, values)["message"] == INSPECTION_UNAVAILABLE
        assert Place.objects.count() == before
        assert self.go.run(self.actor, target=self.exit).success
        assert Place.objects.count() == before + 1 and self.actor.location == self.remote

    def test_no_arrival_outcomes_output_effects_and_actual_location(self):  # noqa: C901
        from actions.definitions import movement

        self.load(carry_capacity(self.actor) + 1)
        pool, _ = FatiguePool.objects.get_or_create(character_sheet=self.sheet)
        before = pool.physical_current
        for mode in ("exception", "move_refused", "after_hook_redirect"):
            for path in ("resolved", "typed", "rest"):
                self.actor.location = self.room
                self.actor.save(update_fields=["db_location"])
                PlacePresence.objects.get_or_create(
                    place=self.place, persona=self.sheet.primary_persona
                )
                intent = self.trigger(self.go.key)
                third = self.room
                if mode == "after_hook_redirect":
                    third = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
                    RoomProfileFactory(objectdb=third, published_at=timezone.now())
                result_trigger = self.trigger(
                    self.go.key, event=EventName.ACTION_RESULT, room=third
                )
                events, post_results = [], []
                original_execute = self.go.execute

                def execute(actor, context=None, **kwargs):
                    context.post_effects.append(lambda ctx: post_results.append(ctx.result.success))
                    return original_execute(actor, context=context, **kwargs)

                def observe(event, payload, **kwargs):
                    if event in (EventName.ACTION_INTENT, EventName.ACTION_RESULT):
                        events.append((event, payload, kwargs.get("location")))
                    return emit_event(event, payload, **kwargs)

                def after_hook(actor, source):
                    actor.location = third
                    actor.save(update_fields=["db_location"])

                self.exit.db.err_traverse = None
                with (
                    patch.object(self.actor, "msg", wraps=self.actor.msg) as messages,
                    patch.object(
                        self.exit, "at_failed_traverse", wraps=self.exit.at_failed_traverse
                    ) as failed,
                    patch.object(
                        self.exit,
                        "at_traverse",
                        side_effect=RuntimeError("fixture failure")
                        if mode == "exception"
                        else None,
                        wraps=self.exit.at_traverse,
                    ) as hook,
                    patch.object(
                        self.actor,
                        "move_to",
                        return_value=False if mode == "move_refused" else DEFAULT,
                        wraps=self.actor.move_to,
                    ) as move,
                    patch.object(
                        self.exit,
                        "at_post_traverse",
                        side_effect=after_hook if mode == "after_hook_redirect" else None,
                        wraps=self.exit.at_post_traverse,
                    ) as after,
                    patch("flows.emit.emit_event", side_effect=observe),
                    patch(
                        "flows.service_functions.movement.logger.exception"
                    ) as traversal_error_log,
                    patch(
                        "world.items.services.encumbrance.charge_move_fatigue",
                        wraps=charge_move_fatigue,
                    ) as fatigue,
                    patch(
                        "world.room_features.services.react_to_unauthorized_entry",
                        wraps=react_to_unauthorized_entry,
                    ) as wards,
                    patch(
                        "actions.definitions.movement.send_room_state",
                        wraps=movement.send_room_state,
                    ) as broadcast,
                ):
                    values = (
                        {"target": self.exit}
                        if path == "resolved"
                        else self.wire("exits", self.exit)
                    )
                    if path == "rest":
                        result = self.post(self.go.key, values)
                        assert (
                            not result["success"]
                            and result["message"] == "You cannot go that way."
                            and result["data"] is None
                        )
                    else:
                        with patch.object(self.go, "execute", side_effect=execute):
                            result = self.go.run(self.actor, **values)
                        assert (
                            not result.success
                            and result.message == "You cannot go that way."
                            and result.data == {}
                        ), (mode, path, result)
                        assert post_results == [False]
                hook.assert_called_once_with(self.actor, self.remote)
                if mode == "exception":
                    traversal_error_log.assert_called_once_with(
                        "at_traverse failed for exit %s", self.exit.pk
                    )
                else:
                    traversal_error_log.assert_not_called()
                assert self.actor.location == third
                fatigue.assert_not_called()
                wards.assert_not_called()
                assert pool.physical_current == before
                broadcast.assert_called_once()
                assert broadcast.call_args.args[0].obj.location == third
                if mode in ("exception", "move_refused"):
                    failed.assert_called_once_with(self.actor)
                    assert any(
                        call.args and call.args[0] == "You cannot go there."
                        for call in messages.call_args_list
                    )
                    after.assert_not_called()
                    assert PlacePresence.objects.filter(
                        place=self.place, persona=self.sheet.primary_persona
                    ).exists()
                else:
                    failed.assert_not_called()
                    after.assert_called_once_with(self.actor, self.room)
                    assert move.call_count == 1
                assert [event for event, _, _ in events] == [
                    EventName.ACTION_INTENT,
                    EventName.ACTION_RESULT,
                ]
                _, payload, location = events[-1]
                assert (
                    payload.success is False
                    and payload.message == "You cannot go that way."
                    and location == third
                )
                assert self.room.trigger_handler.fire_count(intent.pk) == 1
                assert third.trigger_handler.fire_count(result_trigger.pk) == 1
                self.remove_trigger(intent)
                self.remove_trigger(result_trigger, room=third)

    def test_custom_exit_refusal_message_survives_failed_rest(self):
        events = []

        def observe(event, payload, **kwargs):
            if event == EventName.ACTION_RESULT:
                events.append((payload, kwargs.get("location")))
            return emit_event(event, payload, **kwargs)

        self.exit.db.err_traverse = "The passage refuses you."
        with (
            patch.object(self.actor, "move_to", return_value=False),
            patch.object(self.actor, "msg", wraps=self.actor.msg) as messages,
            patch.object(
                self.exit, "at_failed_traverse", wraps=self.exit.at_failed_traverse
            ) as failed,
            patch("flows.emit.emit_event", side_effect=observe),
        ):
            result = self.post(self.go.key, self.wire("exits", self.exit))
        assert (
            not result["success"]
            and result["message"] == "You cannot go that way."
            and result["data"] is None
        )
        assert self.actor.location == self.room
        failed.assert_not_called()
        assert any(
            call.args and call.args[0] == "The passage refuses you."
            for call in messages.call_args_list
        )
        assert len(events) == 1
        payload, location = events[0]
        assert (
            payload.success is False
            and payload.message == result["message"]
            and location == self.room
        )

    def test_scheduled_hop_stops_when_traversal_hook_does_not_arrive(self):
        token = uuid.uuid4()
        self.actor.ndb.active_travel_token = token
        self.actor.ndb.active_travel_task = object()
        with (
            patch.object(self.exit, "at_traverse", return_value=None),
            patch.object(self.exit, "at_failed_traverse") as failed,
            patch.object(self.actor, "msg", wraps=self.actor.msg) as messages,
            patch("actions.definitions.movement.delay") as delay_next,
            patch("actions.definitions.movement.send_room_state") as broadcast,
        ):
            TravelAction._do_hop(self.actor, [self.exit, self.exit], 0, token)

        failed.assert_not_called()
        assert self.actor.location == self.room
        assert self.actor.ndb.active_travel_token is None
        assert self.actor.ndb.active_travel_task is None
        delay_next.assert_not_called()
        broadcast.assert_not_called()
        text = [call.args[0] for call in messages.call_args_list if call.args]
        assert "Your route stops here: You cannot go that way." in text
        assert "You arrive." not in text

    def test_failed_scheduled_hop_stops_without_next_hop_or_arrival(self):
        token = uuid.uuid4()
        self.actor.ndb.active_travel_token = token
        self.actor.ndb.active_travel_task = object()
        with (
            patch.object(self.actor, "move_to", return_value=False),
            patch.object(
                self.exit, "at_failed_traverse", wraps=self.exit.at_failed_traverse
            ) as failed,
            patch.object(self.actor, "msg", wraps=self.actor.msg) as messages,
            patch("actions.definitions.movement.delay") as delay_next,
            patch("actions.definitions.movement.send_room_state") as broadcast,
        ):
            TravelAction._do_hop(self.actor, [self.exit, self.exit], 0, token)
        failed.assert_called_once_with(self.actor)
        assert self.actor.location == self.room
        assert (
            self.actor.ndb.active_travel_token is None and self.actor.ndb.active_travel_task is None
        )
        delay_next.assert_not_called()
        broadcast.assert_not_called()
        text = [call.args[0] for call in messages.call_args_list if call.args]
        assert "You cannot go there." in text
        assert "Your route stops here: You cannot go that way." in text
        assert "You arrive." not in text
