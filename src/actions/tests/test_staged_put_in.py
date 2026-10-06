"""Real typed PutIn journeys and pure staged container reads."""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from actions.base import Action
from actions.definitions.items import PutInAction
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from flows.emit import emit_event
from flows.scene_data_manager import SceneDataManager
from world.consent.models import SocialConsentCategory
from world.items.constants import BodyRegion, ContainerAccessPolicy, EquipmentLayer
from world.items.exceptions import ContainerClosed, ContainerFull, ItemTooLarge, NotInPossession
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, TemplateSlotFactory
from world.items.models import EquippedItem, OwnershipEvent
from world.items.services.equip import equip_item
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


class StagedPutInTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        entry = RosterEntryFactory()
        self.sheet = entry.character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        self.account = AccountFactory(is_staff=False)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=self.account),
            start_date=timezone.now(),
            end_date=None,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.item = self.make_item("Selected", pk=960012)
        self.bag = self.make_item("Public bag", container=True, pk=970012)
        self.action = PutInAction()

    def make_item(self, name, *, container=False, location=None, pk=None):
        return ItemInstanceFactory(
            template=ItemTemplateFactory(
                name=name,
                size=1,
                is_container=container,
                supports_open_close=container,
                container_capacity=2 if container else 0,
                container_max_item_size=5 if container else 0,
            ),
            game_object=ObjectDBFactory(
                location=self.actor if location is None else location,
                db_typeclass_path="typeclasses.objects.Object",
            ),
            holder_character_sheet=self.sheet,
            is_open=True,
            **({"pk": pk} if pk is not None else {}),
        )

    def kwargs(self, *, item=None, bag=None, complete=True):
        values = {
            "menu_target": {"kind": "items", "target_id": (self.item if item is None else item).pk}
        }
        if complete:
            values["container_item_id"] = (self.bag if bag is None else bag).pk
        return values

    def read(self, values, pending=frozenset()):
        return self.action.check_availability(
            self.actor, context={"kwargs": values}, pending_inputs=pending
        )

    def post(self, values):
        response = self.client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {"ref": {"backend": "registry", "registry_key": "put_in"}, "kwargs": values},
            format="json",
        )
        assert response.status_code == 200, response.data
        return response.data

    def snapshot(self, item=None):
        item = self.item if item is None else item
        return (
            item.game_object.location,
            item.contained_in,
            item.holder_character_sheet,
            tuple(EquippedItem.objects.filter(item_instance=item).order_by("pk")),
            tuple(OwnershipEvent.objects.filter(item_instance=item).order_by("pk")),
        )

    def trigger(self, action, parameters=None, variable_name=""):
        from flows.constants import EventName
        from flows.factories import (
            FlowDefinitionFactory,
            FlowStepDefinitionFactory,
            TriggerDefinitionFactory,
            TriggerFactory,
        )

        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=action,
            parameters=parameters or {},
            variable_name=variable_name,
        )
        trigger = TriggerFactory(
            obj=self.room,
            trigger_definition=TriggerDefinitionFactory(
                event_name=EventName.ACTION_INTENT, flow_definition=flow
            ),
        )
        self.room.trigger_handler.refresh()
        return trigger

    def remove_trigger(self, trigger):
        trigger.delete()
        self.room.trigger_handler.refresh()

    def conceal(self, obj):
        from world.conditions.factories import (
            ConditionCategoryFactory,
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )

        return ConditionInstanceFactory(
            target=obj,
            condition=ConditionTemplateFactory(
                category=ConditionCategoryFactory(conceals_from_perception=True)
            ),
        )

    def test_ac1_pending_is_read_only_and_bound_checks_always_run(self):
        bound = self.kwargs(complete=False)
        assert self.read(bound, frozenset({"container_item_id"})).available
        assert not self.read(bound).available
        for pending, values in (
            (frozenset({"unknown"}), bound),
            (frozenset({"container_item_id"}), {**bound, "container_item_id": None}),
        ):
            with self.assertRaises(ValueError):
                self.read(values, pending)
        with patch.object(Action, "_dead_gate_reason", return_value="dead"):
            assert self.read(bound, frozenset({"container_item_id"})).reasons == ["dead"]
        with (
            patch.object(Action, "_dead_gate_reason", return_value=""),
            patch.object(Action, "_offscreen_gate_reason", return_value="offscreen"),
        ):
            assert self.read(bound, frozenset({"container_item_id"})).reasons == ["offscreen"]
        before = self.snapshot()
        assert not self.post(
            {
                **bound,
                "pending_inputs": ["container_item_id"],
                "context": {"pending_inputs": ["container_item_id"]},
            }
        )["success"]
        assert self.snapshot() == before
        self.item.game_object.location = self.room
        assert not self.read(bound, frozenset({"container_item_id"})).available
        self.item.game_object.location = self.bag.game_object
        self.item.contained_in = self.bag
        self.item.save(update_fields=["contained_in"])
        bound["menu_target"]["container_item_id"] = self.bag.pk
        assert not self.read(bound, frozenset({"container_item_id"})).available

    def test_ac2_real_rest_exact_domains_and_existing_effects(self):
        decoy = self.make_item("Object ID decoy", pk=self.item.game_object.pk)
        TemplateSlotFactory(
            template=self.item.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        equip_item(
            character_sheet=self.sheet,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        before = self.snapshot()
        assert self.item.pk != self.item.game_object.pk
        assert self.bag.pk != self.bag.game_object.pk
        assert self.read(self.kwargs()).available
        with (
            patch("world.events.services.tag_catered_provision") as tag,
            patch("flows.emit.emit_event", wraps=emit_event) as emit,
        ):
            assert self.post(self.kwargs())["success"]
        assert self.item.contained_in == self.bag
        assert self.item.game_object.location == self.bag.game_object
        assert self.item.holder_character_sheet == before[2]
        assert self.snapshot()[3:] == before[3:]
        assert decoy.game_object.location == self.actor
        tag.assert_called_once_with(self.item, self.bag, self.actor)
        # The existing action delivers the insertion line through message_location.
        # Retain the existing insertion wording and action event pair.
        from flows.constants import EventName

        names = [call.args[0] for call in emit.call_args_list]
        assert names.count(EventName.ACTION_INTENT) == 1
        assert names.count(EventName.ACTION_RESULT) == 1

    def test_ac2_real_rendered_custom_labels_without_private_keys(self):
        import evennia

        class RecordingSession:
            sessid = 960012

            def __init__(self):
                self.frames = []

            def data_out(self, **kwargs):
                self.frames.append(kwargs)

        session = RecordingSession()
        self.item.custom_name = "a silver keepsake"
        self.item.save(update_fields=["custom_name"])
        self.bag.custom_name = "an embroidered satchel"
        self.bag.save(update_fields=["custom_name"])
        self.item.game_object.key = "Private source key"
        self.bag.game_object.key = "Private destination key"
        evennia.SESSION_HANDLER[session.sessid] = session
        self.actor.sessions.add(session)
        try:
            assert self.post(self.kwargs())["success"]
            delivered = str(session.frames)
            assert "put a silver keepsake into an embroidered satchel." in delivered
            assert "Private source key" not in delivered
            assert "Private destination key" not in delivered
            assert "Selected" not in delivered
            assert "Public bag" not in delivered
            assert self.item.contained_in == self.bag
        finally:
            self.actor.sessions.remove(session)
            evennia.SESSION_HANDLER.pop(session.sessid, None)

    def test_ac2_strict_mixed_invalid_row_only_and_self_neutral(self):
        before = self.snapshot()
        bad = []
        for value in (None, True, False, "1", 0, -1, [], {}, 999999999):
            bad.append({**self.kwargs(), "container_item_id": value})
            bad.append({**self.kwargs(), "menu_target": {"kind": "items", "target_id": value}})
        bad.extend(
            {**self.kwargs(), field: self.bag.game_object.pk}
            for field in (
                "target",
                "target_id",
                "item",
                "item_id",
                "item_instance_id",
                "item_name",
                "owner_id",
                "owner_persona_id",
                "target_persona_id",
                "container",
                "container_id",
            )
        )
        bad.extend(
            (
                {**self.kwargs(), "container_item_id": self.item.pk},
                {
                    **self.kwargs(),
                    "menu_target": {"kind": "objects", "target_id": self.item.game_object.pk},
                },
            )
        )
        row = ItemInstanceFactory(
            template=self.bag.template, game_object=None, holder_character_sheet=self.sheet
        )
        bad.extend((self.kwargs(item=row), self.kwargs(bag=row)))
        for values in bad:
            with self.subTest(values=values):
                assert self.read(values).reasons == ["That isn't available."]
                assert self.post(values)["message"] == "That isn't available."
                assert self.snapshot() == before

    def test_ac3_complete_predicates_and_legacy_messages(self):
        assert self.action.run(self.actor).message == "Put what into what?"
        assert (
            self.action.run(self.actor, target=self.room, container=self.bag).message
            == "That can't be put away."
        )
        assert (
            self.action.run(self.actor, target=self.item, container=self.room).message
            == "That isn't a container."
        )
        before = self.snapshot()
        for case, reason in (
            ("closed", ContainerClosed.user_message),
            ("full", ContainerFull.user_message),
            ("size", ItemTooLarge.user_message),
        ):
            fillers = []
            if case == "closed":
                self.bag.is_open = False
                self.bag.save(update_fields=["is_open"])
            elif case == "full":
                for index in range(2):
                    filler = self.make_item(f"Filler {index}")
                    filler.contained_in = self.bag
                    filler.save(update_fields=["contained_in"])
                    filler.game_object.location = self.bag.game_object
                    fillers.append(filler)
            else:
                self.item.template.size = 99
                self.item.template.save(update_fields=["size"])
            assert self.read(
                self.kwargs(complete=False), frozenset({"container_item_id"})
            ).available
            assert self.read(self.kwargs()).reasons == [reason]
            row = next(
                row
                for row in self.action.container_candidates(
                    self.actor, kwargs=self.kwargs(complete=False)
                )
                if row["container_item_id"] == self.bag.pk
            )
            assert not row["available"]
            assert row["reasons"] == [reason]
            assert self.post(self.kwargs())["message"] == reason
            assert self.snapshot() == before
            self.bag.is_open = True
            self.bag.save(update_fields=["is_open"])
            self.item.template.size = 1
            self.item.template.save(update_fields=["size"])
            for filler in fillers:
                filler.delete()
        self.item.game_object.location = self.room
        assert (
            self.action.run(self.actor, target=self.item, container=self.bag).message
            == NotInPossession.user_message
        )

    def test_ac3_no_ownership_or_container_take_policy_widening(self):
        foreign_sheet = RosterEntryFactory().character_sheet
        self.bag.holder_character_sheet = foreign_sheet
        self.bag.access_policy = ContainerAccessPolicy.OWNER_ONLY
        self.bag.save(update_fields=["holder_character_sheet", "access_policy"])
        self.bag.game_object.location = self.room
        for holder in (None, foreign_sheet):
            item = self.make_item("Physically held")
            item.holder_character_sheet = holder
            item.save(update_fields=["holder_character_sheet"])
            assert self.read(self.kwargs(item=item)).available
            assert self.post(self.kwargs(item=item))["success"]
            assert item.holder_character_sheet == holder
            item.delete()

    def test_ac4_current_visible_roots_only_safe_labels_and_empty(self):
        room_bag = self.make_item("Visible room bag", container=True, location=self.room)
        room_bag.game_object.key = "Private raw key"
        hidden = self.make_item("Concealed", container=True, location=self.room)
        condition = self.conceal(hidden.game_object)
        remote = self.make_item("Remote", container=True, location=self.remote)
        nested = self.make_item("Nested", container=True)
        nested.contained_in = self.bag
        nested.save(update_fields=["contained_in"])
        nested.game_object.location = self.bag.game_object
        row_only = ItemInstanceFactory(
            template=self.bag.template, game_object=None, holder_character_sheet=self.sheet
        )
        private = self.make_item(
            "Private carried",
            container=True,
            location=RosterEntryFactory().character_sheet.character,
        )
        rows = self.action.container_candidates(self.actor, kwargs=self.kwargs(complete=False))
        assert [row["container_item_id"] for row in rows] == sorted([self.bag.pk, room_bag.pk])
        assert (
            next(row for row in rows if row["container_item_id"] == room_bag.pk)["name"]
            == room_bag.display_name
        )
        assert "Private raw key" not in str(rows)
        for item in (hidden, remote, nested, row_only, private):
            assert self.post(self.kwargs(bag=item))["message"] == "That isn't available."
        self.bag.game_object.location = self.remote
        room_bag.game_object.location = self.remote
        assert (
            self.action.container_candidates(self.actor, kwargs=self.kwargs(complete=False)) == ()
        )
        condition.delete()
        self.item.template.is_container = True
        self.item.template.save(update_fields=["is_container"])
        assert all(
            row["container_item_id"] != self.item.pk
            for row in self.action.container_candidates(
                self.actor, kwargs=self.kwargs(complete=False)
            )
        )

    def test_ac5_real_authored_source_redirects_and_cancel(self):
        from flows.consts import FlowActionChoices

        replacement = self.make_item("Replacement")
        for service in (False, True):
            trigger = self.trigger(
                FlowActionChoices.CALL_SERVICE_FUNCTION
                if service
                else FlowActionChoices.MODIFY_PAYLOAD,
                {"payload": "@payload", "object_id": replacement.game_object.pk}
                if service
                else {"field": "target", "op": "set", "value": replacement.game_object.pk},
                "flows.service_functions.actions.redirect_action_target" if service else "",
            )
            before = self.snapshot()
            try:
                assert self.post(self.kwargs())["success"]
                assert replacement.contained_in == self.bag
                assert self.snapshot() == before
            finally:
                self.remove_trigger(trigger)
            replacement.contained_in = None
            replacement.save(update_fields=["contained_in"])
            replacement.game_object.location = self.actor
        for value in (self.room.pk, None, True, "bad"):
            trigger = self.trigger(
                FlowActionChoices.MODIFY_PAYLOAD, {"field": "target", "op": "set", "value": value}
            )
            before = self.snapshot()
            try:
                assert self.post(self.kwargs())["message"] == "That isn't available."
                assert self.snapshot() == before
            finally:
                self.remove_trigger(trigger)
        trigger = self.trigger(FlowActionChoices.CANCEL_EVENT)
        before = self.snapshot()
        try:
            assert self.post(self.kwargs())["message"] == "Something prevents you."
            assert self.snapshot() == before
        finally:
            self.remove_trigger(trigger)
        # An owner assertion on the source is retained on a redirect; it cannot
        # become an unrelated unasserted carried source.
        TemplateSlotFactory(
            template=self.item.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        equip_item(
            character_sheet=self.sheet,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        asserted = self.kwargs()
        asserted["menu_target"]["owner_persona_id"] = self.sheet.primary_persona.pk
        assert self.read(asserted).available
        trigger = self.trigger(
            FlowActionChoices.MODIFY_PAYLOAD,
            {"field": "target", "op": "set", "value": replacement.game_object.pk},
        )
        try:
            assert self.post(asserted)["message"] == "That isn't available."
        finally:
            self.remove_trigger(trigger)

    def test_ac5_destination_redirects_valid_invalid_and_blocked(self):
        from flows.consts import FlowActionChoices

        alternate = self.make_item("Alternate", container=True, location=self.room)
        trigger = self.trigger(
            FlowActionChoices.MODIFY_PAYLOAD,
            {"field": "container_item_id", "op": "set", "value": alternate.pk},
        )
        try:
            assert self.post(self.kwargs())["success"]
            assert self.item.contained_in == alternate
        finally:
            self.remove_trigger(trigger)
        self.item.contained_in = None
        self.item.save(update_fields=["contained_in"])
        self.item.game_object.location = self.actor
        hidden = self.conceal(alternate.game_object)
        for value in (None, True, str(self.bag.pk), 0, -1, 999999999, self.item.pk, alternate.pk):
            trigger = self.trigger(
                FlowActionChoices.MODIFY_PAYLOAD,
                {"field": "container_item_id", "op": "set", "value": value},
            )
            before = self.snapshot()
            try:
                assert self.post(self.kwargs())["message"] == "That isn't available."
                assert self.snapshot() == before
            finally:
                self.remove_trigger(trigger)
        hidden.delete()
        alternate.game_object.location = self.remote
        trigger = self.trigger(
            FlowActionChoices.MODIFY_PAYLOAD,
            {"field": "container_item_id", "op": "set", "value": alternate.pk},
        )
        try:
            assert self.post(self.kwargs())["message"] == "That isn't available."
        finally:
            self.remove_trigger(trigger)
        alternate.game_object.location = self.room
        alternate.is_open = False
        alternate.save(update_fields=["is_open"])
        trigger = self.trigger(
            FlowActionChoices.MODIFY_PAYLOAD,
            {"field": "container_item_id", "op": "set", "value": alternate.pk},
        )
        before = self.snapshot()
        try:
            assert self.post(self.kwargs())["message"] == ContainerClosed.user_message
            assert self.snapshot() == before
        finally:
            self.remove_trigger(trigger)

    def test_ac5_stale_and_post_gate_inputs_rechecked(self):
        selected = self.kwargs()
        assert self.read(selected).available
        self.bag.game_object.location = self.remote
        assert self.post(selected)["message"] == "That isn't available."
        self.bag.game_object.location = self.actor
        original = PutInAction.execute
        for change in ("remote", "closed", "source"):
            self.item.game_object.location = self.actor
            self.bag.game_object.location = self.actor
            self.bag.is_open = True
            self.bag.save(update_fields=["is_open"])
            assert self.read(selected).available

            def execute(action, actor, context=None, *, change=change, **kwargs):
                if change == "remote":
                    self.bag.game_object.location = self.remote
                elif change == "source":
                    self.item.game_object.location = self.room
                else:
                    self.bag.is_open = False
                    self.bag.save(update_fields=["is_open"])
                return original(action, actor, context=context, **kwargs)

            with patch.object(PutInAction, "execute", execute):
                result = self.post(selected)
            assert result["message"] == (
                ContainerClosed.user_message if change == "closed" else "That isn't available."
            )
            assert self.item.contained_in is None
        self.item.game_object.location = self.actor
        self.bag.game_object.location = self.actor
        self.bag.is_open = True
        self.bag.save(update_fields=["is_open"])
        initialize = SceneDataManager.initialize_state_for_object

        def init(sdm, obj):
            state = initialize(sdm, obj)
            self.bag.is_open = False
            self.bag.save(update_fields=["is_open"])
            return state

        with patch.object(SceneDataManager, "initialize_state_for_object", init):
            assert self.post(selected)["message"] == ContainerClosed.user_message
        assert self.item.contained_in is None

    def test_ac6_all_read_stages_pure_for_valid_and_blocked_pairs(self):
        SocialConsentCategory.objects.filter(key="receiving-stolen-goods").delete()
        before = self.snapshot()
        for closed in (False, True):
            self.bag.is_open = not closed
            self.bag.save(update_fields=["is_open"])
            with (
                patch.object(
                    SceneDataManager,
                    "initialize_state_for_object",
                    side_effect=AssertionError("read initialized"),
                ),
                patch("flows.emit.emit_event", side_effect=AssertionError("read emitted")),
                CaptureQueriesContext(connection) as queries,
            ):
                for _ in range(3):
                    assert self.action.is_applicable(self.actor, kwargs=self.kwargs(complete=False))
                    assert self.read(
                        self.kwargs(complete=False), frozenset({"container_item_id"})
                    ).available
                    rows = self.action.container_candidates(
                        self.actor, kwargs=self.kwargs(complete=False)
                    )
                    assert (
                        next(row for row in rows if row["container_item_id"] == self.bag.pk)[
                            "available"
                        ]
                        is not closed
                    )
                    assert self.read(self.kwargs()).available is not closed
            for query in queries:
                sql = query["sql"].upper()
                assert not sql.lstrip().startswith(
                    ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")
                ), sql
                assert "FOR UPDATE" not in sql, sql
            assert self.snapshot() == before
        assert not SocialConsentCategory.objects.filter(key="receiving-stolen-goods").exists()
