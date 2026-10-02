"""Typed item Look journeys through real JSON dispatch."""

from typing import cast
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from actions.definitions import examine_extras
from actions.definitions.perception import LookAtItemAction
from actions.target_menu_types import MenuTargetKind, MenuTargetRequest
from actions.target_resolution import resolve_menu_target
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from world.character_sheets.models import CharacterSheet
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.events.factories import EventFactory
from world.events.models import CateringRole, EventCatering
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    TemplateSlotFactory,
)
from world.items.services.equip import equip_item, unequip_item
from world.missions.constants import GiverKind
from world.missions.factories import (
    MissionGiverFactory,
    MissionNodeFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionInstance
from world.missions.services.trigger_dispatch import maybe_dispatch_on_examine
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.services import create_mask, set_active_persona


class TypedItemLookTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.entry = RosterEntryFactory()
        self.sheet = self.entry.character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        self.account = cast(AccountDB, AccountFactory(is_staff=False))
        RosterTenureFactory(
            player_data=PlayerDataFactory(account=self.account),
            roster_entry=self.entry,
            start_date=timezone.now(),
            end_date=None,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.item = self._item(self.actor, "Exact cup", pk=900001)
        self.other_sheet = cast(CharacterSheet, RosterEntryFactory().character_sheet)
        self.wearer = self.other_sheet.character
        self.wearer.location = self.room
        self.mask = create_mask(self.other_sheet, name="A Grey Hood")
        set_active_persona(self.other_sheet, self.mask)

    def _item(  # noqa: PLR0913
        self,
        location,
        name,
        *,
        physical=True,
        holder=None,
        pk=None,
        template=None,
    ):
        obj = ObjectDBFactory(db_key=name, location=location) if physical else None
        kwargs = {"pk": pk} if pk is not None else {}
        return ItemInstanceFactory(
            template=template or ItemTemplateFactory(name=name, description=f"Detail of {name}"),
            custom_name=name,
            game_object=obj,
            holder_character_sheet=holder or self.sheet,
            **kwargs,
        )

    def _wire(self, item=None, **context):
        return {"kind": "items", "target_id": (item or self.item).pk, **context}

    def _post(self, wire=None, **kwargs):
        response = self.client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {
                "ref": {"backend": "registry", "registry_key": "look_at_item"},
                "kwargs": {"menu_target": self._wire() if wire is None else wire, **kwargs},
            },
            format="json",
        )
        assert response.status_code == 200, response.data
        return response.data

    def _deny(self, wire, **kwargs):
        data = self._post(wire, **kwargs)
        assert data == {
            "backend": "registry",
            "deferred": False,
            "message": "That isn't available to look at.",
            "data": None,
            "success": False,
        }
        return data

    def _conceal(self, target):
        return ConditionInstanceFactory(
            target=target,
            condition=ConditionTemplateFactory(
                category=ConditionCategoryFactory(conceals_from_perception=True),
            ),
        )

    def _equip(self, name, layer, *, physical=True):
        template = ItemTemplateFactory(name=name)
        TemplateSlotFactory(template=template, body_region=BodyRegion.TORSO, equipment_layer=layer)
        item = self._item(
            self.wearer,
            name,
            physical=physical,
            holder=self.other_sheet,
            template=template,
        )
        equip_item(
            character_sheet=self.other_sheet,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=layer,
        )
        return item

    def _trigger(self, event, *, action=None, parameters=None, variable_name=None):
        flow = FlowDefinitionFactory()
        if action is not None:
            FlowStepDefinitionFactory(
                flow=flow,
                parent_id=None,
                action=action,
                parameters=parameters or {},
                variable_name=variable_name or "",
            )
        definition = TriggerDefinitionFactory(event_name=event, flow_definition=flow)
        trigger = TriggerFactory(trigger_definition=definition, obj=self.room)
        self.room.trigger_handler.refresh()
        return trigger

    def _remove_trigger(self, trigger):
        trigger.delete()
        self.room.trigger_handler.refresh()

    def test_exact_json_id_physical_row_only_and_room(self):
        assert self.item.pk != self.item.game_object.pk
        decoy = self._item(self.actor, "Wrong cup", pk=self.item.game_object.pk)
        assert decoy.pk != self.item.pk
        result = self._post()
        assert result["success"] is True
        assert "Exact cup" in result["message"]
        assert "Wrong cup" not in result["message"]
        row = self._item(None, "Row cup", physical=False)
        count = ObjectDBFactory._meta.model.objects.count()
        assert self._post(self._wire(row))["message"] == LookAtItemAction._render_item(row)
        assert row.game_object is None
        assert ObjectDBFactory._meta.model.objects.count() == count
        self.item.game_object.location = self.room
        assert self._post()["success"] is True

    def test_malformed_and_competing_fields_never_choose_precedence(self):
        wires = [
            [],
            3,
            {},
            {"kind": "objects", "target_id": self.item.game_object.pk},
            {**self._wire(), "label": "Trust me"},
            {**self._wire(), "owner_persona_id": self.mask.pk, "container_item_id": self.item.pk},
        ]
        for wire in wires:
            self._deny(wire)
        response = self.client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {
                "ref": {"backend": "registry", "registry_key": "look_at_item"},
                "kwargs": {"menu_target": None},
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.data["success"] is False
        assert response.data["message"] == "That isn't available to look at."
        for key in ("target_id", "owner_persona_id", "container_item_id"):
            for value in (True, False, 0, -1, "1", 1.0, None, [], {}):
                self._deny({**self._wire(), key: value})
        for key in (
            "target",
            "target_id",
            "item",
            "item_id",
            "item_instance_id",
            "item_name",
            "owner_id",
            "container_id",
            "target_persona_id",
            "owner_persona_id",
            "container_item_id",
        ):
            self._deny(self._wire(), **{key: None})

    def test_unavailable_equivalence_and_stale_resolution(self):
        absent = self._deny({"kind": "items", "target_id": 999999999})
        request = MenuTargetRequest(MenuTargetKind.ITEMS, self.item.pk)
        assert resolve_menu_target(self.actor, request) is not None
        self.item.game_object.location = self.remote
        assert self._deny(self._wire()) == absent
        self.item.game_object.location = self.actor
        condition = self._conceal(self.item.game_object)
        assert self._deny(self._wire()) == absent
        condition.delete()
        self.item.destroyed_at = timezone.now()
        self.item.save(update_fields=["destroyed_at"])
        assert self._deny(self._wire()) == absent
        private = self._item(self.wearer, "Private cup", holder=self.other_sheet)
        assert self._deny(self._wire(private)) == absent

    def test_worn_context_mask_privacy_and_current_layers(self):
        shirt = self._equip("Hidden shirt", EquipmentLayer.BASE)
        coat = self._equip("Visible coat", EquipmentLayer.OVER)
        wire = self._wire(coat, owner_persona_id=self.mask.pk)
        assert self._post(wire)["success"] is True
        self._deny(self._wire(shirt, owner_persona_id=self.mask.pk))
        self._deny(self._wire(coat, owner_persona_id=self.other_sheet.primary_persona.pk))
        condition = self._conceal(self.wearer)
        self._deny(wire)
        condition.delete()
        self.wearer.location = self.remote
        self._deny(wire)
        self.wearer.location = self.room
        equipped = coat.equipped_slots.first()
        unequip_item(equipped_item=equipped)
        self._deny(wire)
        assert self.wearer.key not in str(self._deny(wire))

    def test_current_container_assertion_and_row_only_child(self):
        template = ItemTemplateFactory(
            is_container=True,
            supports_open_close=True,
            container_capacity=10,
        )
        bag = self._item(self.actor, "Bag", template=template)
        bag.is_open = True
        bag.save(update_fields=["is_open"])
        for physical in (True, False):
            child = self._item(bag.game_object, "Child", physical=physical)
            child.contained_in = bag
            child.save(update_fields=["contained_in"])
            wire = self._wire(child, container_item_id=bag.pk)
            assert self._post(wire)["success"] is True
            self._deny(self._wire(child))
            self._deny(self._wire(child, container_item_id=self.item.pk))
            bag.is_open = False
            bag.save(update_fields=["is_open"])
            self._deny(wire)
            bag.is_open = True
            bag.save(update_fields=["is_open"])

    def test_read_checks_emit_nothing_write_nothing_and_render_nothing(self):
        triggers = [
            self._trigger(event)
            for event in (
                EventName.ACTION_INTENT,
                EventName.ACTION_RESULT,
                EventName.EXAMINE_PRE,
                EventName.EXAMINED,
            )
        ]
        action = LookAtItemAction()
        with (
            patch.object(action, "_render_item", wraps=action._render_item) as render,
            patch("actions.definitions.examine_extras.gather_examine_extras") as extras,
            CaptureQueriesContext(connection) as queries,
        ):
            for _ in range(2):
                result = action.check_availability(
                    self.actor,
                    context={"kwargs": {"menu_target": self._wire()}},
                )
                assert result.available
            render.assert_not_called()
            extras.assert_not_called()
        assert not [
            q["sql"]
            for q in queries
            if q["sql"].lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}
        ]
        for trigger in triggers:
            assert self.room.trigger_handler.fire_count(trigger.pk) == 0

    def test_real_intent_cancel_and_examine_cancel(self):
        self.item.game_object.location = self.room
        intent = self._trigger(EventName.ACTION_INTENT, action=FlowActionChoices.CANCEL_EVENT)
        assert self._post()["success"] is False
        assert self.room.trigger_handler.fire_count(intent.pk) == 1
        self._remove_trigger(intent)
        pre = self._trigger(EventName.EXAMINE_PRE, action=FlowActionChoices.CANCEL_EVENT)
        post = self._trigger(EventName.EXAMINED)
        result = self._post()
        assert result["success"] is True
        assert result["message"] == ""
        assert self.room.trigger_handler.fire_count(pre.pk) == 1
        assert self.room.trigger_handler.fire_count(post.pk) == 0

    def test_real_redirect_raw_pk_and_service_recheck(self):
        destination = self._item(self.room, "Redirected cup")
        for service in (False, True):
            trigger = self._trigger(
                EventName.ACTION_INTENT,
                action=(
                    FlowActionChoices.CALL_SERVICE_FUNCTION
                    if service
                    else FlowActionChoices.MODIFY_PAYLOAD
                ),
                parameters=(
                    {"payload": "@payload", "object_id": destination.game_object.pk}
                    if service
                    else {"field": "target", "op": "set", "value": destination.game_object.pk}
                ),
                variable_name="flows.service_functions.actions.redirect_action_target"
                if service
                else None,
            )
            result = self._post()
            assert result["success"] is True
            assert "Redirected cup" in result["message"]
            destination.game_object.location = self.remote
            self._deny(self._wire())
            destination.game_object.location = self.room
            self._remove_trigger(trigger)

    def test_contained_redirect_stays_within_asserted_container(self):
        template = ItemTemplateFactory(
            is_container=True,
            supports_open_close=True,
            container_capacity=10,
        )
        bag = self._item(self.actor, "Redirect bag", template=template)
        bag.is_open = True
        bag.save(update_fields=["is_open"])

        def contained_child(name):
            child = self._item(bag.game_object, name)
            child.contained_in = bag
            child.save(update_fields=["contained_in"])
            return child

        original = contained_child("Starting child")
        sibling = contained_child("Sibling child")
        wire = self._wire(original, container_item_id=bag.pk)
        trigger = self._trigger(
            EventName.ACTION_INTENT,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "target", "op": "set", "value": sibling.game_object.pk},
        )
        result = self._post(wire)
        assert result["success"] is True
        assert "Sibling child" in result["message"]
        self._remove_trigger(trigger)
        outside = self._item(self.room, "Outside visible cup")
        trigger = self._trigger(
            EventName.ACTION_INTENT,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "target", "op": "set", "value": outside.game_object.pk},
        )
        self._deny(wire)
        self._remove_trigger(trigger)

    def test_redirect_retains_context_and_rejects_nonitem(self):
        coat = self._equip("Visible coat", EquipmentLayer.OVER)
        trigger = self._trigger(
            EventName.ACTION_INTENT,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "target", "op": "set", "value": self.item.game_object.pk},
        )
        self._deny(self._wire(coat, owner_persona_id=self.mask.pk))
        self._remove_trigger(trigger)
        fixture = ObjectDBFactory(location=self.room)
        self._trigger(
            EventName.ACTION_INTENT,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "target", "op": "set", "value": fixture.pk},
        )
        self._deny(self._wire())

    def test_execute_reresolves_after_availability(self):
        original = LookAtItemAction.check_availability

        def move_after_check(action, actor, target=None, context=None):
            result = original(action, actor, target=target, context=context)
            self.item.game_object.location = self.remote
            return result

        with patch.object(LookAtItemAction, "check_availability", move_after_check):
            self._deny(self._wire())

    def test_physical_extras_once_row_only_none(self):
        self.item.game_object.location = self.room
        pre = self._trigger(EventName.EXAMINE_PRE)
        post = self._trigger(EventName.EXAMINED)
        with (
            patch(
                "actions.definitions.examine_extras.gather_examine_extras",
                wraps=examine_extras.gather_examine_extras,
            ) as gather,
            patch(
                "actions.definitions.examine_extras._maybe_render_crafted_provenance",
                wraps=examine_extras._maybe_render_crafted_provenance,
            ) as provenance,
            patch(
                "actions.definitions.examine_extras._maybe_render_catering_history",
                wraps=examine_extras._maybe_render_catering_history,
            ) as catering,
            patch(
                "world.missions.services.trigger_dispatch.maybe_dispatch_on_examine",
                wraps=maybe_dispatch_on_examine,
            ) as mission,
        ):
            assert self._post()["success"] is True
            gather.assert_called_once_with(self.actor, self.item.game_object)
            provenance.assert_called_once_with(self.item.game_object)
            catering.assert_called_once_with(self.item.game_object)
            mission.assert_called_once_with(self.actor, self.item.game_object)
            row = self._item(None, "Row cup", physical=False)
            assert self._post(self._wire(row))["success"] is True
            assert gather.call_count == 1
        assert self.room.trigger_handler.fire_count(pre.pk) == 1
        assert self.room.trigger_handler.fire_count(post.pk) == 1

    def _mission_fixture(self):
        template = MissionTemplateFactory(name="Typed examine mission")
        MissionNodeFactory(template=template, key="entry", is_entry=True)
        giver = MissionGiverFactory(
            giver_kind=GiverKind.ENVIRONMENTAL_DETAIL,
            target=self.item.game_object,
        )
        giver.templates.add(template)
        return template

    def test_real_reactive_provenance_catering_and_mission_outcomes(self):
        self.item.game_object.location = self.room
        quality = QualityTierFactory(name="Fine", numeric_min=40, numeric_max=59, sort_order=4)
        self.item.quality_tier = quality
        self.item.save(update_fields=["quality_tier"])
        event = EventFactory(name="Cup banquet")
        EventCatering.objects.create(
            event=event,
            item_instance=self.item,
            role=CateringRole.CONTAINER,
        )
        self._trigger(
            EventName.EXAMINE_PRE,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "sections", "op": "set", "value": ["The cup glimmers."]},
        )
        template = self._mission_fixture()
        check = LookAtItemAction().check_availability(
            self.actor,
            context={"kwargs": {"menu_target": self._wire()}},
        )
        assert check.available
        assert not MissionInstance.objects.filter(template=template).exists()
        result = self._post()
        assert result["success"] is True
        assert result["message"].count("The cup glimmers.") == 1
        assert result["message"].count("Of fine quality.") == 1
        assert result["message"].count("Cup banquet") == 1
        assert (
            MissionInstance.objects.filter(
                template=template,
                participants__character_id=self.actor.pk,
            ).count()
            == 1
        )

    def test_cancelled_physical_examine_never_runs_mission_or_object_extras(self):
        self.item.game_object.location = self.room
        template = self._mission_fixture()
        self._trigger(EventName.EXAMINE_PRE, action=FlowActionChoices.CANCEL_EVENT)
        with patch(
            "actions.definitions.examine_extras._maybe_render_crafted_provenance",
            wraps=examine_extras._maybe_render_crafted_provenance,
        ) as provenance:
            result = self._post()
            assert result["success"] is True
            assert result["message"] == ""
            provenance.assert_not_called()
        assert not MissionInstance.objects.filter(template=template).exists()

    def test_malformed_and_hidden_redirects_are_neutral(self):
        destination = self._item(self.room, "Hidden redirected cup")
        self._conceal(destination.game_object)
        for value in (None, True, "1", [], {}, 0, -1, 999999999, destination.game_object.pk):
            trigger = self._trigger(
                EventName.ACTION_INTENT,
                action=FlowActionChoices.MODIFY_PAYLOAD,
                parameters={"field": "target", "op": "set", "value": value},
            )
            self._deny(self._wire())
            self._remove_trigger(trigger)

    def test_mask_replacement_and_holder_change_after_read(self):
        coat = self._equip("Visible coat", EquipmentLayer.OVER)
        wire = self._wire(coat, owner_persona_id=self.mask.pk)
        action = LookAtItemAction()
        assert action.check_availability(
            self.actor,
            context={"kwargs": {"menu_target": wire}},
        ).available
        replacement = create_mask(self.other_sheet, name="A New Hood")
        set_active_persona(self.other_sheet, replacement)
        self._deny(wire)
        wire = self._wire(coat, owner_persona_id=replacement.pk)
        assert action.check_availability(
            self.actor,
            context={"kwargs": {"menu_target": wire}},
        ).available
        coat.holder_character_sheet = self.sheet
        coat.save(update_fields=["holder_character_sheet"])
        self._deny(wire)
