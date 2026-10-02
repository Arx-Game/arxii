"""Typed TakeOut/Steal REST journeys and shared nonmutating checks."""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from actions.definitions.item_helpers import resolve_typed_item
from actions.definitions.items import StealAction, TakeOutAction
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
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.consent.constants import ConsentMode
from world.consent.models import SocialConsentCategory
from world.consent.services import (
    add_social_consent_whitelist,
    set_social_consent_category_rule,
    set_social_consent_preference,
    theft_category,
)
from world.items.constants import (
    BodyRegion,
    ContainerAccessPolicy,
    EquipmentLayer,
    OwnershipEventType,
)
from world.items.exceptions import (
    ContainerAccessDenied,
    NotInContainer,
    NotReachable,
    OwnedByAnother,
    TheftNotPermitted,
    VaultAccessDenied,
)
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, TemplateSlotFactory
from world.items.models import EquippedItem, OwnershipEvent
from world.items.services.equip import equip_item
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.room_features.models import VaultDetails
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.services import create_mask, set_active_persona
from world.societies.models import LegendEntry


class TypedTakeOutStealTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.entry = RosterEntryFactory()
        self.sheet = self.entry.character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        self.other_entry = RosterEntryFactory()
        self.other = self.other_entry.character_sheet
        self.other.character.location = self.room
        self.account = AccountFactory(is_staff=False)
        self.tenure = RosterTenureFactory(
            roster_entry=self.entry,
            player_data=PlayerDataFactory(account=self.account),
            start_date=timezone.now(),
            end_date=None,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)
        self.chest = self._item("Chest", holder=self.other)
        self.chest.template.is_container = True
        self.chest.template.supports_open_close = True
        self.chest.template.save(update_fields=["is_container", "supports_open_close"])
        self.chest.is_open = True
        self.chest.access_policy = ContainerAccessPolicy.OPEN
        self.chest.save(update_fields=["is_open", "access_policy"])
        self.item = self._item("Exact child", holder=self.other, pk=940001)
        self._contain(self.item)

    def _item(self, name, holder=None, pk=None, location=None, physical=True):
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

    def _contain(self, item, chest=None):
        chest = self.chest if chest is None else chest
        item.contained_in = chest
        item.save(update_fields=["contained_in"])
        item.game_object.location = chest.game_object

    def _wire(self, item=None, kind="items", contained=True, **assertions):
        item = self.item if item is None else item
        wire = {"kind": kind, "target_id": item.pk if kind == "items" else item.game_object.pk}
        if contained:
            wire["container_item_id"] = self.chest.pk
        return {**wire, **assertions}

    def _post(self, key, wire, **extra):
        response = self.client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {
                "ref": {"backend": "registry", "registry_key": key},
                "kwargs": {"menu_target": wire, **extra},
            },
            format="json",
        )
        assert response.status_code == 200, response.data
        return response.data

    def _read(self, action, kwargs):
        return action.check_availability(self.actor, context={"kwargs": kwargs})

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

    def _parity(self, action, wire, error):
        kwargs = {"menu_target": wire}
        assert action.is_applicable(self.actor, kwargs=kwargs)
        checked = self._read(action, kwargs)
        assert checked.reasons == [error.user_message], checked
        result = self._post(action.key, wire)
        assert not result["success"]
        assert result["message"] == "; ".join(checked.reasons)

    def _owner_tenure(self):
        return RosterTenureFactory(roster_entry=self.other_entry, end_date=None)

    def _allow(self, owner):
        category = theft_category()
        pref = set_social_consent_preference(owner, allow_social_actions=True)
        set_social_consent_category_rule(pref, category, ConsentMode.ALLOWLIST)
        add_social_consent_whitelist(owner, self.tenure, category)

    def _trigger(self, action, parameters=None, variable_name=""):
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=action,
            parameters=parameters or {},
            variable_name=variable_name,
        )
        trigger = TriggerFactory(
            trigger_definition=TriggerDefinitionFactory(
                event_name=EventName.ACTION_INTENT, flow_definition=flow
            ),
            obj=self.room,
        )
        self.room.trigger_handler.refresh()
        return trigger

    def _remove(self, trigger):
        trigger.delete()
        self.room.trigger_handler.refresh()

    def _vault(self):
        feature = RoomFeatureInstanceFactory(
            room_profile=self.room.room_profile,
            feature_kind=RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.VAULT),
            level=1,
        )
        return VaultDetails.objects.create(
            feature_instance=feature, founder_persona=self.other.primary_persona, max_items=20
        )

    def test_ac1_takeout_exact_child_preserves_holder_and_null(self):
        assert self.item.pk != self.item.game_object.pk
        decoy = self._item("Domain decoy", pk=self.item.game_object.pk)
        for holder in (self.other, None):
            self.item.holder_character_sheet = holder
            self.item.save(update_fields=["holder_character_sheet"])
            self._contain(self.item)
            assert self._read(TakeOutAction(), {"menu_target": self._wire()}).available
            assert self._post("take_out", self._wire())["success"]
            assert self.item.contained_in is None
            assert self.item.game_object.location == self.actor
            assert self.item.holder_character_sheet == holder
            assert self.item.__class__.objects.filter(
                pk=self.item.pk, contained_in__isnull=True, game_object__db_location=self.actor
            ).exists()
        assert decoy.game_object.location == self.room
        assert not OwnershipEvent.objects.filter(item_instance=self.item).exists()

    def test_ac1_steal_real_consequences_items_and_objects(self):
        for kind in ("items", "objects"):
            item = self._item("Foreign room item", holder=self.other)
            assert item.pk != item.game_object.pk
            decoy = self._item("Other domain", pk=item.game_object.pk)
            wire = self._wire(item, kind=kind, contained=False)
            assert self._post("steal", wire)["success"]
            assert item.game_object.location == self.actor
            assert item.holder_character_sheet == self.sheet
            event = OwnershipEvent.objects.get(item_instance=item)
            assert event.event_type == OwnershipEventType.STOLEN
            assert event.from_character_sheet == self.other
            assert event.to_character_sheet == self.sheet
            assert decoy.game_object.location == self.room
        deeds = LegendEntry.objects.filter(persona=self.sheet.primary_persona)
        assert deeds.count() == 2
        assert all(deed.crime_tags.exists() for deed in deeds)

    def test_ac2_fit_and_shared_containment_validation(self):
        action = TakeOutAction()
        assert action.is_applicable(self.actor, kwargs={"menu_target": self._wire()})
        for holder in (None, self.sheet):
            item = self._item("Not theft", holder=holder)
            wire = self._wire(item, contained=False)
            assert not StealAction().is_applicable(self.actor, kwargs={"menu_target": wire})
            self._deny("steal", wire)
            self._deny("take_out", wire)
        carried = self._item("Borrowed carried", holder=self.other, location=self.actor)
        self._deny("steal", self._wire(carried, contained=False))
        loose = self._item("Loose foreign", holder=self.other)
        kwargs = {"target": loose}
        assert self._read(action, kwargs).reasons == [NotInContainer.user_message]
        assert action.run(self.actor, **kwargs).message == NotInContainer.user_message
        from flows.service_functions.inventory import validate_take_out

        sdm = SceneDataManager()
        with self.assertRaises(NotInContainer):
            validate_take_out(
                CharacterState(self.actor, context=sdm), ItemState(loose, context=sdm)
            )

    def test_ac2_foreign_visible_worn_is_not_take_authority(self):
        wearer = self.other.character
        persona = create_mask(self.other, name="A Grey Hood")
        set_active_persona(self.other, persona)
        coat = self._item("Visible coat", holder=self.other, location=wearer)
        TemplateSlotFactory(
            template=coat.template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        equip_item(
            character_sheet=self.other,
            item_instance=coat,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        wire = self._wire(coat, contained=False, owner_persona_id=persona.pk)
        assert resolve_typed_item(self.actor, {"menu_target": wire}) is not None
        self._parity(StealAction(), wire, NotReachable)
        self._deny("take_out", wire)
        assert EquippedItem.objects.filter(item_instance=coat).exists()
        assert coat.game_object.location == wearer
        hidden = ConditionInstanceFactory(
            target=wearer,
            condition=ConditionTemplateFactory(
                category=ConditionCategoryFactory(conceals_from_perception=True)
            ),
        )
        self._deny("steal", wire)
        hidden.delete()
        private = self._item("Private carried", holder=self.other, location=wearer)
        self._deny("steal", self._wire(private, contained=False))

    def test_ac3_policy_denial_bypass_and_third_party_stash(self):
        self.chest.access_policy = ContainerAccessPolicy.OWNER_ONLY
        self.chest.save(update_fields=["access_policy"])
        self._parity(TakeOutAction(), self._wire(), ContainerAccessDenied)
        assert self._post("steal", self._wire())["success"]
        assert self.item.contained_in is None
        assert OwnershipEvent.objects.filter(item_instance=self.item, event_type="stolen").exists()
        self.chest.access_policy = ContainerAccessPolicy.OPEN
        self.chest.save(update_fields=["access_policy"])
        third = RosterEntryFactory().character_sheet
        self.item.holder_character_sheet = third
        self.item.save(update_fields=["holder_character_sheet"])
        self._contain(self.item)
        self._parity(TakeOutAction(), self._wire(), OwnedByAnother)

    def test_ac3_real_consent_refusal_then_allowlist_success(self):
        owner = self._owner_tenure()
        self.chest.access_policy = ContainerAccessPolicy.OWNER_ONLY
        self.chest.save(update_fields=["access_policy"])
        self._parity(StealAction(), self._wire(), TheftNotPermitted)
        assert not OwnershipEvent.objects.filter(item_instance=self.item).exists()
        self._allow(owner)
        assert self._read(StealAction(), {"menu_target": self._wire()}).available
        assert self._post("steal", self._wire())["success"]

    def test_ac3_ac7_ancestor_consent_read_and_rest_parity(self):
        owner = self._owner_tenure()
        set_social_consent_preference(owner, allow_social_actions=True)
        self.chest.access_policy = ContainerAccessPolicy.OWNER_ONLY
        self.chest.save(update_fields=["access_policy"])
        SocialConsentCategory.objects.filter(key="theft").delete()
        parent = None
        for phase in ("absent", "ancestor_default_deny", "ancestor_rule_deny", "ancestor_allowed"):
            if phase == "ancestor_default_deny":
                parent = SocialConsentCategory.objects.create(
                    key="task10-antagonism", name="Antagonism", default_mode=ConsentMode.ALLOWLIST
                )
                SocialConsentCategory.objects.create(
                    key="theft", name="Theft", parent=parent, default_mode=ConsentMode.EVERYONE
                )
            elif phase == "ancestor_rule_deny":
                parent.default_mode = ConsentMode.EVERYONE
                parent.save(update_fields=["default_mode"])
                pref = set_social_consent_preference(owner, allow_social_actions=True)
                set_social_consent_category_rule(pref, parent, ConsentMode.ALLOWLIST)
            elif phase == "ancestor_allowed":
                add_social_consent_whitelist(owner, self.tenure, parent)
            allowed = phase == "ancestor_allowed"
            wire = self._wire()
            before = (
                SocialConsentCategory.objects.count(),
                OwnershipEvent.objects.count(),
                LegendEntry.objects.count(),
                self.item.contained_in,
                self.item.game_object.location,
                self.item.holder_character_sheet,
            )
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
                    action = StealAction()
                    assert action.is_applicable(self.actor, kwargs={"menu_target": wire})
                    for kwargs in ({"menu_target": wire}, {"target": self.item.game_object}):
                        checked = self._read(action, kwargs)
                        assert checked.available == allowed, checked
                        assert checked.reasons == (
                            [] if allowed else [TheftNotPermitted.user_message]
                        ), checked
            sql = [q["sql"].upper() for q in queries.captured_queries]
            assert not [
                q
                for q in sql
                if q.lstrip().startswith(("INSERT", "UPDATE", "DELETE")) or "FOR UPDATE" in q
            ]
            assert any("SOCIALCONSENTCATEGORY" in q for q in sql), sql
            if phase != "absent":
                assert any("SOCIALCONSENTCATEGORYRULE" in q for q in sql), sql
                assert any("SOCIALCONSENTWHITELIST" in q for q in sql), sql
            assert before == (
                SocialConsentCategory.objects.count(),
                OwnershipEvent.objects.count(),
                LegendEntry.objects.count(),
                self.item.contained_in,
                self.item.game_object.location,
                self.item.holder_character_sheet,
            )
            if phase == "absent":
                assert not SocialConsentCategory.objects.filter(key="theft").exists()
            result = self._post("steal", wire)
            assert result["success"] == allowed, result
            if not allowed:
                assert result["message"] == TheftNotPermitted.user_message
                assert before == (
                    SocialConsentCategory.objects.count(),
                    OwnershipEvent.objects.count(),
                    LegendEntry.objects.count(),
                    self.item.contained_in,
                    self.item.game_object.location,
                    self.item.holder_character_sheet,
                )
            else:
                assert self.item.contained_in is None
                assert self.item.game_object.location == self.actor
                assert self.item.holder_character_sheet == self.sheet
                assert (
                    OwnershipEvent.objects.filter(
                        item_instance=self.item, event_type=OwnershipEventType.STOLEN
                    ).count()
                    == 1
                )
                deed = LegendEntry.objects.get(persona=self.sheet.primary_persona)
                assert deed.crime_tags.exists()

    def test_ac3_real_vault_access_and_founder_consent(self):
        from flows.service_functions.inventory import validate_pick_up, validate_steal

        owner = self._owner_tenure()
        self.chest.holder_character_sheet = None
        self.chest.save(update_fields=["holder_character_sheet"])
        self.item.holder_character_sheet = None
        self.item.save(update_fields=["holder_character_sheet"])
        vault = self._vault()
        # Vault denial uses physical location, not the root container's room.
        loose = self._item("Vault room item")
        wire = self._wire(loose, contained=False)
        self._parity(StealAction(), wire, TheftNotPermitted)
        sdm = SceneDataManager()
        character = CharacterState(self.actor, context=sdm)
        state = ItemState(loose, context=sdm)
        with self.assertRaises(VaultAccessDenied):
            validate_pick_up(character, state)
        with self.assertRaises(TheftNotPermitted):
            validate_steal(character, state)
        self._allow(owner)
        validate_steal(character, state)
        assert self._post("steal", wire)["success"]
        assert loose.holder_character_sheet == self.sheet
        vault.founder_persona = self.sheet.primary_persona
        vault.save(update_fields=["founder_persona"])
        self._contain(self.item)
        assert self._post("take_out", self._wire())["success"]
        assert self.item.holder_character_sheet is None

    def test_ac3_fixed_and_package_refusals_are_shared(self):
        loose = self._item("Fixed room item")
        wire = self._wire(loose, contained=False)
        with patch(
            "flows.service_functions.inventory._placed_as_active_decoration", return_value=True
        ):
            self._parity(StealAction(), wire, TheftNotPermitted)
        with (
            patch.object(ItemState, "can_take", return_value=False),
            patch("world.npc_services.servant_fetch.can_servant_fetch", return_value=False),
        ):
            self._parity(TakeOutAction(), self._wire(), NotReachable)
            self.chest.access_policy = ContainerAccessPolicy.OWNER_ONLY
            self.chest.save(update_fields=["access_policy"])
            self._parity(StealAction(), self._wire(), NotReachable)

    def test_ac4_malformed_domains_and_competing_fields(self):
        for key in ("take_out", "steal"):
            for wire in (
                None,
                [],
                {},
                {"kind": "places", "target_id": 1},
                {**self._wire(), "label": "untrusted"},
                {**self._wire(), "owner_persona_id": 1},
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
        self._deny("take_out", self._wire(self.chest, kind="objects", contained=False))
        plain = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object", location=self.room)
        self._deny("steal", {"kind": "objects", "target_id": plain.pk})
        row = self._item("Row only", holder=self.sheet, physical=False)
        for key in ("take_out", "steal"):
            self._deny(key, self._wire(row, contained=False))

    def test_ac4_current_container_and_concealment_rechecked(self):
        self.chest.access_policy = ContainerAccessPolicy.OWNER_ONLY
        self.chest.save(update_fields=["access_policy"])
        wire = self._wire()
        for key in ("take_out", "steal"):
            absent = self._deny(key, {"kind": "items", "target_id": 999999999})
            self.chest.is_open = False
            self.chest.save(update_fields=["is_open"])
            assert self._deny(key, wire) == absent
            self.chest.is_open = True
            self.chest.save(update_fields=["is_open"])
            self.chest.game_object.location = self.remote
            assert self._deny(key, wire) == absent
            self.chest.game_object.location = self.room
            hidden = ConditionInstanceFactory(
                target=self.item.game_object,
                condition=ConditionTemplateFactory(
                    category=ConditionCategoryFactory(conceals_from_perception=True)
                ),
            )
            assert self._deny(key, wire) == absent
            hidden.delete()
            self.item.contained_in = None
            self.item.save(update_fields=["contained_in"])
            assert self._deny(key, wire) == absent
            self._contain(self.item)
        assert self.item.holder_character_sheet == self.other
        assert not OwnershipEvent.objects.filter(item_instance=self.item).exists()

    def test_ac4_stale_worn_owner_context_rest_is_neutral(self):
        wearer = self.other.character
        persona = create_mask(self.other, name="A Grey Hood")
        replacement = create_mask(self.other, name="A New Hood")
        third = RosterEntryFactory().character_sheet
        third.character.location = self.room
        absent = self._deny("steal", {"kind": "items", "target_id": 999999999})
        for change in ("active_persona", "wearer_location", "holder", "equipment", "new_wearer"):
            with self.subTest(change=change):
                wearer.location = self.room
                set_active_persona(self.other, persona)
                coat = self._item("Visible coat", holder=self.other, location=wearer)
                TemplateSlotFactory(
                    template=coat.template,
                    body_region=BodyRegion.TORSO,
                    equipment_layer=EquipmentLayer.BASE,
                )
                equip_item(
                    character_sheet=self.other,
                    item_instance=coat,
                    body_region=BodyRegion.TORSO,
                    equipment_layer=EquipmentLayer.BASE,
                )
                wire = self._wire(coat, contained=False, owner_persona_id=persona.pk)
                kwargs = {"menu_target": wire}
                assert resolve_typed_item(self.actor, kwargs) is not None
                assert StealAction().is_applicable(self.actor, kwargs=kwargs)
                checked = self._read(StealAction(), kwargs)
                assert not checked.available
                assert checked.reasons == [NotReachable.user_message]
                if change == "active_persona":
                    set_active_persona(self.other, replacement)
                elif change == "wearer_location":
                    wearer.location = self.remote
                elif change == "holder":
                    coat.holder_character_sheet = third
                    coat.save(update_fields=["holder_character_sheet"])
                elif change == "equipment":
                    EquippedItem.objects.filter(item_instance=coat).delete()
                else:
                    EquippedItem.objects.filter(item_instance=coat).delete()
                    coat.holder_character_sheet = third
                    coat.save(update_fields=["holder_character_sheet"])
                    coat.game_object.location = third.character
                    equip_item(
                        character_sheet=third,
                        item_instance=coat,
                        body_region=BodyRegion.TORSO,
                        equipment_layer=EquipmentLayer.BASE,
                    )

                def snapshot(coat=coat):
                    return (
                        coat.game_object.location,
                        coat.holder_character_sheet,
                        coat.contained_in,
                        wearer.location,
                        list(
                            EquippedItem.objects.filter(item_instance=coat)
                            .order_by("pk")
                            .values_list("pk", "character_id", "body_region", "equipment_layer")
                        ),
                        OwnershipEvent.objects.count(),
                        LegendEntry.objects.count(),
                    )

                before = snapshot()
                assert self._deny("steal", wire) == absent
                assert snapshot() == before
                assert coat.__class__.objects.filter(
                    pk=coat.pk,
                    holder_character_sheet=coat.holder_character_sheet,
                    game_object__db_location=coat.game_object.location,
                    contained_in__isnull=True,
                ).exists()
                assert not OwnershipEvent.objects.filter(item_instance=coat).exists()
                EquippedItem.objects.filter(item_instance=coat).delete()
        wearer.location = self.room
        set_active_persona(self.other, persona)

    def test_ac5_real_intent_container_redirects_both_adapters_and_cancel(self):
        for key in ("take_out", "steal"):
            self.chest.access_policy = (
                ContainerAccessPolicy.OPEN
                if key == "take_out"
                else ContainerAccessPolicy.OWNER_ONLY
            )
            self.chest.save(update_fields=["access_policy"])
            for service in (False, True):
                sibling = self._item("Sibling", holder=self.other)
                self._contain(sibling)
                trigger = self._trigger(
                    FlowActionChoices.CALL_SERVICE_FUNCTION
                    if service
                    else FlowActionChoices.MODIFY_PAYLOAD,
                    {"payload": "@payload", "object_id": sibling.game_object.pk}
                    if service
                    else {"field": "target", "op": "set", "value": sibling.game_object.pk},
                    "flows.service_functions.actions.redirect_action_target" if service else "",
                )
                try:
                    assert self._post(key, self._wire())["success"]
                    assert sibling.game_object.location == self.actor
                    assert self.item.contained_in == self.chest
                finally:
                    self._remove(trigger)
            outside = self._item("Outside", holder=self.other)
            for value in (outside.game_object.pk, self.remote.pk, "bad", None, True):
                trigger = self._trigger(
                    FlowActionChoices.MODIFY_PAYLOAD,
                    {"field": "target", "op": "set", "value": value},
                )
                try:
                    self._deny(key, self._wire())
                finally:
                    self._remove(trigger)
            trigger = self._trigger(FlowActionChoices.CANCEL_EVENT)
            try:
                result = self._post(key, self._wire())
                assert not result["success"]
                assert result["message"] == "Something prevents you."
                assert self.item.contained_in == self.chest
            finally:
                self._remove(trigger)

    def test_ac5_objects_redirect_preserves_object_domain(self):
        source = self._item("Source", holder=self.other)
        destination = self._item("Destination", holder=self.other)
        trigger = self._trigger(
            FlowActionChoices.MODIFY_PAYLOAD,
            {"field": "target", "op": "set", "value": destination.game_object.pk},
        )
        try:
            assert self._post("steal", self._wire(source, kind="objects", contained=False))[
                "success"
            ]
            assert source.game_object.location == self.room
            assert destination.game_object.location == self.actor
        finally:
            self._remove(trigger)

    def test_ac5_execute_rechecks_after_availability(self):
        action = TakeOutAction()
        wire = self._wire()
        original = action.check_availability

        def close_after_read(*args, **kwargs):
            result = original(*args, **kwargs)
            assert result.available
            self.chest.is_open = False
            self.chest.save(update_fields=["is_open"])
            return result

        with patch.object(action, "check_availability", side_effect=close_after_read):
            result = action.run(self.actor, menu_target=wire)
        assert not result.success
        assert result.message == "That isn't available."
        assert self.item.contained_in == self.chest

    def test_ac6_legacy_resolved_and_servant_fallback(self):
        for action, missing, invalid in (
            (TakeOutAction(), "Take what out?", "That can't be taken out."),
            (StealAction(), "Steal what?", "That can't be stolen."),
        ):
            assert action.run(self.actor).message == missing
            assert action.run(self.actor, target=self.room).message == invalid
        self.chest.game_object.location = self.remote
        kwargs = {"target": self.item}
        with (
            patch("world.npc_services.servant_fetch.can_servant_fetch", return_value=True),
            patch("world.npc_services.servant_fetch.servant_fetch_item") as queue,
        ):
            assert self._read(TakeOutAction(), kwargs).available
            queue.assert_not_called()
            result = TakeOutAction().run(self.actor, **kwargs)
            assert result.success
            assert result.message == "A servant bows and departs to fetch that."
            queue.assert_called_once_with(actor=self.actor, item_instance=self.item)
            self._deny("take_out", self._wire())
            assert queue.call_count == 1
        with patch("world.npc_services.servant_fetch.can_servant_fetch", return_value=False):
            assert self._read(TakeOutAction(), kwargs).reasons == [NotReachable.user_message]
            assert TakeOutAction().run(self.actor, **kwargs).message == NotReachable.user_message

    def test_ac7_absent_category_and_real_consent_reads_never_write(self):
        owner = self._owner_tenure()
        self.chest.access_policy = ContainerAccessPolicy.OWNER_ONLY
        self.chest.save(update_fields=["access_policy"])
        SocialConsentCategory.objects.filter(key="theft").delete()
        for phase in ("absent", "denied", "allowed"):
            if phase == "denied":
                theft_category()
            if phase == "allowed":
                self._allow(owner)
            before = (
                OwnershipEvent.objects.count(),
                LegendEntry.objects.count(),
                ObjectDBFactory._meta.model.objects.count(),
                self.item.contained_in,
                self.item.game_object.location,
                self.item.holder_character_sheet,
            )
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
                    for action in (TakeOutAction(), StealAction()):
                        action.is_applicable(self.actor, kwargs={"menu_target": self._wire()})
                        self._read(action, {"menu_target": self._wire()})
                        self._read(action, {"target": self.item.game_object})
            assert not [
                q["sql"]
                for q in queries.captured_queries
                if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
                or "FOR UPDATE" in q["sql"].upper()
            ]
            assert before == (
                OwnershipEvent.objects.count(),
                LegendEntry.objects.count(),
                ObjectDBFactory._meta.model.objects.count(),
                self.item.contained_in,
                self.item.game_object.location,
                self.item.holder_character_sheet,
            )
            if phase == "absent":
                assert not SocialConsentCategory.objects.filter(key="theft").exists()
