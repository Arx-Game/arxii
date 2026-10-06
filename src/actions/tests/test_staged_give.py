"""Staged Give checks and real typed REST execution."""

from dataclasses import dataclass
from typing import ClassVar
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from actions.base import Action
from actions.definitions.movement import GiveAction
from actions.prerequisites import Prerequisite
from actions.types import ActionResult, TargetType
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from flows.scene_data_manager import SceneDataManager
from world.consent.models import SocialConsentCategory
from world.consent.services import add_social_consent_whitelist, receiving_stolen_goods_category
from world.items.constants import OwnershipEventType
from world.items.exceptions import RecipientConsentDenied
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import OwnershipEvent
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.services import create_mask, set_active_persona


@dataclass
class Probe(Prerequisite):
    required_input_names: ClassVar[frozenset[str]] = frozenset()
    reason: str = "bound blocker"

    def is_met(self, actor, target=None, context=None):
        return False, self.reason


class RecipientProbe(Probe):
    required_input_names = frozenset({"recipient_persona_id"})


class ProbeAction(Action):
    required_input_names = frozenset({"recipient_persona_id"})

    def get_prerequisites(self):
        return [Probe(), RecipientProbe(reason="recipient blocker")]

    def execute(self, actor, context=None, **kwargs):
        return ActionResult(success=True)


class StagedInputTests(SimpleTestCase):
    def setUp(self):
        self.action = ProbeAction("give", "Give", "gift", "items", TargetType.SINGLE)

    def test_ac1_only_declared_missing_dependencies_defer(self):
        with (
            patch.object(Action, "_dead_gate_reason", return_value=""),
            patch.object(Action, "_offscreen_gate_reason", return_value=""),
        ):
            full = self.action.check_availability(None)
            staged = self.action.check_availability(
                None, pending_inputs=frozenset({"recipient_persona_id"})
            )
            assert full.reasons == ["bound blocker", "recipient blocker"]
            assert staged.reasons == ["bound blocker"]
            for pending, kwargs in (
                (frozenset({"unknown"}), {}),
                (frozenset({"recipient_persona_id"}), {"recipient_persona_id": None}),
                (frozenset({"recipient_persona_id"}), {"recipient_persona_id": False}),
            ):
                with self.assertRaises(ValueError):
                    self.action.check_availability(
                        None, context={"kwargs": kwargs}, pending_inputs=pending
                    )

    def test_ac1_builtin_gates_never_defer(self):
        with patch.object(Action, "_dead_gate_reason", return_value="dead"):
            result = self.action.check_availability(
                None, pending_inputs=frozenset({"recipient_persona_id"})
            )
            assert result.reasons == ["dead", "bound blocker"]
        with (
            patch.object(Action, "_dead_gate_reason", return_value=""),
            patch.object(Action, "_offscreen_gate_reason", return_value="offscreen"),
        ):
            assert self.action.check_availability(
                None, pending_inputs=frozenset({"recipient_persona_id"})
            ).reasons == ["offscreen", "bound blocker"]


class TypedGiveTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.entry = RosterEntryFactory()
        self.sheet = self.entry.character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        self.receiver_entry = RosterEntryFactory()
        self.receiver_sheet = self.receiver_entry.character_sheet
        self.receiver = self.receiver_sheet.character
        self.receiver.location = self.room
        self.account = AccountFactory(is_staff=False)
        self.giver_tenure = RosterTenureFactory(
            roster_entry=self.entry,
            player_data=PlayerDataFactory(account=self.account),
            start_date=timezone.now(),
            end_date=None,
        )
        self.receiver_tenure = RosterTenureFactory(
            roster_entry=self.receiver_entry, start_date=timezone.now(), end_date=None
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.item = ItemInstanceFactory(
            pk=950011,
            template=ItemTemplateFactory(name="Selected gift"),
            game_object=ObjectDBFactory(
                location=self.actor, db_typeclass_path="typeclasses.objects.Object"
            ),
            holder_character_sheet=self.sheet,
        )
        self.action = GiveAction()

    def kwargs(self, recipient=True):
        values = {"menu_target": {"kind": "items", "target_id": self.item.pk}}
        if recipient:
            values["recipient_persona_id"] = self.receiver_sheet.primary_persona.pk
        return values

    def read(self, kwargs, pending=frozenset()):
        return self.action.check_availability(
            self.actor, context={"kwargs": kwargs}, pending_inputs=pending
        )

    def post(self, kwargs):
        response = self.client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {"ref": {"backend": "registry", "registry_key": "give"}, "kwargs": kwargs},
            format="json",
        )
        assert response.status_code == 200, response.data
        return response.data

    def unchanged(self):
        assert self.item.game_object.location == self.actor
        assert self.item.holder_character_sheet == self.sheet
        assert not OwnershipEvent.objects.filter(
            item_instance=self.item, event_type=OwnershipEventType.GIVEN
        ).exists()

    def hot(self):
        OwnershipEvent.objects.create(
            item_instance=self.item,
            event_type=OwnershipEventType.STOLEN,
            from_character_sheet=self.receiver_sheet,
            to_character_sheet=self.sheet,
        )

    def test_ac1_missing_choice_pending_not_refusal_execution_never_pending(self):
        bound = self.kwargs(False)
        assert self.read(bound, frozenset({"recipient_persona_id"})).available
        assert not self.read(bound).available
        bound["pending_inputs"] = ["recipient_persona_id"]
        assert not self.post(bound)["success"]
        self.unchanged()
        self.item.game_object.location = self.room
        assert not self.read(self.kwargs(False), frozenset({"recipient_persona_id"})).available

    def test_ac2_rest_exact_item_and_recipient_domains(self):
        assert self.item.pk != self.item.game_object.pk
        assert self.receiver_sheet.primary_persona.pk != self.item.pk
        assert self.read(self.kwargs()).available
        assert self.post(self.kwargs())["success"]
        assert self.item.game_object.location == self.receiver
        assert self.item.holder_character_sheet == self.receiver_sheet
        event = OwnershipEvent.objects.get(
            item_instance=self.item, event_type=OwnershipEventType.GIVEN
        )
        assert event.from_character_sheet == self.sheet
        assert event.to_character_sheet == self.receiver_sheet

    def test_ac2_mixed_invalid_and_wrong_domains_neutral(self):
        bad = []
        for value in (True, False, "1", 0, -1, None, [], {}):
            bad.append({**self.kwargs(), "recipient_persona_id": value})
            bad.append({**self.kwargs(), "menu_target": {"kind": "items", "target_id": value}})
        bad.extend(
            {**self.kwargs(), field: self.receiver.pk}
            for field in ("target", "target_id", "item_instance_id", "recipient", "recipient_id")
        )
        bad.append(
            {
                **self.kwargs(),
                "menu_target": {"kind": "objects", "target_id": self.item.game_object.pk},
            }
        )
        for kwargs in bad:
            with self.subTest(kwargs=kwargs):
                assert self.read(kwargs).reasons == ["That isn't available."]
                assert self.post(kwargs)["message"] == "That isn't available."
                self.unchanged()

    def test_ac3_real_recipient_hook_not_none_probe(self):
        with patch(
            "flows.object_states.item_state.ItemState.can_give",
            autospec=True,
            side_effect=lambda _state, recipient, **_kwargs: recipient is not None,
        ):
            assert self.read(self.kwargs(False), frozenset({"recipient_persona_id"})).available
            assert self.read(self.kwargs()).available
            assert self.post(self.kwargs())["success"]

    def test_ac4_current_mask_hidden_remote_self_and_blocked_candidates(self):
        persona = create_mask(self.receiver_sheet, name="The silver visitor")
        set_active_persona(self.receiver_sheet, persona)
        rows = self.action.recipient_candidates(self.actor, kwargs=self.kwargs(False))
        assert [row["recipient_persona_id"] for row in rows] == [persona.pk]
        assert rows[0]["name"] == persona.display_ic()
        assert self.read(self.kwargs()).reasons == ["That isn't available."]
        selected = {**self.kwargs(False), "recipient_persona_id": persona.pk}
        assert self.read(selected).available
        with patch("actions.definitions.movement.can_perceive", return_value=False):
            assert self.action.recipient_candidates(self.actor, kwargs=self.kwargs(False)) == ()
            assert self.read(selected).reasons == ["That isn't available."]
        self.receiver.location = self.remote
        assert self.action.recipient_candidates(self.actor, kwargs=self.kwargs(False)) == ()
        assert self.read(selected).reasons == ["That isn't available."]
        self.receiver.location = self.room
        self.hot()
        rows = self.action.recipient_candidates(self.actor, kwargs=self.kwargs(False))
        assert len(rows) == 1
        assert not rows[0]["available"]
        assert rows[0]["reasons"] == [RecipientConsentDenied.user_message]

    def test_ac6_hot_consent_absent_existing_whitelist_full_run_parity(self):
        self.hot()
        SocialConsentCategory.objects.filter(key="receiving-stolen-goods").delete()
        assert self.read(self.kwargs(False), frozenset({"recipient_persona_id"})).available
        assert self.read(self.kwargs()).reasons == [RecipientConsentDenied.user_message]
        assert self.post(self.kwargs())["message"] == RecipientConsentDenied.user_message
        assert not SocialConsentCategory.objects.filter(key="receiving-stolen-goods").exists()
        self.unchanged()
        category = receiving_stolen_goods_category()
        assert self.read(self.kwargs()).reasons == [RecipientConsentDenied.user_message]
        add_social_consent_whitelist(
            owner_tenure=self.receiver_tenure, allowed_tenure=self.giver_tenure, category=category
        )
        assert self.read(self.kwargs()).available
        assert self.post(self.kwargs())["success"]

    def test_ac6_all_read_stages_pure_with_absent_hot_category(self):
        self.hot()
        SocialConsentCategory.objects.filter(key="receiving-stolen-goods").delete()
        with (
            patch.object(
                SceneDataManager,
                "initialize_state_for_object",
                side_effect=AssertionError("read initialized state"),
            ),
            patch("flows.emit.emit_event", side_effect=AssertionError("read emitted event")),
            CaptureQueriesContext(connection) as queries,
        ):
            for _ in range(3):
                self.action.is_applicable(self.actor, kwargs=self.kwargs(False))
                self.read(self.kwargs(False), frozenset({"recipient_persona_id"}))
                self.action.recipient_candidates(self.actor, kwargs=self.kwargs(False))
                self.read(self.kwargs())
        for query in queries:
            sql = query["sql"].upper()
            assert not sql.lstrip().startswith(("INSERT", "UPDATE", "DELETE")), sql
            assert "FOR UPDATE" not in sql, sql
        assert not SocialConsentCategory.objects.filter(key="receiving-stolen-goods").exists()
        self.unchanged()

    def test_ac5_stale_selected_face_and_possession_execution_refuse(self):
        selected = self.kwargs()
        assert self.read(selected).available
        persona = create_mask(self.receiver_sheet, name="A new face")
        set_active_persona(self.receiver_sheet, persona)
        assert self.post(selected)["message"] == "That isn't available."
        selected["recipient_persona_id"] = persona.pk
        assert self.read(selected).available
        self.item.game_object.location = self.room
        assert self.post(selected)["message"] == "That isn't available."
        assert not OwnershipEvent.objects.filter(item_instance=self.item).exists()

    def test_ac3_legacy_complete_messages_and_transfer(self):
        assert self.action.run(self.actor).message == "Give what to whom?"
        assert (
            self.action.run(self.actor, target=self.room, recipient=self.receiver).message
            == "That can't be given."
        )
        assert self.action.run(self.actor, target=self.item, recipient=self.receiver).success

    def fresh_item(self, name, location=None, holder=None, pk=None):
        return ItemInstanceFactory(
            template=ItemTemplateFactory(name=name),
            game_object=ObjectDBFactory(
                location=self.actor if location is None else location,
                db_typeclass_path="typeclasses.objects.Object",
            ),
            holder_character_sheet=holder,
            **({"pk": pk} if pk is not None else {}),
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

    def test_ac2_worn_auto_unequip_and_id_decoy(self):
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import TemplateSlotFactory
        from world.items.models import EquippedItem
        from world.items.services.equip import equip_item

        for region in (BodyRegion.TORSO, BodyRegion.HEAD):
            TemplateSlotFactory(
                template=self.item.template, body_region=region, equipment_layer=EquipmentLayer.BASE
            )
        for region in (BodyRegion.TORSO, BodyRegion.HEAD):
            equip_item(
                character_sheet=self.sheet,
                item_instance=self.item,
                body_region=region,
                equipment_layer=EquipmentLayer.BASE,
            )
        decoy = self.fresh_item("ID decoy", pk=self.item.game_object.pk, holder=self.sheet)
        assert EquippedItem.objects.filter(item_instance=self.item).count() == 2
        assert self.post(self.kwargs())["success"]
        assert not EquippedItem.objects.filter(item_instance=self.item).exists()
        assert self.item.game_object.location == self.receiver
        assert decoy.game_object.location == self.actor
        assert decoy.holder_character_sheet == self.sheet
        assert (
            OwnershipEvent.objects.filter(
                item_instance=self.item, event_type=OwnershipEventType.GIVEN
            ).count()
            == 1
        )
        assert not OwnershipEvent.objects.filter(item_instance=decoy).exists()

    def test_ac3_null_and_foreign_holder_possession_not_ownership(self):
        for holder in (None, self.receiver_sheet):
            item = self.fresh_item("Held physically", holder=holder)
            values = {**self.kwargs(), "menu_target": {"kind": "items", "target_id": item.pk}}
            assert self.action.is_applicable(self.actor, kwargs=values)
            assert self.read(values).available
            assert self.post(values)["success"]
            event = OwnershipEvent.objects.get(
                item_instance=item, event_type=OwnershipEventType.GIVEN
            )
            assert event.from_character_sheet == holder
            assert event.to_character_sheet == self.receiver_sheet
        owner_entry = RosterEntryFactory()
        owner_tenure = RosterTenureFactory(
            roster_entry=owner_entry, start_date=timezone.now(), end_date=None
        )
        self.item.holder_character_sheet = owner_entry.character_sheet
        self.item.save(update_fields=["holder_character_sheet"])
        self.hot()
        category = receiving_stolen_goods_category()
        add_social_consent_whitelist(
            owner_tenure=self.receiver_tenure, allowed_tenure=owner_tenure, category=category
        )
        assert self.read(self.kwargs()).available
        assert self.post(self.kwargs())["success"]

    def test_ac4_absent_concealed_remote_and_inactive_face_same_refusal(self):
        from world.conditions.factories import (
            ConditionCategoryFactory,
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )

        absent = self.post({**self.kwargs(), "recipient_persona_id": 999999999})
        assert absent["message"] == "That isn't available."
        hidden = ConditionInstanceFactory(
            target=self.receiver,
            condition=ConditionTemplateFactory(
                category=ConditionCategoryFactory(conceals_from_perception=True)
            ),
        )
        assert self.post(self.kwargs()) == absent
        assert self.action.recipient_candidates(self.actor, kwargs=self.kwargs(False)) == ()
        hidden.delete()
        self.receiver.location = self.remote
        assert self.post(self.kwargs()) == absent
        self.receiver.location = self.room
        selected = self.kwargs()
        persona = create_mask(self.receiver_sheet, name="A public stranger")
        set_active_persona(self.receiver_sheet, persona)
        assert self.post(selected) == absent
        assert (
            self.post({**selected, "recipient_persona_id": self.sheet.primary_persona.pk}) == absent
        )
        rows = self.action.recipient_candidates(self.actor, kwargs=self.kwargs(False))
        assert [row["recipient_persona_id"] for row in rows] == [persona.pk]
        assert rows[0]["name"] == "A public stranger"
        self.unchanged()

    def test_ac5_real_intent_cancel_modify_payload_and_resolving_redirect(self):
        from flows.consts import FlowActionChoices

        replacement = self.fresh_item("Replacement", holder=self.sheet)
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
            try:
                assert self.post(self.kwargs())["success"]
                assert replacement.game_object.location == self.receiver
                self.unchanged()
            finally:
                self.remove_trigger(trigger)
            replacement.game_object.location = self.actor
            replacement.holder_character_sheet = self.sheet
            replacement.save(update_fields=["holder_character_sheet"])
        foreign = self.fresh_item("Foreign", location=self.receiver, holder=self.receiver_sheet)
        remote = self.fresh_item("Remote", location=self.remote)
        for value in (
            self.room.pk,
            foreign.game_object.pk,
            remote.game_object.pk,
            None,
            True,
            "bad",
        ):
            trigger = self.trigger(
                FlowActionChoices.MODIFY_PAYLOAD, {"field": "target", "op": "set", "value": value}
            )
            try:
                assert self.post(self.kwargs())["message"] == "That isn't available."
                self.unchanged()
            finally:
                self.remove_trigger(trigger)
        trigger = self.trigger(FlowActionChoices.CANCEL_EVENT)
        try:
            assert self.post(self.kwargs())["message"] == "Something prevents you."
            self.unchanged()
        finally:
            self.remove_trigger(trigger)

    def test_ac5_contained_intent_redirect_retains_assertions(self):
        from flows.consts import FlowActionChoices

        replacement = self.fresh_item("Replacement", holder=self.sheet)
        bag = self.fresh_item("Bag", holder=self.sheet)
        bag.template.is_container = True
        bag.template.supports_open_close = True
        bag.template.save()
        bag.is_open = True
        bag.save(update_fields=["is_open"])
        for item in (self.item, replacement):
            item.contained_in = bag
            item.save(update_fields=["contained_in"])
            item.game_object.location = bag.game_object
        outside = self.fresh_item("Outside", holder=self.sheet)
        selected = self.kwargs()
        selected["menu_target"]["container_item_id"] = bag.pk
        for destination, success in ((outside, False), (replacement, True)):
            trigger = self.trigger(
                FlowActionChoices.MODIFY_PAYLOAD,
                {"field": "target", "op": "set", "value": destination.game_object.pk},
            )
            try:
                result = self.post(selected)
                assert result["success"] is success
                assert self.item.game_object.location == bag.game_object
                assert self.item.contained_in == bag
                if success:
                    assert replacement.game_object.location == self.receiver
                    assert replacement.contained_in == bag  # Current Give does not clear it.
                else:
                    assert result["message"] == "That isn't available."
                    assert outside.game_object.location == self.actor
            finally:
                self.remove_trigger(trigger)

    def transfer_snapshot(self, item):
        from world.items.models import EquippedItem

        return (
            item.game_object.db_location_id,
            item.holder_character_sheet_id,
            item.contained_in_id,
            tuple(
                (row.pk, row.character_id, row.body_region, row.equipment_layer)
                for row in EquippedItem.objects.filter(item_instance=item).order_by("pk")
            ),
            tuple(
                (
                    row.pk,
                    row.event_type,
                    row.from_character_sheet_id,
                    row.to_character_sheet_id,
                    row.from_persona_display_id,
                    row.to_persona_display_id,
                )
                for row in OwnershipEvent.objects.filter(item_instance=item).order_by("pk")
            ),
        )

    def test_ac5_authored_recipient_redirect_accepts_current_alternate(self):
        from flows.consts import FlowActionChoices

        alternate_entry = RosterEntryFactory()
        alternate_sheet = alternate_entry.character_sheet
        alternate = alternate_sheet.character
        alternate.location = self.room
        RosterTenureFactory(roster_entry=alternate_entry, start_date=timezone.now(), end_date=None)
        public = create_mask(alternate_sheet, name="Another public visitor")
        set_active_persona(alternate_sheet, public)
        assert public != self.receiver_sheet.primary_persona
        assert self.read(self.kwargs()).available
        trigger = self.trigger(
            FlowActionChoices.MODIFY_PAYLOAD,
            {"field": "recipient_persona_id", "op": "set", "value": public.pk},
        )
        try:
            assert self.post(self.kwargs())["success"]
        finally:
            self.remove_trigger(trigger)
        assert self.item.game_object.location == alternate
        assert self.item.holder_character_sheet == alternate_sheet
        event = OwnershipEvent.objects.get(
            item_instance=self.item, event_type=OwnershipEventType.GIVEN
        )
        assert event.from_character_sheet == self.sheet
        assert event.to_character_sheet == alternate_sheet
        assert event.to_persona_display == alternate_sheet.primary_persona
        assert self.receiver != self.item.game_object.location

    def test_ac5_authored_recipient_redirect_invalid_faces_neutral_no_transfer(self):
        from flows.consts import FlowActionChoices
        from world.conditions.factories import (
            ConditionCategoryFactory,
            ConditionInstanceFactory,
            ConditionTemplateFactory,
        )

        alternate_entry = RosterEntryFactory()
        alternate_sheet = alternate_entry.character_sheet
        alternate = alternate_sheet.character
        alternate.location = self.room
        RosterTenureFactory(roster_entry=alternate_entry, start_date=timezone.now(), end_date=None)
        previous = create_mask(alternate_sheet, name="Previous face")
        public = create_mask(alternate_sheet, name="Current face")
        set_active_persona(alternate_sheet, previous)
        set_active_persona(alternate_sheet, public)
        inactive = create_mask(alternate_sheet, name="Inactive face")
        set_active_persona(alternate_sheet, public)
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import TemplateSlotFactory
        from world.items.services.equip import equip_item

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
        self.hot()
        category = receiving_stolen_goods_category()
        add_social_consent_whitelist(
            owner_tenure=self.receiver_tenure, allowed_tenure=self.giver_tenure, category=category
        )
        assert self.read(self.kwargs()).available
        item_before = self.transfer_snapshot(self.item)
        assert len(item_before[3]) == 1
        assert len(item_before[4]) == 1
        category_before = tuple(
            (row.pk, row.key) for row in SocialConsentCategory.objects.order_by("pk")
        )
        for case, value in (
            ("invalid_null", None),
            ("invalid_bool", True),
            ("invalid_string", str(public.pk)),
            ("invalid_zero", 0),
            ("absent", 999999999),
            ("stale", previous.pk),
            ("inactive", inactive.pk),
            ("covered_primary", alternate_sheet.primary_persona.pk),
            ("remote", public.pk),
            ("concealed", public.pk),
        ):
            with self.subTest(case=case):
                hidden = None
                if case == "remote":
                    alternate.location = self.remote
                elif case == "concealed":
                    hidden = ConditionInstanceFactory(
                        target=alternate,
                        condition=ConditionTemplateFactory(
                            category=ConditionCategoryFactory(conceals_from_perception=True)
                        ),
                    )
                trigger = self.trigger(
                    FlowActionChoices.MODIFY_PAYLOAD,
                    {"field": "recipient_persona_id", "op": "set", "value": value},
                )
                try:
                    result = self.post(self.kwargs())
                    assert not result["success"]
                    assert result["message"] == "That isn't available."
                    assert self.transfer_snapshot(self.item) == item_before
                    assert (
                        tuple(
                            (row.pk, row.key)
                            for row in SocialConsentCategory.objects.order_by("pk")
                        )
                        == category_before
                    )
                finally:
                    self.remove_trigger(trigger)
                    alternate.location = self.room
                    if hidden is not None:
                        hidden.delete()
        self.unchanged()

    def test_ac5_changes_between_gate_and_execute(self):
        original = GiveAction.execute
        for change in ("location", "face", "visibility", "possession", "consent"):
            self.receiver.location = self.room
            self.item.game_object.location = self.actor
            set_active_persona(self.receiver_sheet, self.receiver_sheet.primary_persona)
            allowed = None
            if change == "consent":
                self.hot()
                category = receiving_stolen_goods_category()
                allowed = add_social_consent_whitelist(
                    owner_tenure=self.receiver_tenure,
                    allowed_tenure=self.giver_tenure,
                    category=category,
                )
            assert self.read(self.kwargs()).available

            def execute(action, actor, context=None, *, change=change, allowed=allowed, **kwargs):
                if change == "location":
                    self.receiver.location = self.remote
                elif change == "face":
                    set_active_persona(
                        self.receiver_sheet, create_mask(self.receiver_sheet, name="Changed face")
                    )
                elif change == "possession":
                    self.item.game_object.location = self.room
                elif change == "consent":
                    allowed.delete()
                if change == "visibility":
                    with patch("actions.definitions.movement.can_perceive", return_value=False):
                        return original(action, actor, context=context, **kwargs)
                return original(action, actor, context=context, **kwargs)

            with patch.object(GiveAction, "execute", execute):
                result = self.post(self.kwargs())
            assert not result["success"]
            assert result["message"] == (
                RecipientConsentDenied.user_message
                if change == "consent"
                else "That isn't available."
            )
            assert self.item.holder_character_sheet == self.sheet
            assert not OwnershipEvent.objects.filter(
                item_instance=self.item, event_type=OwnershipEventType.GIVEN
            ).exists()

    def test_ac6_nonhot_and_receiver_without_active_tenure_no_category_write(self):
        SocialConsentCategory.objects.filter(key="receiving-stolen-goods").delete()
        assert self.read(self.kwargs()).available
        assert self.post(self.kwargs())["success"]
        assert not SocialConsentCategory.objects.filter(key="receiving-stolen-goods").exists()
        self.item.game_object.location = self.actor
        self.item.holder_character_sheet = self.sheet
        self.item.save(update_fields=["holder_character_sheet"])
        self.hot()
        self.receiver_tenure.end_date = timezone.now()
        self.receiver_tenure.save(update_fields=["end_date"])
        from world.roster.models import RosterTenure

        assert not RosterTenure.objects.filter(
            roster_entry__character_sheet=self.receiver_sheet, end_date__isnull=True
        ).exists()
        # The receiver-without-active-tenure fixture exercises the documented bypass.
        assert self.read(self.kwargs()).available
        assert self.post(self.kwargs())["success"]
        assert not SocialConsentCategory.objects.filter(key="receiving-stolen-goods").exists()

    def test_ac1_default_actions_undeclared_inputs_and_bound_gate_order(self):
        from actions.definitions.items import StealAction, TakeOutAction
        from actions.definitions.movement import DropAction, GetAction

        for action in (GetAction(), DropAction(), TakeOutAction(), StealAction()):
            before = action.check_availability(self.actor, context={"kwargs": self.kwargs()})
            after = action.check_availability(
                self.actor, context={"kwargs": self.kwargs()}, pending_inputs=frozenset()
            )
            assert before == after
            with self.assertRaises(ValueError):
                action.check_availability(
                    self.actor, pending_inputs=frozenset({"recipient_persona_id"})
                )
        with patch.object(
            ProbeAction,
            "get_prerequisites",
            return_value=[RecipientProbe(reason="recipient"), Probe(reason="later bound")],
        ):
            probe = ProbeAction("give", "Give", "gift", "items", TargetType.SINGLE)
            assert probe.check_availability(
                self.actor, pending_inputs=frozenset({"recipient_persona_id"})
            ).reasons == ["later bound"]
        original = GiveAction.check_availability
        received = []

        def checked(action, actor, target=None, context=None, *, pending_inputs=frozenset()):
            received.append(pending_inputs)
            return original(action, actor, target, context, pending_inputs=pending_inputs)

        with patch.object(GiveAction, "check_availability", checked):
            result = self.post({**self.kwargs(False), "pending_inputs": ["recipient_persona_id"]})
        assert not result["success"]
        assert received == [frozenset()]
        self.unchanged()
