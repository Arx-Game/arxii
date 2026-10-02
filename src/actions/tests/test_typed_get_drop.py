"""Typed Get/Drop REST journeys and shared nonmutating checks."""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from actions.definitions.item_helpers import resolve_typed_item, typed_item_request
from actions.definitions.movement import DropAction, GetAction
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from flows.object_states.character_state import CharacterState
from flows.object_states.item_state import ItemState
from flows.scene_data_manager import SceneDataManager
from flows.service_functions.inventory import validate_drop, validate_pick_up
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.items.constants import BodyRegion, ContainerAccessPolicy, EquipmentLayer
from world.items.exceptions import (
    ContainerAccessDenied,
    ItemFixedInPlace,
    NoDropLocation,
    NotInPossession,
    NotReachable,
    OwnedByAnother,
    VaultAccessDenied,
    VaultFull,
)
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, TemplateSlotFactory
from world.items.models import EquippedItem
from world.items.services.equip import equip_item
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.room_features.models import VaultDetails
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.services import create_mask, set_active_persona


class TypedGetDropTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.entry = RosterEntryFactory()
        self.sheet = self.entry.character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        self.other_sheet = RosterEntryFactory().character_sheet
        self.account = AccountFactory(is_staff=False)
        RosterTenureFactory(
            player_data=PlayerDataFactory(account=self.account),
            roster_entry=self.entry,
            start_date=timezone.now(),
            end_date=None,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.item = self._item("Exact room item", pk=930001)

    def _item(self, name, *, pk=None, location=None, holder=None, physical=True):
        obj = (
            ObjectDBFactory(
                db_key=name,
                db_typeclass_path="typeclasses.objects.Object",
                location=self.room if location is None else location,
            )
            if physical
            else None
        )
        return ItemInstanceFactory(
            template=ItemTemplateFactory(name=name),
            game_object=obj,
            holder_character_sheet=holder,
            **({"pk": pk} if pk is not None else {}),
        )

    def _wire(self, item=None, kind="items", **assertions):
        item = self.item if item is None else item
        return {
            "kind": kind,
            "target_id": item.pk if kind == "items" else item.game_object.pk,
            **assertions,
        }

    def _post(self, key, wire=None, **extra):
        response = self.client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {
                "ref": {"backend": "registry", "registry_key": key},
                "kwargs": {"menu_target": self._wire() if wire is None else wire, **extra},
            },
            format="json",
        )
        assert response.status_code == 200, response.data
        return response.data

    def _deny(self, key, wire, **extra):
        result = self._post(key, wire, **extra)
        assert result == {
            "backend": "registry",
            "deferred": False,
            "data": None,
            "success": False,
            "message": "That isn't available.",
        }, result
        return result

    def _read(self, action, wire):
        return action.check_availability(self.actor, context={"kwargs": {"menu_target": wire}})

    def _fit(self, action, wire):
        return action.is_applicable(self.actor, kwargs={"menu_target": wire})

    def _matches(self, key, wire, error):
        action = GetAction() if key == "get" else DropAction()
        assert self._fit(action, wire)
        checked = self._read(action, wire)
        assert checked.reasons == [error.user_message], checked
        result = self._post(key, wire)
        assert result["success"] is False
        assert result["message"] == "; ".join(checked.reasons)

    def _trigger(
        self, action=None, parameters=None, variable_name="", event=EventName.ACTION_INTENT
    ):
        flow = FlowDefinitionFactory()
        if action is not None:
            FlowStepDefinitionFactory(
                flow=flow,
                parent_id=None,
                action=action,
                parameters=parameters or {},
                variable_name=variable_name,
            )
        trigger = TriggerFactory(
            trigger_definition=TriggerDefinitionFactory(event_name=event, flow_definition=flow),
            obj=self.room,
        )
        self.room.trigger_handler.refresh()
        return trigger

    def _remove(self, trigger):
        trigger.delete()
        self.room.trigger_handler.refresh()

    def _vault(self, founder=None, capacity=1):
        instance = RoomFeatureInstanceFactory(
            room_profile=self.room.room_profile,
            feature_kind=RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.VAULT),
            level=1,
        )
        return VaultDetails.objects.create(
            feature_instance=instance,
            founder_persona=(self.sheet if founder is None else founder).primary_persona,
            max_items=capacity,
        )

    def _wear(self, item):
        for region in (BodyRegion.TORSO, BodyRegion.HEAD):
            TemplateSlotFactory(
                template=item.template, body_region=region, equipment_layer=EquipmentLayer.BASE
            )
        for region in (BodyRegion.TORSO, BodyRegion.HEAD):
            equip_item(
                character_sheet=self.sheet,
                item_instance=item,
                body_region=region,
                equipment_layer=EquipmentLayer.BASE,
            )

    def test_ac1_items_rest_exact_ids_and_ordinary_drop_ownership(self):
        assert self.item.pk != self.item.game_object.pk
        decoy = self._item("ID-domain decoy", pk=self.item.game_object.pk)
        assert self._read(GetAction(), self._wire()).available
        assert self._post("get")["success"]
        assert self.item.game_object.location == self.actor
        assert self.item.holder_character_sheet == self.sheet
        assert decoy.game_object.location == self.room
        assert self._read(DropAction(), self._wire()).available
        assert self._post("drop")["success"]
        assert self.item.game_object.location == self.room
        assert self.item.holder_character_sheet == self.sheet
        assert decoy.game_object.location == self.room

    def test_success_messages_use_current_public_item_name_without_owner_identity(self):
        self.item.custom_name = "A silver keepsake"
        self.item.holder_character_sheet = self.other_sheet
        self.item.save(update_fields=["custom_name", "holder_character_sheet"])
        self.item.game_object.location = self.actor
        with patch.object(self.actor, "msg") as messages:
            assert self._post("drop")["success"]
        text = " ".join(str((call.args, call.kwargs)) for call in messages.call_args_list)
        assert self.item.display_name in text
        assert self.other_sheet.character.key not in text
        self.item.holder_character_sheet = None
        self.item.custom_name = "A renamed silver keepsake"
        self.item.save(update_fields=["holder_character_sheet", "custom_name"])
        with patch.object(self.actor, "msg") as messages:
            assert self._post("get")["success"]
        text = " ".join(str((call.args, call.kwargs)) for call in messages.call_args_list)
        assert self.item.display_name in text
        assert self.other_sheet.character.key not in text

    def test_ac1_objects_get_actual_relation_and_no_nonitem_get_or_room_drop(self):
        wire = self._wire(kind="objects")
        decoy = self._item("Object-ID decoy", pk=self.item.game_object.pk)
        self._deny("drop", wire)
        assert self._post("get", wire)["success"]
        assert self.item.game_object.location == self.actor
        assert decoy.game_object.location == self.room
        self._deny("get", wire)
        assert self._post("drop", self._wire())["success"]
        fixture = ObjectDBFactory(
            db_typeclass_path="typeclasses.objects.Object", location=self.room
        )
        self._deny("get", {"kind": "objects", "target_id": fixture.pk})
        self._deny("drop", {"kind": "objects", "target_id": fixture.pk})

    def test_ac2_fit_ownership_is_not_possession_and_worn_drop(self):
        owned_room = self._item("Own room item", holder=self.sheet)
        assert not self._fit(GetAction(), self._wire(owned_room))
        self._deny("get", self._wire(owned_room))
        assert GetAction().run(self.actor, target=owned_room.game_object).success
        assert self._fit(DropAction(), self._wire(owned_room))
        owned_room.holder_character_sheet = self.other_sheet
        owned_room.save(update_fields=["holder_character_sheet"])
        self._wear(owned_room)
        assert not self._fit(GetAction(), self._wire(owned_room))
        assert self._read(DropAction(), self._wire(owned_room)).available
        assert self._post("drop", self._wire(owned_room))["success"]
        assert not EquippedItem.objects.filter(item_instance=owned_room).exists()
        assert owned_room.holder_character_sheet == self.other_sheet
        assert not self._fit(DropAction(), self._wire(owned_room))
        row = self._item("Row only", physical=False, holder=self.sheet)
        for key, action in (("get", GetAction()), ("drop", DropAction())):
            assert not self._fit(action, self._wire(row))
            self._deny(key, self._wire(row))

    def test_ac2_other_wearer_and_private_inventory_are_not_shortcuts(self):
        wearer = self.other_sheet.character
        wearer.location = self.room
        persona = create_mask(self.other_sheet, name="A Grey Hood")
        set_active_persona(self.other_sheet, persona)
        foreign = self._item("Exposed foreign coat", location=wearer, holder=self.other_sheet)
        TemplateSlotFactory(
            template=foreign.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        equip_item(
            character_sheet=self.other_sheet,
            item_instance=foreign,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        wire = self._wire(foreign, owner_persona_id=persona.pk)
        private = self._item("Private carried item", location=wearer, holder=self.other_sheet)
        for key, action in (("get", GetAction()), ("drop", DropAction())):
            assert not self._fit(action, wire)
            self._deny(key, wire)
            self._deny(key, self._wire(private))
        own = self._item("Own carried item", location=self.actor, holder=self.sheet)
        self._deny("drop", self._wire(own, owner_persona_id=persona.pk))
        assert foreign.game_object.location == wearer
        assert EquippedItem.objects.filter(item_instance=foreign).exists()

    def test_ac2_exposed_carried_content_drop_and_no_get_shortcut(self):
        bag = self._item("Bag", location=self.actor, holder=self.sheet)
        bag.template.is_container = True
        bag.template.supports_open_close = True
        bag.template.save()
        bag.is_open = True
        bag.save(update_fields=["is_open"])
        self.item.contained_in = bag
        self.item.save(update_fields=["contained_in"])
        self.item.game_object.location = bag.game_object
        wire = self._wire(container_item_id=bag.pk)
        assert not self._fit(GetAction(), wire)
        self._deny("get", wire)
        assert self._fit(DropAction(), wire)
        assert self._post("drop", wire)["success"]
        assert self.item.contained_in is None
        assert self.item.game_object.location == self.room

    def test_ac3_shared_take_and_drop_predicates(self):
        self.item.holder_character_sheet = self.other_sheet
        self.item.save(update_fields=["holder_character_sheet"])
        self._matches("get", self._wire(), OwnedByAnother)
        self.item.holder_character_sheet = None
        self.item.save(update_fields=["holder_character_sheet"])
        with patch(
            "flows.service_functions.inventory._placed_as_active_decoration", return_value=True
        ):
            self._matches("get", self._wire(), ItemFixedInPlace)
        with (
            patch.object(ItemState, "can_take", return_value=False),
            patch("world.npc_services.servant_fetch.can_servant_fetch", return_value=False),
        ):
            self._matches("get", self._wire(), NotReachable)
        assert self._post("get")["success"]
        with patch.object(ItemState, "can_drop", return_value=False):
            self._matches("drop", self._wire(), NotInPossession)
        self.actor.location = None
        self._matches("drop", self._wire(), NoDropLocation)

    def test_ac3_real_container_policy_legacy_parity_and_typed_get_omission(self):
        chest = self._item("Policy chest", holder=self.other_sheet)
        chest.template.is_container = True
        chest.template.supports_open_close = True
        chest.template.save(update_fields=["is_container", "supports_open_close"])
        chest.is_open = True
        chest.access_policy = ContainerAccessPolicy.OWNER_ONLY
        chest.save(update_fields=["is_open", "access_policy"])
        self.item.contained_in = chest
        self.item.save(update_fields=["contained_in"])
        self.item.game_object.location = chest.game_object
        before = (
            self.item.game_object.location,
            self.item.contained_in,
            self.item.holder_character_sheet,
            chest.game_object.location,
            chest.holder_character_sheet,
            chest.access_policy,
            chest.is_open,
        )
        action = GetAction()
        wire = self._wire(container_item_id=chest.pk)
        resolved = resolve_typed_item(self.actor, {"menu_target": wire})
        assert resolved is not None
        assert resolved.item == self.item
        assert not self._fit(action, wire)
        assert self._read(action, wire).reasons == ["That isn't available."]
        self._deny("get", wire)
        sdm = SceneDataManager()
        actor_state = CharacterState(self.actor, context=sdm)
        item_state = ItemState(self.item, context=sdm)
        assert item_state.can_take(taker=actor_state)
        with self.assertRaises(ContainerAccessDenied) as denied:
            validate_pick_up(actor_state, item_state)
        assert denied.exception.user_message == ContainerAccessDenied.user_message
        kwargs = {"target": self.item.game_object}
        with (
            patch("world.npc_services.servant_fetch.can_servant_fetch") as eligible,
            patch("world.npc_services.servant_fetch.servant_fetch_item") as queue,
        ):
            checked = action.check_availability(self.actor, context={"kwargs": kwargs})
            assert not checked.available
            assert checked.reasons == [ContainerAccessDenied.user_message]
            result = action.run(self.actor, **kwargs)
            assert not result.success
            assert result.message == "; ".join(checked.reasons)
            eligible.assert_not_called()
            queue.assert_not_called()
        assert (
            self.item.game_object.location,
            self.item.contained_in,
            self.item.holder_character_sheet,
            chest.game_object.location,
            chest.holder_character_sheet,
            chest.access_policy,
            chest.is_open,
        ) == before
        assert self.item.game_object.db_location_id == chest.game_object.pk
        assert self.item.__class__.objects.filter(
            pk=self.item.pk,
            contained_in=chest,
            holder_character_sheet__isnull=True,
            game_object__db_location=chest.game_object,
        ).exists()
        assert chest.__class__.objects.filter(
            pk=chest.pk,
            holder_character_sheet=self.other_sheet,
            access_policy=ContainerAccessPolicy.OWNER_ONLY,
            is_open=True,
            game_object__db_location=self.room,
        ).exists()
        assert not EquippedItem.objects.filter(item_instance=self.item).exists()

    def test_ac3_real_vault_deposit_take_access_and_capacity_preserves_worn_state(self):
        self.item.game_object.location = self.actor
        self.item.holder_character_sheet = self.sheet
        self.item.save(update_fields=["holder_character_sheet"])
        self._wear(self.item)
        vault = self._vault(founder=self.other_sheet)
        blocker = self._item("Vault capacity blocker")
        self._matches("drop", self._wire(), VaultFull)
        assert EquippedItem.objects.filter(item_instance=self.item).count() == 2
        assert self.item.game_object.location == self.actor
        assert self.item.holder_character_sheet == self.sheet
        sdm = SceneDataManager()
        with self.assertRaises(VaultFull):
            validate_drop(
                CharacterState(self.actor, context=sdm), ItemState(self.item, context=sdm)
            )
        assert EquippedItem.objects.filter(item_instance=self.item).count() == 2
        blocker.game_object.location = self.remote
        assert self._post("drop")["success"]
        assert not EquippedItem.objects.filter(item_instance=self.item).exists()
        assert self.item.holder_character_sheet is None
        self._matches("get", self._wire(), VaultAccessDenied)
        vault.founder_persona = self.sheet.primary_persona
        vault.save(update_fields=["founder_persona"])
        assert self._post("get")["success"]
        assert self.item.holder_character_sheet == self.sheet

    def test_ac4_legacy_servant_fallback_and_reachable_owner_denial(self):
        self.item.game_object.location = self.remote
        self.item.holder_character_sheet = self.other_sheet
        self.item.save(update_fields=["holder_character_sheet"])
        kwargs = {"target": self.item.game_object}
        with (
            patch(
                "world.npc_services.servant_fetch.can_servant_fetch", return_value=True
            ) as eligible,
            patch(
                "world.npc_services.servant_fetch.servant_fetch_item", return_value=True
            ) as queue,
        ):
            checked = GetAction().check_availability(self.actor, context={"kwargs": kwargs})
            assert checked.available
            queue.assert_not_called()
            result = GetAction().run(self.actor, **kwargs)
            assert result.success
            assert result.message == "A servant bows and departs to fetch that."
            queue.assert_called_once_with(actor=self.actor, item_instance=self.item)
            self._deny("get", self._wire())
            assert queue.call_count == 1
        with patch("world.npc_services.servant_fetch.can_servant_fetch", return_value=False):
            checked = GetAction().check_availability(self.actor, context={"kwargs": kwargs})
            assert checked.reasons == [NotReachable.user_message]
            assert GetAction().run(self.actor, **kwargs).message == NotReachable.user_message
        self.item.game_object.location = self.room
        with patch("world.npc_services.servant_fetch.can_servant_fetch") as eligible:
            self._matches("get", self._wire(), OwnedByAnother)
            eligible.assert_not_called()

    def test_ac5_strict_domains_mixed_fields_and_unavailable_equivalence(self):
        assert typed_item_request({"menu_target": self._wire(kind="objects")}) is None
        absent = self._deny("get", {"kind": "items", "target_id": 999999999})
        for key in ("get", "drop"):
            self._deny(key, [], menu_target=None)
            for wire in (
                [],
                {},
                {"kind": "places", "target_id": 1},
                {**self._wire(), "label": "untrusted"},
                {**self._wire(kind="objects"), "owner_persona_id": 1},
                {**self._wire(kind="objects"), "container_item_id": 1},
                {**self._wire(), "owner_persona_id": 1, "container_item_id": 1},
            ):
                self._deny(key, wire)
            for field in ("target_id", "owner_persona_id", "container_item_id"):
                for value in (True, False, 0, -1, "1", 1.0, None, [], {}):
                    self._deny(key, {**self._wire(), field: value})
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
                self._deny(key, self._wire(), **{field: None})
        self.item.game_object.location = self.remote
        assert self._deny("get", self._wire()) == absent
        self.item.game_object.location = self.room
        condition = ConditionInstanceFactory(
            target=self.item.game_object,
            condition=ConditionTemplateFactory(
                category=ConditionCategoryFactory(conceals_from_perception=True)
            ),
        )
        assert self._deny("get", self._wire()) == absent
        condition.delete()
        self.item.destroyed_at = timezone.now()
        self.item.save(update_fields=["destroyed_at"])
        assert self._deny("get", self._wire()) == absent

    def test_ac5_objects_malformed_scalars_extra_and_competing_legacy_fields(self):
        wire = self._wire(kind="objects")
        before = (
            self.item.game_object.location,
            self.item.holder_character_sheet,
            self.item.contained_in,
        )
        for key, action in (("get", GetAction()), ("drop", DropAction())):
            for value in (True, False, "1", 1.0, 0, -1, None, [], {}):
                with self.subTest(key=key, target_id=value):
                    malformed = {**wire, "target_id": value}
                    assert self._read(action, malformed).reasons == ["That isn't available."]
                    self._deny(key, malformed)
            malformed = {**wire, "label": "untrusted"}
            assert self._read(action, malformed).reasons == ["That isn't available."]
            self._deny(key, malformed)
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
                with self.subTest(key=key, legacy=field):
                    checked = action.check_availability(
                        self.actor, context={"kwargs": {"menu_target": wire, field: None}}
                    )
                    assert checked.reasons == ["That isn't available."]
                    self._deny(key, wire, **{field: None})
        assert (
            self.item.game_object.location,
            self.item.holder_character_sheet,
            self.item.contained_in,
        ) == before
        assert self.item.__class__.objects.filter(
            pk=self.item.pk,
            contained_in__isnull=True,
            holder_character_sheet__isnull=True,
            game_object__db_location=self.room,
        ).exists()

    def test_ac6_real_intent_domains_redirect_and_cancel(self):
        destination = self._item("Redirect destination")
        for kind in ("items", "objects"):
            for service in (False, True):
                trigger = self._trigger(
                    FlowActionChoices.CALL_SERVICE_FUNCTION
                    if service
                    else FlowActionChoices.MODIFY_PAYLOAD,
                    {"payload": "@payload", "object_id": destination.game_object.pk}
                    if service
                    else {"field": "target", "op": "set", "value": destination.game_object.pk},
                    "flows.service_functions.actions.redirect_action_target" if service else "",
                )
                try:
                    assert self._post("get", self._wire(kind=kind))["success"]
                    assert destination.game_object.location == self.actor
                    assert self.item.game_object.location == self.room
                    destination.game_object.location = self.room
                    destination.holder_character_sheet = None
                    destination.save(update_fields=["holder_character_sheet"])
                finally:
                    self._remove(trigger)
        for value in (self.remote.pk, "bad", None, True):
            trigger = self._trigger(
                FlowActionChoices.MODIFY_PAYLOAD, {"field": "target", "op": "set", "value": value}
            )
            try:
                self._deny("get", self._wire())
            finally:
                self._remove(trigger)
        trigger = self._trigger(FlowActionChoices.CANCEL_EVENT)
        try:
            result = self._post("get")
            assert not result["success"]
            assert result["message"] == "Something prevents you."
            assert self.item.game_object.location == self.room
        finally:
            self._remove(trigger)

    def test_ac6_drop_container_redirect_preserves_scope(self):
        bag = self._item("Redirect bag", location=self.actor, holder=self.sheet)
        bag.template.is_container = True
        bag.template.supports_open_close = True
        bag.template.save()
        bag.is_open = True
        bag.save(update_fields=["is_open"])
        sibling = self._item("Inside sibling")
        outside = self._item("Outside sibling", location=self.actor)
        for item in (self.item, sibling):
            item.contained_in = bag
            item.save(update_fields=["contained_in"])
            item.game_object.location = bag.game_object
        for destination, success in ((outside, False), (sibling, True)):
            trigger = self._trigger(
                FlowActionChoices.MODIFY_PAYLOAD,
                {"field": "target", "op": "set", "value": destination.game_object.pk},
            )
            try:
                result = self._post("drop", self._wire(container_item_id=bag.pk))
                assert result["success"] is success
                assert self.item.contained_in == bag
                assert self.item.game_object.location == bag.game_object
                if success:
                    assert sibling.contained_in is None
                    assert sibling.game_object.location == self.room
                else:
                    assert result["message"] == "That isn't available."
                    assert outside.game_object.location == self.actor
            finally:
                self._remove(trigger)

    def test_ac7_read_only_and_execution_reresolves(self):
        intent = self._trigger()
        result = self._trigger(event=EventName.ACTION_RESULT)
        carried = self._item("Read-only Drop", location=self.actor, holder=self.sheet)
        self._wear(carried)
        count = ObjectDBFactory._meta.model.objects.count()
        with (
            CaptureQueriesContext(connection) as queries,
            patch(
                "flows.scene_data_manager.SceneDataManager.initialize_state_for_object",
                side_effect=AssertionError("read initialized state"),
            ),
            patch("flows.emit.emit_event", side_effect=AssertionError("read emitted event")),
            patch(
                "world.npc_services.servant_fetch.servant_fetch_item",
                side_effect=AssertionError("read queued fetch"),
            ),
        ):
            for _ in range(3):
                assert self._fit(GetAction(), self._wire())
                assert self._read(GetAction(), self._wire()).available
                assert not self._fit(DropAction(), self._wire())
                assert not self._read(DropAction(), self._wire()).available
                assert self._fit(DropAction(), self._wire(carried))
                assert self._read(DropAction(), self._wire(carried)).available
        assert carried.game_object.location == self.actor
        assert carried.holder_character_sheet == self.sheet
        assert EquippedItem.objects.filter(item_instance=carried).count() == 2
        assert not [
            q["sql"]
            for q in queries.captured_queries
            if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
            or "FOR UPDATE" in q["sql"].upper()
        ], queries.captured_queries
        assert ObjectDBFactory._meta.model.objects.count() == count
        assert self.room.trigger_handler.fire_count(intent.pk) == 0
        assert self.room.trigger_handler.fire_count(result.pk) == 0
        assert self.item.game_object.location == self.room
        assert self.item.holder_character_sheet is None
        original = GetAction.check_availability

        def moved(action, actor, target=None, context=None, *, pending_inputs=frozenset()):
            checked = original(
                action, actor, target=target, context=context, pending_inputs=pending_inputs
            )
            self.item.game_object.location = self.remote
            return checked

        with patch.object(GetAction, "check_availability", moved):
            self._deny("get", self._wire())

    def test_ac6_capacity_changes_after_read_preserve_worn_item(self):
        self.item.game_object.location = self.actor
        self.item.holder_character_sheet = self.sheet
        self.item.save(update_fields=["holder_character_sheet"])
        self._wear(self.item)
        vault = self._vault(capacity=1)
        assert self._read(DropAction(), self._wire()).available
        vault.max_items = 0
        vault.save(update_fields=["max_items"])
        self._matches("drop", self._wire(), VaultFull)
        assert self.item.game_object.location == self.actor
        assert self.item.holder_character_sheet == self.sheet
        assert EquippedItem.objects.filter(item_instance=self.item).count() == 2

    def test_ac7_legacy_messages_instances_and_late_service_denial(self):
        assert GetAction().run(self.actor).message == "Get what?"
        assert DropAction().run(self.actor).message == "Drop what?"
        assert GetAction().run(self.actor, target=self.room).message == "That can't be picked up."
        assert DropAction().run(self.actor, target=self.room).message == "That can't be dropped."
        assert GetAction().run(self.actor, target=self.item).success
        with patch("actions.definitions.movement.drop", side_effect=VaultFull):
            result = self._post("drop")
            assert not result["success"]
            assert result["message"] == VaultFull.user_message
        assert DropAction().run(self.actor, target=self.item.game_object).success
