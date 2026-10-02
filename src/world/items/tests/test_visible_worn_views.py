"""Tests for VisibleWornItemViewSet and VisibleItemDetailViewSet endpoints."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.factories import (
    FlowDefinitionFactory,
    FlowStepDefinitionFactory,
    TriggerDefinitionFactory,
    TriggerFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
)
from world.conditions.services import register_detection
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.items.services.equip import unequip_item
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.services import create_mask, set_active_persona


class _VisibleWornSetupMixin:
    """Shared setUp for the visible-worn endpoint tests.

    Builds two rooms; in room A, account A plays character A and account B
    plays character B; in room C, account C plays character C. Character A
    wears two items: a shirt at TORSO/BASE (covered) and a coat at
    TORSO/OVER (plain cut — conceals by default, #2985). The shirt is concealed to
    same-room observers; the coat is visible.
    """

    def setUp(self) -> None:
        # Two rooms.
        self.room = ObjectDBFactory(
            db_key="VWVRoomA",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.other_room = ObjectDBFactory(
            db_key="VWVRoomB",
            db_typeclass_path="typeclasses.rooms.Room",
        )

        # Account A → character A (in room A) — the "target" being looked at.
        self.account_a = AccountFactory(username="vwv_account_a")
        self.character_a = CharacterFactory(db_key="VWVCharA", location=self.room)
        self.character_a.db_account = self.account_a
        self.character_a.save()
        self.sheet_a = CharacterSheetFactory(character=self.character_a)
        self.entry_a = RosterEntryFactory(character_sheet=self.sheet_a)
        self.player_data_a = PlayerDataFactory(account=self.account_a)
        self.tenure_a = RosterTenureFactory(
            roster_entry=self.entry_a,
            player_data=self.player_data_a,
            end_date=None,
        )

        # Account B → character B (in room A, same room as A) — the "near observer".
        self.account_b = AccountFactory(username="vwv_account_b")
        self.character_b = CharacterFactory(db_key="VWVCharB", location=self.room)
        self.character_b.db_account = self.account_b
        self.character_b.save()
        self.sheet_b = CharacterSheetFactory(character=self.character_b)
        self.entry_b = RosterEntryFactory(character_sheet=self.sheet_b)
        self.player_data_b = PlayerDataFactory(account=self.account_b)
        self.tenure_b = RosterTenureFactory(
            roster_entry=self.entry_b,
            player_data=self.player_data_b,
            end_date=None,
        )

        # Account C → character C (in room B, different room) — the "far observer".
        self.account_c = AccountFactory(username="vwv_account_c")
        self.character_c = CharacterFactory(db_key="VWVCharC", location=self.other_room)
        self.character_c.db_account = self.account_c
        self.character_c.save()
        self.sheet_c = CharacterSheetFactory(character=self.character_c)
        self.entry_c = RosterEntryFactory(character_sheet=self.sheet_c)
        self.player_data_c = PlayerDataFactory(account=self.account_c)
        self.tenure_c = RosterTenureFactory(
            roster_entry=self.entry_c,
            player_data=self.player_data_c,
            end_date=None,
        )

        # Two-layer outfit on character A:
        #   - shirt at TORSO/BASE  — concealed (covered by coat)
        #   - coat at TORSO/OVER   — visible, plain cut (conceals by default)
        self.shirt_template = ItemTemplateFactory(name="VWVShirt")
        TemplateSlotFactory(
            template=self.shirt_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        shirt_obj = ObjectDBFactory(
            db_key="VWVShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        shirt_obj.location = self.character_a
        shirt_obj.save()
        self.shirt = ItemInstanceFactory(
            template=self.shirt_template,
            game_object=shirt_obj,
            holder_character_sheet=self.sheet_a,
        )

        self.coat_template = ItemTemplateFactory(name="VWVCoat")
        TemplateSlotFactory(
            template=self.coat_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OVER,
        )
        coat_obj = ObjectDBFactory(
            db_key="VWVCoatObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        coat_obj.location = self.character_a
        coat_obj.save()
        self.coat = ItemInstanceFactory(
            template=self.coat_template,
            game_object=coat_obj,
            holder_character_sheet=self.sheet_a,
        )

        # Equip both on character A.
        EquippedItem.objects.create(
            character=self.character_a.sheet_data,
            item_instance=self.shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        EquippedItem.objects.create(
            character=self.character_a.sheet_data,
            item_instance=self.coat,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OVER,
        )

        self.client = APIClient()


class CharacterLookWornDataTests(_VisibleWornSetupMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.account_b)
        self.mask = create_mask(self.sheet_a, name="A Grey Hood")
        set_active_persona(self.sheet_a, self.mask)

    def _look(self, persona=None, **kwargs):
        response = self.client.post(
            f"/api/actions/characters/{self.character_b.pk}/dispatch/",
            {
                "ref": {"backend": "registry", "registry_key": "look"},
                "kwargs": (kwargs if kwargs else {"target_persona_id": (persona or self.mask).pk}),
            },
            format="json",
        )
        assert response.status_code == 200, response.data
        # REST renderer must serialize the actual result, not a mocked dispatcher.
        assert response.content
        return response.data

    def _detail(self, item=None, observer=None):
        item = item or self.coat
        observer = observer or self.character_b
        return self.client.get(f"/api/items/visible-item-detail/{item.pk}/?observer={observer.pk}")

    def _conceal(self, obj):
        return ConditionInstanceFactory(
            target=obj,
            condition=ConditionTemplateFactory(
                category=ConditionCategoryFactory(conceals_from_perception=True)
            ),
        )

    def _cancel(self, event):
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=FlowActionChoices.CANCEL_EVENT,
            parameters={},
        )
        definition = TriggerDefinitionFactory(event_name=event, flow_definition=flow)
        trigger = TriggerFactory(trigger_definition=definition, obj=self.room)
        self.room.trigger_handler.refresh()
        return trigger

    def test_ac1_exact_public_rows_no_carried_inventory(self):
        private = ItemInstanceFactory(holder_character_sheet=self.sheet_a, game_object=None)
        result = self._look()
        assert result["success"] is True
        assert result["data"] == {
            "visible_worn_items": [
                {
                    "id": self.coat.pk,
                    "display_name": self.coat.display_name,
                    "body_region": BodyRegion.TORSO,
                    "equipment_layer": EquipmentLayer.OVER,
                    "owner_persona_id": self.mask.pk,
                }
            ]
        }
        assert private.pk not in {row["id"] for row in result["data"]["visible_worn_items"]}
        assert self.character_a.key not in str(result["data"])

    def test_ac2_denied_absent_remote_and_noncharacter_have_no_data(self):
        hidden = self._conceal(self.character_a)
        denied = self._look()
        assert denied["success"] is False
        assert denied["data"] is None
        absent = self._look(target_persona_id=999999999)
        assert absent["data"] is None
        hidden.delete()
        self.character_a.location = self.other_room
        assert self._look()["data"] is None
        assert self._look(target=self.room.pk)["data"] is None
        obj = ObjectDBFactory(location=self.room)
        assert self._look(target=obj.pk)["data"] is None

    def test_ac3_real_cancel_suppresses_companion(self):
        for event in (EventName.ACTION_INTENT, EventName.EXAMINE_PRE):
            with self.subTest(event=event):
                trigger = self._cancel(event)
                examined_trigger = (
                    self._cancel(EventName.EXAMINED) if event == EventName.EXAMINE_PRE else None
                )
                result = self._look()
                assert result["data"] is None
                if event == EventName.EXAMINE_PRE:
                    assert result["success"] is True
                    assert result["message"] == ""
                    assert self.room.trigger_handler.fire_count(examined_trigger.pk) == 0
                    examined_trigger.delete()
                    self.room.trigger_handler.refresh()
                else:
                    assert result["success"] is False
                assert self.room.trigger_handler.fire_count(trigger.pk) == 1
                trigger.delete()
                self.room.trigger_handler.refresh()

    def test_ac4_detail_hidden_absent_detection_and_layers(self):
        missing = self.client.get(
            f"/api/items/visible-item-detail/999999999/?observer={self.character_b.pk}"
        )
        self._conceal(self.character_a)
        with patch("actions.target_resolution.visible_worn_items_for") as layers:
            hidden = self._detail()
            assert hidden.status_code == 404
            layers.assert_not_called()
        assert hidden.data == missing.data
        register_detection(self.sheet_b, self.character_a)
        assert self._detail().status_code == 200
        assert self._detail(self.shirt).status_code == 404
        condition = self._conceal(self.coat.game_object)
        assert self._detail().status_code == 404
        condition.delete()
        self.character_a.location = self.other_room
        assert self._detail().status_code == 404
        self.character_a.location = None
        self.character_b.location = None
        assert self._detail().status_code == 404

    def test_ac5_row_only_equipped_and_carried_have_no_proxy(self):
        self.coat.game_object = None
        self.coat.save(update_fields=["game_object"])
        before = ObjectDBFactory._meta.model.objects.count()
        assert self._look()["data"]["visible_worn_items"][0]["id"] == self.coat.pk
        response = self._detail()
        assert response.status_code == 200
        assert response.data["game_object_id"] is None
        carried = ItemInstanceFactory(holder_character_sheet=self.sheet_a, game_object=None)
        assert self._detail(carried).status_code == 404
        assert ObjectDBFactory._meta.model.objects.count() == before

    def test_ac6_persona_swap_and_stale_equipment(self):
        old = self._look()["data"]["visible_worn_items"][0]
        new = create_mask(self.sheet_a, name="A Blue Hood")
        set_active_persona(self.sheet_a, new)
        assert self._look(new)["data"]["visible_worn_items"][0]["owner_persona_id"] == new.pk
        response = self.client.post(
            f"/api/actions/characters/{self.character_b.pk}/dispatch/",
            {
                "ref": {"backend": "registry", "registry_key": "look_at_item"},
                "kwargs": {
                    "menu_target": {
                        "kind": "items",
                        "target_id": old["id"],
                        "owner_persona_id": old["owner_persona_id"],
                    }
                },
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.data["success"] is False
        unequip_item(equipped_item=self.coat.equipped_slots.first())
        assert self._detail().status_code == 404
        assert self.coat.pk not in {
            row["id"] for row in self._look(new)["data"]["visible_worn_items"]
        }

    def test_ac4_destroyed_and_moved_item_fail_closed(self):
        self.coat.game_object.location = self.other_room
        assert self._detail().status_code == 404
        assert self._look()["data"]["visible_worn_items"] == []
        self.coat.game_object.location = self.character_a
        self.coat.destroyed_at = timezone.now()
        self.coat.save(update_fields=["destroyed_at"])
        assert self._detail().status_code == 404
        assert self._look()["data"]["visible_worn_items"] == []

    def test_ac2_empty_character_and_ac5_self_layers(self):
        for item in (self.coat, self.shirt):
            unequip_item(equipped_item=item.equipped_slots.first())
        assert self._look()["data"] == {"visible_worn_items": []}
        # Existing self/staff layer bypass is covered by the retained detail tests.
        self.client.force_authenticate(user=self.account_a)
        assert self._detail(self.coat, self.character_a).status_code == 404


class VisibleWornObserverPrivacyTests(_VisibleWornSetupMixin, TestCase):
    def test_concealed_wearer_is_empty_before_enumeration_then_detected_is_visible(self):
        category = ConditionCategoryFactory(conceals_from_perception=True)
        template = ConditionTemplateFactory(category=category)
        ConditionInstanceFactory(target=self.character_a, condition=template)
        self.client.force_authenticate(user=self.account_b)
        url = (
            f"/api/items/visible-worn/?character={self.character_a.pk}"
            f"&observer={self.character_b.pk}"
        )
        with patch("world.items.views.visible_worn_items_for") as layers:
            response = self.client.get(url)
            assert response.status_code == 200
            assert response.data == []
            layers.assert_not_called()
        absent = self.client.get(
            f"/api/items/visible-worn/?character=999999999&observer={self.character_b.pk}"
        )
        assert absent.status_code == response.status_code
        assert absent.data == response.data
        register_detection(self.sheet_b, self.character_a)
        assert {row["id"] for row in self.client.get(url).data} == {self.coat.pk}

    def test_unlocated_other_characters_are_not_a_shared_room(self):
        self.character_a.location = None
        self.character_b.location = None
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(
            f"/api/items/visible-worn/?character={self.character_a.pk}"
            f"&observer={self.character_b.pk}"
        )
        assert response.status_code == 200
        assert response.data == []

    def test_concealment_keeps_self_and_staff_bypasses(self):
        category = ConditionCategoryFactory(conceals_from_perception=True)
        template = ConditionTemplateFactory(category=category)
        ConditionInstanceFactory(target=self.character_a, condition=template)
        self.client.force_authenticate(user=self.account_a)
        response = self.client.get(
            f"/api/items/visible-worn/?character={self.character_a.pk}"
            f"&observer={self.character_a.pk}"
        )
        assert {row["id"] for row in response.data} == {self.shirt.pk, self.coat.pk}
        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(f"/api/items/visible-worn/?character={self.character_a.pk}")
        assert {row["id"] for row in response.data} == {self.shirt.pk, self.coat.pk}


class VisibleWornItemViewSetTests(_VisibleWornSetupMixin, TestCase):
    """Tests for ``GET /api/items/visible-worn/?character=N``."""

    def test_unauthenticated_returns_401_or_403(self) -> None:
        """Unauthenticated requests are rejected by the permission class."""
        response = self.client.get(f"/api/items/visible-worn/?character={self.character_a.pk}")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_same_room_observer_returns_visible_items_only(self) -> None:
        """Account B (same room) sees the coat but not the concealed shirt."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(
            f"/api/items/visible-worn/?character={self.character_a.pk}"
            f"&observer={self.character_b.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertIn(self.coat.pk, ids)
        self.assertNotIn(self.shirt.pk, ids)

    def test_different_room_observer_returns_empty(self) -> None:
        """Account C (different room) sees nothing — out of scope, empty list."""
        self.client.force_authenticate(user=self.account_c)
        response = self.client.get(
            f"/api/items/visible-worn/?character={self.character_a.pk}"
            f"&observer={self.character_c.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_self_look_returns_everything_including_concealed(self) -> None:
        """Account A looking at character A sees the concealed shirt."""
        self.client.force_authenticate(user=self.account_a)
        response = self.client.get(
            f"/api/items/visible-worn/?character={self.character_a.pk}"
            f"&observer={self.character_a.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertIn(self.shirt.pk, ids)
        self.assertIn(self.coat.pk, ids)

    def test_staff_returns_everything_from_anywhere(self) -> None:
        """Staff bypass: not in the same room, still sees concealed items.

        Staff doesn't need to pass an observer (full visibility).
        """
        staff = AccountFactory(username="vwv_staff", is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(f"/api/items/visible-worn/?character={self.character_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data}
        self.assertIn(self.shirt.pk, ids)
        self.assertIn(self.coat.pk, ids)

    def test_missing_character_param_returns_empty(self) -> None:
        """No ``?character=`` query → empty list (not an error)."""
        self.client.force_authenticate(user=self.account_a)
        response = self.client.get(f"/api/items/visible-worn/?observer={self.character_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_unknown_character_id_returns_empty(self) -> None:
        """An ID that doesn't exist returns an empty list, not 404."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(
            f"/api/items/visible-worn/?character=999999999&observer={self.character_b.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_missing_observer_returns_empty_for_non_staff(self) -> None:
        """Non-staff requests without ``?observer=`` return empty (no leak)."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(f"/api/items/visible-worn/?character={self.character_a.pk}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_observer_not_owned_by_user_returns_empty(self) -> None:
        """Non-staff supplying an observer they don't own returns empty."""
        self.client.force_authenticate(user=self.account_b)
        # Account B tries to claim character A as their observer.
        response = self.client.get(
            f"/api/items/visible-worn/?character={self.character_a.pk}"
            f"&observer={self.character_a.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])


class VisibleItemDetailViewSetTests(_VisibleWornSetupMixin, TestCase):
    """Tests for ``GET /api/items/visible-item-detail/<id>/``."""

    def test_detail_visible_item_returns_full_data(self) -> None:
        """Account B (same room) can fetch the visible coat — full payload."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(
            f"/api/items/visible-item-detail/{self.coat.pk}/?observer={self.character_b.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.coat.pk)
        # The detail serializer mirrors ItemInstanceReadSerializer — confirm
        # the nested template payload is present (not just an id).
        self.assertEqual(response.data["template"]["name"], "VWVCoat")

    def test_detail_concealed_item_returns_404(self) -> None:
        """A concealed shirt is hidden — non-staff non-self gets 404."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(
            f"/api/items/visible-item-detail/{self.shirt.pk}/?observer={self.character_b.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_staff_can_fetch_concealed(self) -> None:
        """Staff bypass: concealed item is reachable (no observer needed)."""
        staff = AccountFactory(username="vwv_detail_staff", is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(f"/api/items/visible-item-detail/{self.shirt.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.shirt.pk)

    def test_detail_item_from_another_room_returns_404(self) -> None:
        """Account C is in a different room → both items are out of scope (404)."""
        self.client.force_authenticate(user=self.account_c)
        coat_response = self.client.get(
            f"/api/items/visible-item-detail/{self.coat.pk}/?observer={self.character_c.pk}"
        )
        self.assertEqual(coat_response.status_code, status.HTTP_404_NOT_FOUND)
        shirt_response = self.client.get(
            f"/api/items/visible-item-detail/{self.shirt.pk}/?observer={self.character_c.pk}"
        )
        self.assertEqual(shirt_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_self_can_fetch_concealed(self) -> None:
        """Self-look: account A can fetch the concealed shirt on character A."""
        self.client.force_authenticate(user=self.account_a)
        response = self.client.get(
            f"/api/items/visible-item-detail/{self.shirt.pk}/?observer={self.character_a.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.shirt.pk)

    def test_detail_missing_observer_returns_404_for_non_staff(self) -> None:
        """Non-staff requests without ``?observer=`` get 404."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(f"/api/items/visible-item-detail/{self.coat.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_observer_not_owned_returns_404(self) -> None:
        """Non-staff supplying an observer they don't own gets 404."""
        self.client.force_authenticate(user=self.account_b)
        # Account B tries to claim character A as their observer.
        response = self.client.get(
            f"/api/items/visible-item-detail/{self.coat.pk}/?observer={self.character_a.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_detail_includes_game_object_id(self) -> None:
        """game_object_id is the ObjectDB pk, distinct from the ItemInstance id (#1909)."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(
            f"/api/items/visible-item-detail/{self.coat.pk}/?observer={self.character_b.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["game_object_id"], self.coat.game_object_id)
        self.assertNotEqual(response.data["game_object_id"], response.data["id"])

    def test_detail_can_steal_false_by_default(self) -> None:
        """Theft is a default-deny consent category: no rule means can_steal=False (#1909)."""
        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(
            f"/api/items/visible-item-detail/{self.coat.pk}/?observer={self.character_b.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["can_steal"])

    def test_detail_can_steal_true_once_owner_whitelists_actor(self) -> None:
        """Once character A opts character B into theft consent, can_steal flips True (#1909)."""
        from world.consent.constants import ConsentMode
        from world.consent.services import (
            add_social_consent_whitelist,
            set_social_consent_category_rule,
            set_social_consent_preference,
            theft_category,
        )

        preference = set_social_consent_preference(self.tenure_a, allow_social_actions=True)
        set_social_consent_category_rule(preference, theft_category(), ConsentMode.ALLOWLIST)
        add_social_consent_whitelist(self.tenure_a, self.tenure_b, theft_category())

        self.client.force_authenticate(user=self.account_b)
        response = self.client.get(
            f"/api/items/visible-item-detail/{self.coat.pk}/?observer={self.character_b.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["can_steal"])

    def test_detail_self_look_never_flags_can_steal(self) -> None:
        """Self-look on your own worn item never renders the steal affordance."""
        self.client.force_authenticate(user=self.account_a)
        response = self.client.get(
            f"/api/items/visible-item-detail/{self.shirt.pk}/?observer={self.character_a.pk}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["can_steal"])

    def test_detail_staff_never_flags_can_steal(self) -> None:
        """Staff bypass has no observer concept — can_steal defaults to False."""
        staff = AccountFactory(username="vwv_detail_staff_steal", is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(f"/api/items/visible-item-detail/{self.coat.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["can_steal"])
