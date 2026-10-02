"""Typed equipment journeys and read-only action checks."""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from actions.definitions.items import EquipAction, UnequipAction
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from flows.object_states.item_state import ItemState
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.exceptions import ItemPlacedNotEquippable, NotEquipped, NotInPossession
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, TemplateSlotFactory
from world.items.models import EquippedItem
from world.items.services.equip import equip_item
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.services import create_mask, set_active_persona


class TypedItemEquipmentTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.entry = RosterEntryFactory()
        self.sheet = self.entry.character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        assert self.actor.pk == self.sheet.pk
        self.account = AccountFactory(is_staff=False)
        RosterTenureFactory(
            player_data=PlayerDataFactory(account=self.account),
            roster_entry=self.entry,
            start_date=timezone.now(),
            end_date=None,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.item = self._item("Exact coat", pk=920001)
        self.other_sheet = RosterEntryFactory().character_sheet
        self.wearer = self.other_sheet.character
        self.wearer.location = self.room
        self.mask = create_mask(self.other_sheet, name="A Grey Hood")
        set_active_persona(self.other_sheet, self.mask)

    def _item(self, name, *, pk=None, physical=True, equipment=True, location=None):
        template = ItemTemplateFactory(name=name)
        if equipment:
            for region in (BodyRegion.TORSO, BodyRegion.HEAD):
                TemplateSlotFactory(
                    template=template, body_region=region, equipment_layer=EquipmentLayer.BASE
                )
        obj = ObjectDBFactory(db_key=name, location=location or self.actor) if physical else None
        return ItemInstanceFactory(
            template=template,
            game_object=obj,
            holder_character_sheet=self.sheet,
            **({"pk": pk} if pk is not None else {}),
        )

    def _wire(self, item=None, **context):
        return {"kind": "items", "target_id": (item or self.item).pk, **context}

    def _post(self, key="equip", *, kwargs=None):
        response = self.client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {
                "ref": {"backend": "registry", "registry_key": key},
                "kwargs": {"menu_target": self._wire()} if kwargs is None else kwargs,
            },
            format="json",
        )
        assert response.status_code == 200, response.data
        return response.data

    def _deny(self, wire, key="equip", **extra):
        result = self._post(key, kwargs={"menu_target": wire, **extra})
        assert result == {
            "backend": "registry",
            "deferred": False,
            "data": None,
            "success": False,
            "message": "That isn't available.",
        }
        return result

    def _availability(self, action, wire=None):
        return action.check_availability(
            self.actor, context={"kwargs": {"menu_target": self._wire() if wire is None else wire}}
        )

    def _trigger(self, event, action=None, parameters=None, variable_name=None):
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

    def _remove(self, trigger):
        trigger.delete()
        self.room.trigger_handler.refresh()

    def test_ac1_exact_rest_ids_multiregion_auto_swap_and_unequip(self):
        assert self.item.pk != self.item.game_object.pk
        decoy = self._item("Different ID domain", pk=self.item.game_object.pk)
        assert self._post()["success"] is True
        assert (
            EquippedItem.objects.filter(character=self.sheet, item_instance=self.item).count() == 2
        )
        assert not EquippedItem.objects.filter(item_instance=decoy).exists()
        replacement = self._item("Replacement")
        assert self._availability(EquipAction(), self._wire(replacement)).available
        assert self._post(kwargs={"menu_target": self._wire(replacement)})["success"]
        assert not EquippedItem.objects.filter(item_instance=self.item).exists()
        assert EquippedItem.objects.filter(item_instance=replacement).count() == 2
        assert self._post("unequip", kwargs={"menu_target": self._wire(replacement)})["success"]
        assert not EquippedItem.objects.filter(item_instance=replacement).exists()
        assert replacement.game_object.location == self.actor
        assert replacement.holder_character_sheet == self.sheet

    def test_ac2_semantic_omission_and_legacy_noop(self):
        equip, unequip = EquipAction(), UnequipAction()
        assert equip.is_applicable(self.actor, kwargs={"menu_target": self._wire()})
        assert not unequip.is_applicable(self.actor, kwargs={"menu_target": self._wire()})
        for item in (
            self._item("Cup", equipment=False),
            self._item("Row", physical=False),
            self._item("Room coat", location=self.room),
        ):
            assert not equip.is_applicable(self.actor, kwargs={"menu_target": self._wire(item)})
            self._deny(self._wire(item))
        assert self._post()["success"]
        assert not equip.is_applicable(self.actor, kwargs={"menu_target": self._wire()})
        assert unequip.is_applicable(self.actor, kwargs={"menu_target": self._wire()})
        count = EquippedItem.objects.count()
        assert equip.run(self.actor, target=self.item.game_object).success
        assert EquippedItem.objects.count() == count
        self._deny(self._wire())
        self.item.game_object.location = self.wearer
        self.item.holder_character_sheet = self.other_sheet
        self.item.save(update_fields=["holder_character_sheet"])
        EquippedItem.objects.filter(item_instance=self.item).delete()
        equip_item(
            character_sheet=self.other_sheet,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        wire = self._wire(owner_persona_id=self.mask.pk)
        assert not equip.is_applicable(self.actor, kwargs={"menu_target": wire})
        assert not unequip.is_applicable(self.actor, kwargs={"menu_target": wire})
        self._deny(wire)
        self._deny(wire, "unequip")

    def test_ac3_actual_shared_denial_reasons_match_run(self):
        for predicate, message in (
            ("permission", NotInPossession.user_message),
            ("placement", ItemPlacedNotEquippable.user_message),
        ):
            seam = (
                patch.object(ItemState, "can_equip", return_value=False)
                if predicate == "permission"
                else patch("world.items.polish_services.can_equip_item", return_value=False)
            )
            with seam:
                action = EquipAction()
                assert action.is_applicable(self.actor, kwargs={"menu_target": self._wire()})
                availability = self._availability(action)
                assert availability.reasons == [message]
                result = self._post()
                assert not result["success"]
                assert result["message"] == "; ".join(availability.reasons)
                assert not EquippedItem.objects.filter(item_instance=self.item).exists()
        action = UnequipAction()
        availability = action.check_availability(
            self.actor,
            target=self.item.game_object,
            context={"kwargs": {"target": self.item.game_object}},
        )
        assert availability.reasons == [NotEquipped.user_message]
        assert (
            action.run(self.actor, target=self.item.game_object).message == NotEquipped.user_message
        )

    def test_ac4_malformed_mixed_and_unavailable_equivalence(self):
        for key in ("equip", "unequip"):
            wires = [
                None,
                [],
                3,
                {},
                {"kind": "objects", "target_id": self.item.game_object.pk},
                {**self._wire(), "label": "trust me"},
                {
                    **self._wire(),
                    "owner_persona_id": self.mask.pk,
                    "container_item_id": self.item.pk,
                },
            ]
            for wire in wires:
                self._deny(wire, key)
            for field in ("target_id", "owner_persona_id", "container_item_id"):
                for value in (True, False, 0, -1, "1", 1.0, None, [], {}):
                    self._deny({**self._wire(), field: value}, key)
            for field in (
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
                self._deny(self._wire(), key, **{field: None})
        absent = self._deny({"kind": "items", "target_id": 999999999})
        assert self._availability(EquipAction()).available
        self.item.game_object.location = self.remote
        assert self._deny(self._wire()) == absent
        self.item.game_object.location = self.actor
        condition = ConditionInstanceFactory(
            target=self.item.game_object,
            condition=ConditionTemplateFactory(
                category=ConditionCategoryFactory(conceals_from_perception=True)
            ),
        )
        assert self._deny(self._wire()) == absent
        condition.delete()
        self.item.destroyed_at = timezone.now()
        self.item.save(update_fields=["destroyed_at"])
        assert self._deny(self._wire()) == absent

    def test_ac5_real_intent_redirect_and_cancellation(self):
        destination = self._item("Redirect destination")
        for service in (False, True):
            trigger = self._trigger(
                EventName.ACTION_INTENT,
                action=FlowActionChoices.CALL_SERVICE_FUNCTION
                if service
                else FlowActionChoices.MODIFY_PAYLOAD,
                parameters={"payload": "@payload", "object_id": destination.game_object.pk}
                if service
                else {"field": "target", "op": "set", "value": destination.game_object.pk},
                variable_name="flows.service_functions.actions.redirect_action_target"
                if service
                else None,
            )
            assert self._post()["success"]
            assert EquippedItem.objects.filter(item_instance=destination).count() == 2
            assert not EquippedItem.objects.filter(item_instance=self.item).exists()
            self._remove(trigger)
            assert self._post("unequip", kwargs={"menu_target": self._wire(destination)})["success"]
        for value in (destination.game_object.pk, self.room.pk, "wrong", None, True):
            destination.game_object.location = self.remote
            trigger = self._trigger(
                EventName.ACTION_INTENT,
                action=FlowActionChoices.MODIFY_PAYLOAD,
                parameters={"field": "target", "op": "set", "value": value},
            )
            self._deny(self._wire())
            self._remove(trigger)
        trigger = self._trigger(EventName.ACTION_INTENT, action=FlowActionChoices.CANCEL_EVENT)
        result = self._post()
        assert not result["success"]
        assert result["message"] == "Something prevents you."
        assert not EquippedItem.objects.filter(item_instance=self.item).exists()
        self._remove(trigger)

    def test_ac5_rest_unequip_redirect_between_visible_owned_worn_items(self):
        from world.items.services.appearance import visible_worn_items_for

        persona = create_mask(self.sheet, name="Own equipment wearer")
        set_active_persona(self.sheet, persona)
        source = self._item("Worn torso source", equipment=False)
        destination = self._item("Worn head destination", equipment=False)
        for item, region in ((source, BodyRegion.TORSO), (destination, BodyRegion.HEAD)):
            TemplateSlotFactory(
                template=item.template, body_region=region, equipment_layer=EquipmentLayer.BASE
            )
        source_row = equip_item(
            character_sheet=self.sheet,
            item_instance=source,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        source_wire = self._wire(source, owner_persona_id=persona.pk)
        destination_wire = self._wire(destination, owner_persona_id=persona.pk)
        for service in (False, True):
            with self.subTest(service=service):
                destination_row = equip_item(
                    character_sheet=self.sheet,
                    item_instance=destination,
                    body_region=BodyRegion.HEAD,
                    equipment_layer=EquipmentLayer.BASE,
                )
                visible_ids = {
                    row.item_instance.pk
                    for row in visible_worn_items_for(self.actor, observer=self.actor)
                }
                assert {source.pk, destination.pk} <= visible_ids
                assert self._availability(UnequipAction(), source_wire).available
                assert self._availability(UnequipAction(), destination_wire).available
                trigger = self._trigger(
                    EventName.ACTION_INTENT,
                    action=FlowActionChoices.CALL_SERVICE_FUNCTION
                    if service
                    else FlowActionChoices.MODIFY_PAYLOAD,
                    parameters={"payload": "@payload", "object_id": destination.game_object.pk}
                    if service
                    else {"field": "target", "op": "set", "value": destination.game_object.pk},
                    variable_name="flows.service_functions.actions.redirect_action_target"
                    if service
                    else None,
                )
                try:
                    result = self._post("unequip", kwargs={"menu_target": source_wire})
                    assert result["success"] is True, result
                    assert self.room.trigger_handler.fire_count(trigger.pk) == 1
                    assert EquippedItem.objects.filter(
                        pk=source_row.pk,
                        character=self.sheet,
                        item_instance=source,
                        body_region=BodyRegion.TORSO,
                        equipment_layer=EquipmentLayer.BASE,
                    ).exists()
                    assert not EquippedItem.objects.filter(pk=destination_row.pk).exists()
                    assert not EquippedItem.objects.filter(
                        character=self.sheet, item_instance=destination
                    ).exists()
                finally:
                    self._remove(trigger)
                    EquippedItem.objects.filter(pk=destination_row.pk).delete()

    def test_ac5_container_and_owner_assertions_survive_redirects(self):
        bag_template = ItemTemplateFactory(
            is_container=True, supports_open_close=True, container_capacity=10
        )
        bag = ItemInstanceFactory(
            template=bag_template,
            holder_character_sheet=self.sheet,
            game_object=ObjectDBFactory(location=self.actor),
            is_open=True,
        )
        sibling = self._item("Contained sibling")
        for item in (self.item, sibling):
            item.game_object.location = bag.game_object
            item.contained_in = bag
            item.save(update_fields=["contained_in"])
        trigger = self._trigger(
            EventName.ACTION_INTENT,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "target", "op": "set", "value": sibling.game_object.pk},
        )
        assert self._post(kwargs={"menu_target": self._wire(container_item_id=bag.pk)})["success"]
        assert EquippedItem.objects.filter(item_instance=sibling).exists()
        self._remove(trigger)
        outside = self._item("Outside bag")
        trigger = self._trigger(
            EventName.ACTION_INTENT,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "target", "op": "set", "value": outside.game_object.pk},
        )
        self._deny(self._wire(container_item_id=bag.pk))
        self._remove(trigger)
        assert self._post(kwargs={"menu_target": self._wire(outside)})["success"]
        foreign = self._item("Visible foreign coat", location=self.wearer)
        foreign.holder_character_sheet = self.other_sheet
        foreign.save(update_fields=["holder_character_sheet"])
        equip_item(
            character_sheet=self.other_sheet,
            item_instance=foreign,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        assert self._availability(UnequipAction(), self._wire(outside)).available
        trigger = self._trigger(
            EventName.ACTION_INTENT,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={"field": "target", "op": "set", "value": outside.game_object.pk},
        )
        self._deny(self._wire(foreign, owner_persona_id=self.mask.pk), "unequip")
        assert EquippedItem.objects.filter(item_instance=outside, character=self.sheet).exists()
        self._remove(trigger)

    def test_ac6_read_only_and_execute_reresolution(self):
        intent = self._trigger(EventName.ACTION_INTENT)
        result = self._trigger(EventName.ACTION_RESULT)
        objects_before = ObjectDBFactory._meta.model.objects.count()
        with (
            CaptureQueriesContext(connection) as queries,
            patch(
                "flows.scene_data_manager.SceneDataManager.initialize_state_for_object",
                side_effect=AssertionError("read initialized state"),
            ),
            patch("flows.emit.emit_event", side_effect=AssertionError("read emitted event")),
        ):
            for _ in range(3):
                assert EquipAction().is_applicable(self.actor, kwargs={"menu_target": self._wire()})
                assert self._availability(EquipAction()).available
        forbidden = ("INSERT", "UPDATE", "DELETE", "FOR UPDATE")
        assert not [
            q["sql"]
            for q in queries.captured_queries
            if q["sql"].lstrip().upper().startswith(forbidden) or "FOR UPDATE" in q["sql"].upper()
        ], queries.captured_queries
        assert ObjectDBFactory._meta.model.objects.count() == objects_before
        assert self.room.trigger_handler.fire_count(intent.pk) == 0
        assert self.room.trigger_handler.fire_count(result.pk) == 0
        assert not EquippedItem.objects.filter(item_instance=self.item).exists()
        original = EquipAction.check_availability

        def move_after_check(
            action, actor, target=None, context=None, *, pending_inputs=frozenset()
        ):
            checked = original(
                action, actor, target=target, context=context, pending_inputs=pending_inputs
            )
            self.item.game_object.location = self.remote
            return checked

        with patch.object(EquipAction, "check_availability", move_after_check):
            self._deny(self._wire())

    def test_ac6_locked_service_item_error_is_business_refusal(self):
        with patch("actions.definitions.items.equip", side_effect=ItemPlacedNotEquippable):
            result = self._post()
        assert not result["success"]
        assert result["message"] == ItemPlacedNotEquippable.user_message

    def test_ac7_legacy_resolved_instance_and_object_inputs(self):
        assert EquipAction().run(self.actor, target=self.item).success
        assert UnequipAction().run(self.actor, target=self.item.game_object).success
        assert EquipAction().run(self.actor).message == "Equip what?"
        assert UnequipAction().run(self.actor).message == "Remove what?"
