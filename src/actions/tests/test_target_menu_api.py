"""Authenticated target-menu journeys and fail-closed executable wire contracts."""

from contextlib import ExitStack, contextmanager
import json
import re
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from actions.base import Action
from actions.constants import Pipeline
from actions.models import ActionTemplate, ActionTemplateGate, ConsequencePool, ConsequencePoolEntry
from evennia_extensions.factories import AccountFactory, ObjectDBFactory, RoomProfileFactory
from flows.object_states.base_state import BaseState
from flows.scene_data_manager import SceneDataManager
from world.checks.factories import ConsequenceFactory
from world.conditions.factories import CapabilityTypeFactory
from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, TemplateSlotFactory
from world.items.models import EquippedItem, ItemTemplateAppearanceEffect, OwnershipEvent
from world.magic.factories import (
    CharacterTechniqueFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueFactory,
)
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import (
    ApproachConsequence,
    ChallengeInstance,
    ChallengeTemplateConsequence,
    ObjectProperty,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PlaceFactory
from world.scenes.models import Persona, Scene
from world.scenes.place_models import PlacePresence
from world.scenes.services import create_mask, set_active_persona
from world.traits.factories import CheckOutcomeFactory


@contextmanager
def menu_read_only():
    """Reject gameplay writes, state initialization, events and behavior imports."""

    def sql_read(execute, sql, params, many, context):
        text = sql.upper()
        assert sql.lstrip().upper().startswith(("SELECT", "WITH")), sql
        assert not set(re.findall(r"[A-Z_]+", text)).intersection(
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
            }
        ), sql
        assert not re.search(r"FOR\s+(UPDATE|SHARE|NO\s+KEY|KEY\s+SHARE)", text), sql
        return execute(sql, params, many, context)

    def empty_hook(state, *args, **kwargs):
        assert not state.packages, "A menu attempted a behavior hook."

    with ExitStack() as stack:
        stack.enter_context(connection.execute_wrapper(sql_read))
        stack.enter_context(patch.object(BaseState, "_run_package_hook", empty_hook))
        for owner, name in (
            (Action, "run"),
            (BaseState, "initialize_state"),
            (SceneDataManager, "initialize_state_for_object"),
            (SceneDataManager, "get_state_by_pk"),
        ):
            stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
        for path in (
            "flows.emit.emit_event",
            "behaviors.models.import_module",
            "world.mechanics.challenge_resolution.instantiate_challenge",
        ):
            stack.enter_context(patch(path, side_effect=AssertionError(path)))
        yield


@override_settings(TARGET_MENU_ACCOUNT_RATE="1000/min")
class TargetMenuAPITests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.profile = RoomProfileFactory(objectdb=self.room, published_at=timezone.now())
        RoomProfileFactory(objectdb=self.remote, published_at=timezone.now())
        self.entry = RosterEntryFactory()
        self.sheet = self.entry.character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        assert self.actor.pk == self.sheet.pk
        self.account = AccountFactory(is_staff=False)
        self.tenure = RosterTenureFactory(
            roster_entry=self.entry,
            player_data=PlayerDataFactory(account=self.account),
            start_date=timezone.now(),
            end_date=None,
        )
        self.client = APIClient()
        # Shared-login middleware needs an existing session before the guarded GET.
        self.client.session.save()
        self.client.force_authenticate(user=self.account)
        self.other_entry = RosterEntryFactory()
        self.other_sheet = self.other_entry.character_sheet
        self.other = self.other_sheet.character
        self.other.location = self.room
        self.mask = create_mask(self.other_sheet, name="A copper mask")
        set_active_persona(self.other_sheet, self.mask)
        self.item = self.make_item("Carried coat", equipment=True)
        self.bag = self.make_item("Carried bag", container=True)
        self.obj = ObjectDBFactory(
            db_typeclass_path="typeclasses.objects.Object", location=self.room
        )
        self.exit = ObjectDBFactory(
            db_typeclass_path="typeclasses.exits.Exit", location=self.room, destination=self.remote
        )
        self.place = PlaceFactory(room=self.profile)

    def tearDown(self):
        from django.core.cache import cache

        cache.clear()

    def make_item(self, name, *, location=None, equipment=False, container=False, row_only=False):
        template = ItemTemplateFactory(
            name=name,
            size=1,
            is_container=container,
            supports_open_close=container,
            container_capacity=4 if container else 0,
            container_max_item_size=5 if container else 0,
        )
        if equipment:
            TemplateSlotFactory(
                template=template, body_region=BodyRegion.TORSO, equipment_layer=EquipmentLayer.BASE
            )
        return ItemInstanceFactory(
            template=template,
            holder_character_sheet=self.sheet,
            contained_in=None,
            is_open=True,
            quality_tier=None,
            game_object=None
            if row_only
            else ObjectDBFactory(
                db_typeclass_path="typeclasses.objects.Object",
                location=self.actor if location is None else location,
            ),
        )

    def url(self, kind="items", target=None, actor=None):
        target = self.item if target is None else target
        return f"/api/actions/characters/{(actor or self.actor).pk}/{kind}/{target.pk}/menu/"

    def headers(self, response):
        assert response["Cache-Control"] == "private, no-store"
        assert {"Cookie", "Authorization"}.issubset(set(response["Vary"].split(", ")))

    def read(self, kind="items", target=None, **query):
        with menu_read_only():
            response = self.client.get(self.url(kind, target), query)
        assert response.status_code == 200, response.content
        self.headers(response)
        assert set(response.data) == {"actor_id", "target", "label", "groups", "entries"}
        for entry in response.data["entries"]:
            assert set(entry) == {
                "key",
                "label",
                "group",
                "ref",
                "kwargs",
                "available",
                "reasons",
                "inputs",
                "candidates",
                "next_candidate_cursor",
                "action",
                "risk",
            }
            assert entry["kwargs"] == (
                {"menu_target": entry["kwargs"]["menu_target"]}
                if entry["group"] != "authored"
                else {}
            )
            for candidate in entry["candidates"]:
                expected = {"give": {"recipient_persona_id"}, "put_in": {"container_item_id"}}.get(
                    entry["key"]
                )
                if expected is not None:
                    assert set(candidate["kwargs"]) == expected
                else:
                    assert set(candidate["kwargs"]).issubset({"use_target", "option_id"})
        return response.data

    def entries(self, payload):
        return {row["key"]: row for row in payload["entries"]}

    def dispatch(self, entry, candidate=None):
        values = {**entry["kwargs"], **({} if candidate is None else candidate["kwargs"])}
        return self.client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {"ref": entry["ref"], "kwargs": values},
            format="json",
        )

    def test_read_equip_drop_get_and_stale_possession(self):
        before = (
            Scene.objects.count(),
            OwnershipEvent.objects.count(),
            EquippedItem.objects.count(),
        )
        initial = self.read()
        rows = self.entries(initial)
        assert [row["label"] for row in initial["entries"]][:5] == [
            "Look",
            "Drop",
            "Equip",
            "Give",
            "Put in",
        ]
        assert {"get", "steal", "unequip", "set_container_policy", "activate_permit"}.isdisjoint(
            rows
        )
        assert before == (
            Scene.objects.count(),
            OwnershipEvent.objects.count(),
            EquippedItem.objects.count(),
        )
        response = self.dispatch(rows["equip"])
        assert response.status_code == 200, response.data
        assert response.data["success"], response.data
        rows = self.entries(self.read())
        assert "equip" not in rows
        assert rows["unequip"]["available"]
        assert self.dispatch(rows["unequip"]).data["success"]
        assert self.dispatch(self.entries(self.read())["drop"]).data["success"]
        assert "get" not in self.entries(self.read())
        self.item.holder_character_sheet = None
        self.item.save(update_fields=["holder_character_sheet"])
        assert self.dispatch(self.entries(self.read())["get"]).data["success"]
        stale = self.entries(self.read())["drop"]
        self.item.game_object.location = self.remote
        assert not self.dispatch(stale).data["success"]

    def test_ownership_context_and_neutral_errors(self):
        response = APIClient().get(self.url())
        assert response.status_code in (401, 403)
        self.headers(response)
        self.client.force_authenticate(user=AccountFactory(is_staff=False))
        response = self.client.get(self.url())
        assert response.status_code == 403
        self.headers(response)
        self.client.force_authenticate(user=self.account)
        self.tenure.end_date = timezone.now()
        self.tenure.save(update_fields=["end_date"])
        assert self.client.get(self.url()).status_code == 403
        self.tenure.end_date = None
        self.tenure.save(update_fields=["end_date"])
        for kind, target in (("unknown", self.item), ("objects", self.actor)):
            response = self.client.get(self.url(kind, target))
            assert response.status_code == 404
            assert response.data == {"detail": "That isn't available."}
            self.headers(response)
        absent = self.client.get(self.url().replace(f"/{self.item.pk}/menu/", "/999999999/menu/"))
        self.item.game_object.location = self.remote
        moved = self.client.get(self.url())
        with patch("actions.target_resolution.can_perceive", return_value=False):
            hidden = self.client.get(self.url("objects", self.obj))
        assert absent.data == moved.data == hidden.data == {"detail": "That isn't available."}
        self.headers(hidden)
        self.item.game_object.location = self.actor
        for query in (
            {"owner_persona_id": "1.5"},
            {"owner_persona_id": 0},
            {"owner_persona_id": 1, "container_item_id": 2},
            {"inputs_for": "unknown"},
        ):
            response = self.client.get(self.url(), query)
            assert response.status_code == 400, response.data
            self.headers(response)
        response = self.client.get(
            self.url("objects", self.obj), {"container_item_id": self.bag.pk}
        )
        assert response.status_code == 404
        assert response.data == absent.data
        baseline = self.read()
        with menu_read_only():
            ignored = self.client.get(
                self.url(),
                {"harmless_unknown": "objects/999999", "item_id": 999999, "target": "private"},
            )
        assert ignored.status_code == 200
        assert ignored.data == baseline

    def test_object_item_exit_place_and_row_only_identity(self):
        assert set(self.entries(self.read("objects", self.obj))) == {"look"}
        ground = self.make_item("Ground object", location=self.room)
        ground.holder_character_sheet = None
        ground.save(update_fields=["holder_character_sheet"])
        payload = self.read("objects", ground.game_object)
        assert payload["target"] == {"kind": "objects", "target_id": ground.game_object.pk}
        assert self.entries(payload)["get"]["kwargs"] == {
            "menu_target": {"kind": "items", "target_id": ground.pk}
        }
        exits = self.entries(self.read("exits", self.exit))
        assert set(exits) == {"look", "traverse_exit"}
        assert all(
            row["kwargs"] == {"menu_target": {"kind": "exits", "target_id": self.exit.pk}}
            for row in exits.values()
        )
        join = self.entries(self.read("places", self.place))
        assert set(join) == {"join_place"}
        assert join["join_place"]["kwargs"] == {
            "menu_target": {"kind": "places", "target_id": self.place.pk}
        }
        assert self.dispatch(join["join_place"]).data["success"]
        assert not self.dispatch(join["join_place"]).data["success"]
        leave = self.entries(self.read("places", self.place))
        assert set(leave) == {"leave_place"}
        assert self.dispatch(leave["leave_place"]).data["success"]
        assert not PlacePresence.objects.filter(place=self.place).exists()
        self.exit.location = self.remote
        assert not self.dispatch(exits["traverse_exit"]).data["success"]
        row = self.make_item("Row only", row_only=True)
        assert set(self.entries(self.read(target=row))) == {"look_at_item"}
        assert self.dispatch(self.entries(self.read(target=row))["look_at_item"]).data["success"]
        assert row.game_object is None

    def test_give_put_complete_candidates_and_stale_rechecks(self):
        give = self.entries(self.read())["give"]
        assert give["available"]
        assert give["inputs"][0]["name"] == "recipient_persona_id"
        candidate = next(
            row
            for row in give["candidates"]
            if row["kwargs"]["recipient_persona_id"] == self.mask.pk
        )
        assert candidate["available"]
        assert self.other.key not in candidate["label"]
        assert not self.dispatch(give).data["success"]
        self.other.location = self.remote
        assert not self.dispatch(give, candidate).data["success"]
        assert not self.entries(self.read())["give"]["available"]
        self.other.location = self.room
        self.make_item("Room bag", container=True, location=self.room)
        put = self.entries(self.read(inputs_for="put_in"))["put_in"]
        assert {row["kwargs"]["container_item_id"] for row in put["candidates"]} == {self.bag.pk}
        self.bag.is_open = False
        self.bag.save(update_fields=["is_open"])
        blocked = self.entries(self.read())["put_in"]
        assert not blocked["available"]
        assert blocked["reasons"]
        assert blocked["candidates"]
        assert not blocked["candidates"][0]["available"]
        assert not self.dispatch(put, put["candidates"][0]).data["success"]
        self.bag.is_open = True
        self.bag.save(update_fields=["is_open"])
        put = self.entries(self.read())["put_in"]
        assert self.dispatch(put, put["candidates"][0]).data["success"]
        contained = self.entries(self.read(container_item_id=self.bag.pk))
        assert "take_out" in contained
        assert "get" not in contained
        assert self.dispatch(contained["take_out"]).data["success"]
        assert self.dispatch(give, candidate).data["success"]
        assert self.client.get(self.url()).status_code == 404

    def test_give_candidate_cursor_pages_and_rejects_invalid_cursor(self):
        # Create enough active personas to cross the shared page boundary.
        recipients = []
        for _ in range(28):
            entry = RosterEntryFactory()
            recipient = entry.character_sheet.character
            recipient.location = self.room
            persona = create_mask(entry.character_sheet, name=f"Recipient {len(recipients)}")
            set_active_persona(entry.character_sheet, persona)
            recipients.append(persona)
        recipient_count = Persona.objects.filter(
            character_sheet__character__db_location=self.room
        ).count()
        assert recipient_count >= 25
        first = self.read()
        give = self.entries(first)["give"]
        assert len(give["candidates"]) <= 25
        assert give["next_candidate_cursor"]
        from actions.target_menu import build_target_menu
        from actions.target_menu_types import MenuTargetKind, MenuTargetRequest

        with self.assertRaises(ValueError):
            build_target_menu(
                self.actor,
                MenuTargetRequest(MenuTargetKind.ITEMS, self.item.pk),
                inputs_for="give",
                candidate_cursor=give["next_candidate_cursor"],
                account_id=self.account.pk + 1,
            )
        deleted_id = give["candidates"][0]["kwargs"]["recipient_persona_id"]
        expected_ids = {persona.pk for persona in recipients} | {self.mask.pk}
        Persona.objects.filter(pk=deleted_id).delete()
        pages = [give]
        cursor = give["next_candidate_cursor"]
        while cursor:
            page = self.entries(self.read(inputs_for="give", candidate_cursor=cursor))["give"]
            pages.append(page)
            assert len(page["candidates"]) <= 25
            cursor = page["next_candidate_cursor"]
        keys = [row["key"] for page in pages for row in page["candidates"]]
        assert len(keys) == len(set(keys))
        candidate_ids = {int(key) for key in keys}
        assert candidate_ids == expected_ids, {
            "missing": expected_ids - candidate_ids,
            "extra": candidate_ids - expected_ids,
        }
        invalid = self.client.get(self.url(), {"inputs_for": "give", "candidate_cursor": "bad"})
        assert invalid.status_code == 400
        oversize = self.client.get(
            self.url(), {"inputs_for": "give", "candidate_cursor": "x" * 2049}
        )
        assert oversize.status_code == 400
        no_action = self.client.get(self.url(), {"candidate_cursor": give["next_candidate_cursor"]})
        assert no_action.status_code == 400
        wrong_action = self.client.get(
            self.url(),
            {"inputs_for": "put_in", "candidate_cursor": give["next_candidate_cursor"]},
        )
        assert wrong_action.status_code == 400

    def test_worn_visibility_and_wearer_privacy(self):
        self.item.game_object.location = self.other
        self.item.holder_character_sheet = self.other_sheet
        self.item.save(update_fields=["holder_character_sheet"])
        EquippedItem.objects.create(
            character=self.other_sheet,
            item_instance=self.item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        payload = self.read(owner_persona_id=self.mask.pk)
        assert {"equip", "get", "drop", "give", "put_in", "unequip"}.isdisjoint(
            self.entries(payload)
        )
        stale = self.entries(payload)["look_at_item"]
        with patch("actions.target_resolution.can_perceive", return_value=False):
            assert (
                self.client.get(self.url(), {"owner_persona_id": self.mask.pk}).status_code == 404
            )
            assert not self.dispatch(stale).data["success"]
        with patch("actions.target_resolution.visible_worn_items_for", return_value=[]):
            assert (
                self.client.get(self.url(), {"owner_persona_id": self.mask.pk}).status_code == 404
            )

    def test_use_options_typed_cosmetic_inputs_and_depletion(self):
        from actions.target_menu_serializers import MenuCandidateSerializer, MenuEntrySerializer

        trait = FormTraitFactory(is_cosmetic=True, composite_option=None)
        option = FormTraitOptionFactory(trait=trait, requires_teaching=False)
        unlearned = FormTraitOptionFactory(trait=trait, requires_teaching=True)
        source = self.make_item("Cosmetic row", row_only=True)
        source.template.is_consumable = True
        source.template.max_charges = 3
        source.template.on_use_pool = None
        source.template.on_use_target_kind = None
        source.template.save()
        source.charges = 3
        source.save(update_fields=["charges"])
        ItemTemplateAppearanceEffect.objects.create(
            item_template=source.template, trait=trait, target_option=None
        )
        use = self.entries(self.read(target=source))["use_item"]
        assert use["available"]
        assert use["risk"] is None
        assert [(row["name"], row["required"]) for row in use["inputs"]] == [
            ("option_id", True),
            ("descriptor", False),
        ]
        candidate = next(
            row for row in use["candidates"] if row["kwargs"]["option_id"] == option.pk
        )
        blocked = next(
            row for row in use["candidates"] if row["kwargs"]["option_id"] == unlearned.pk
        )
        assert candidate["available"]
        assert not blocked["available"]
        assert blocked["reasons"]
        assert not self.dispatch(use).data["success"]
        assert source.charges == 3
        for blend in (False, True):
            extra = {"descriptor": "silver filigree", "blend": blend}
            row = {**use, "kwargs": {**use["kwargs"], **extra}}
            assert (
                MenuEntrySerializer(row, context={"action_key": "use_item"}).data["kwargs"]
                == row["kwargs"]
            )
            chosen = {**candidate, "kwargs": {**candidate["kwargs"], **extra}}
            assert (
                MenuCandidateSerializer(
                    chosen, context={"action_key": "use_item", "candidate_kind": "combination"}
                ).data["kwargs"]
                == chosen["kwargs"]
            )
        from world.forms.factories import CharacterFormFactory, CharacterFormValueFactory

        form = CharacterFormFactory(character=self.sheet)
        CharacterFormValueFactory(form=form, trait=trait, option=option)
        response = self.dispatch(
            use,
            {
                **candidate,
                "kwargs": {**candidate["kwargs"], "descriptor": "silver filigree", "blend": False},
            },
        )
        assert response.status_code == 200, response.data
        assert response.data["success"], response.data
        source.charges = 0
        source.save(update_fields=["charges"])
        depleted = self.entries(self.read(target=source))["use_item"]
        assert not depleted["available"]
        assert depleted["reasons"]
        assert not self.dispatch(use, candidate).data["success"]
        assert source.charges == 0

    def test_put_cursor_continues_from_initial_menu(self):
        containers = [self.make_item(f"Paged bag {index}", container=True) for index in range(27)]
        expected_ids = {self.bag.pk, *(item.pk for item in containers)}
        initial = self.entries(self.read())["put_in"]
        assert len(initial["candidates"]) == 25
        assert initial["next_candidate_cursor"]
        pages = [initial]
        cursor = initial["next_candidate_cursor"]
        while cursor:
            page = self.entries(self.read(inputs_for="put_in", candidate_cursor=cursor))["put_in"]
            pages.append(page)
            cursor = page["next_candidate_cursor"]
        candidate_ids = {
            row["kwargs"]["container_item_id"] for page in pages for row in page["candidates"]
        }
        assert candidate_ids == expected_ids

    def test_cursor_binds_effective_item_source(self):
        for index in range(26):
            entry = RosterEntryFactory()
            entry.character_sheet.character.location = self.room
            persona = create_mask(entry.character_sheet, name=f"Cursor recipient {index}")
            set_active_persona(entry.character_sheet, persona)
        first = self.read()["entries"]
        cursor = self.entries({"entries": first})["give"]["next_candidate_cursor"]
        assert cursor
        from dataclasses import replace

        from actions.target_menu import build_target_menu
        from actions.target_menu_types import MenuTargetKind, MenuTargetRequest
        from actions.target_resolution import resolve_menu_target

        request = MenuTargetRequest(MenuTargetKind.ITEMS, self.item.pk)
        resolved = resolve_menu_target(self.actor, request)
        assert resolved is not None
        changed_source = replace(resolved, item=self.bag)
        with patch("actions.target_menu.resolve_menu_target", return_value=changed_source):
            with self.assertRaises(ValueError):
                build_target_menu(
                    self.actor,
                    request,
                    inputs_for="give",
                    candidate_cursor=cursor,
                    account_id=self.account.pk,
                )

    def test_use_product_cursor_pages_by_target_and_option_ids(self):
        trait = FormTraitFactory(is_cosmetic=True, composite_option=None)
        options = [FormTraitOptionFactory(trait=trait, requires_teaching=False) for _ in range(30)]
        source = self.make_item("Paged cosmetic", row_only=True)
        source.template.is_consumable = True
        source.template.max_charges = 3
        source.template.on_use_pool = None
        source.template.on_use_target_kind = None
        source.template.save()
        source.charges = 3
        source.save(update_fields=["charges"])
        ItemTemplateAppearanceEffect.objects.create(
            item_template=source.template, trait=trait, target_option=None
        )
        from actions.definitions.items import UseItemAction

        availability_checks = []
        original_check = UseItemAction.check_availability

        def counted_check(action, *args, **kwargs):
            availability_checks.append(action)
            return original_check(action, *args, **kwargs)

        with patch.object(UseItemAction, "check_availability", counted_check):
            first = self.entries(self.read(target=source))["use_item"]
        assert len(availability_checks) <= 26
        assert len(first["candidates"]) == 25
        assert first["next_candidate_cursor"]
        second_page = self.read(
            target=source,
            inputs_for="use_item",
            candidate_cursor=first["next_candidate_cursor"],
        )
        second = self.entries(second_page)["use_item"]
        assert second["next_candidate_cursor"] is None
        candidate_ids = [
            row["kwargs"]["option_id"] for page in (first, second) for row in page["candidates"]
        ]
        assert candidate_ids == [option.pk for option in options]

    def authored_fixture(self):
        capability = CapabilityTypeFactory(innate_baseline=0)
        technique = TechniqueFactory(intensity=2)
        TechniqueCapabilityGrantFactory(
            technique=technique, capability=capability, base_value=5, intensity_multiplier=1
        )
        known = CharacterTechniqueFactory(character=self.sheet, technique=technique)
        prop = PropertyFactory()
        ObjectProperty.objects.create(object=self.obj, property=prop, value=1)
        template = ChallengeTemplateFactory(severity=3)
        template.properties.add(prop)
        application = ApplicationFactory(
            capability=capability, target_property=prop, default_template=template
        )
        approach = ChallengeApproachFactory(
            challenge_template=template, application=application, display_name="Ignite fixture"
        )
        tier = CheckOutcomeFactory(success_level=-1)
        death = ConsequenceFactory(
            outcome_tier=tier,
            character_loss=True,
            label="PRIVATE-LABEL",
            mechanical_description="PRIVATE-MECHANICAL-DETAIL",
        )
        ChallengeTemplateConsequence.objects.create(challenge_template=template, consequence=death)
        return known, template, approach, tier, death

    def test_authored_association_tier_override_and_stale_capability(self):
        known, template, approach, tier, _ = self.authored_fixture()
        with patch(
            "world.mechanics.services._get_difficulty_indicator_for_check",
            return_value=DifficultyIndicator.MODERATE,
        ):
            before = ChallengeInstance.objects.count()
            payload = self.read("objects", self.obj)
            rows = [row for row in payload["entries"] if row["group"] == "authored"]
            assert len(rows) == 1
            assert ChallengeInstance.objects.count() == before
            entry = rows[0]
            assert entry["ref"]["backend"] == "world_interaction"
            assert entry["ref"]["target_object_id"] == self.obj.pk
            assert entry["action"]["difficulty"] == "moderate"
            assert entry["risk"]["known"]
            assert entry["risk"]["character_loss_possible"]
            assert all(
                set(row) == {"stage", "tier", "character_loss"} for row in entry["risk"]["outcomes"]
            )
            assert "PRIVATE-MECHANICAL-DETAIL" not in json.dumps(payload)
            assert "PRIVATE-LABEL" not in json.dumps(payload)
            assert not any(
                row["group"] == "authored" for row in self.read("exits", self.exit)["entries"]
            )
            assert not any(
                row["group"] == "authored" for row in self.read("places", self.place)["entries"]
            )
            safe = ConsequenceFactory(outcome_tier=tier, character_loss=False)
            ApproachConsequence.objects.create(approach=approach, consequence=safe)
            assert not next(
                row
                for row in self.read("objects", self.obj)["entries"]
                if row["group"] == "authored"
            )["risk"]["character_loss_possible"]
            other_loss = ConsequenceFactory(
                outcome_tier=CheckOutcomeFactory(success_level=-2), character_loss=True
            )
            ChallengeTemplateConsequence.objects.create(
                challenge_template=template, consequence=other_loss
            )
            assert next(
                row
                for row in self.read("objects", self.obj)["entries"]
                if row["group"] == "authored"
            )["risk"]["character_loss_possible"]
            instance = ChallengeInstance.objects.create(
                template=template,
                location=self.room,
                target_object=self.obj,
                is_active=True,
                is_revealed=True,
            )
            authored = next(
                row
                for row in self.read("objects", self.obj)["entries"]
                if row["group"] == "authored"
            )
            assert authored["ref"]["backend"] == "challenge"
            assert authored["ref"]["challenge_instance_id"] == instance.pk
            instance.is_revealed = False
            instance.save(update_fields=["is_revealed"])
            assert not any(
                row["ref"]["backend"] == "challenge"
                for row in self.read("objects", self.obj)["entries"]
            )
            known.delete()
            assert self.dispatch(entry).status_code == 400

    def test_authored_template_pools_null_target_and_unknown_risk(self):
        from dataclasses import replace

        from actions.target_menu import _risk
        from world.mechanics.services import get_available_actions

        _, _, approach, tier, death = self.authored_fixture()
        pool = ConsequencePool.objects.create(name=f"Menu main {self.actor.pk}")
        ConsequencePoolEntry.objects.create(
            pool=pool, consequence=ConsequenceFactory(outcome_tier=tier, character_loss=False)
        )
        template = ActionTemplate.objects.create(
            name=f"Menu template {self.actor.pk}",
            check_type=approach.check_type,
            consequence_pool=pool,
            pipeline=Pipeline.SINGLE,
        )
        approach.action_template = template
        approach.save(update_fields=["action_template"])
        with patch(
            "world.mechanics.services._get_difficulty_indicator_for_check",
            return_value=DifficultyIndicator.MODERATE,
        ):
            row = next(
                row
                for row in self.read("objects", self.obj)["entries"]
                if row["group"] == "authored"
            )
            assert row["risk"]["known"]
            assert not row["risk"]["character_loss_possible"]
            gate_pool = ConsequencePool.objects.create(name=f"Menu gate {self.actor.pk}")
            ConsequencePoolEntry.objects.create(pool=gate_pool, consequence=death)
            ActionTemplateGate.objects.create(
                action_template=template,
                check_type=approach.check_type,
                consequence_pool=gate_pool,
                gate_role="activation",
                step_order=-1,
            )
            template.pipeline = Pipeline.GATED
            template.save(update_fields=["pipeline"])
            row = next(
                row
                for row in self.read("objects", self.obj)["entries"]
                if row["group"] == "authored"
            )
            assert row["risk"]["character_loss_possible"]
            assert {outcome["stage"] for outcome in row["risk"]["outcomes"]} == {
                "main",
                "gate:activation",
            }
            actual = next(
                row
                for row in get_available_actions(self.actor, self.room)
                if row.target_object == self.obj
            )
            null = replace(actual, target_object=None, challenge_instance_id=999991)
            with patch(
                "actions.target_menu.get_available_actions", return_value=[null, actual, actual]
            ):
                rows = [
                    row
                    for row in self.read("objects", self.obj)["entries"]
                    if row["group"] == "authored"
                ]
            assert len(rows) == 2
            assert rows[0]["key"] != rows[1]["key"]
            actual.resolved_challenge_approach = None
            assert _risk(actual) == {
                "known": False,
                "character_loss_possible": None,
                "outcomes": [],
            }

    def test_account_throttle_headers_retry_after_and_recomposition(self):
        from actions.target_menu import build_target_menu
        from actions.target_menu_views import MenuAccountThrottle

        with (
            override_settings(TARGET_MENU_ACCOUNT_RATE="3/min"),
            patch(
                "actions.target_menu_views.build_target_menu", wraps=build_target_menu
            ) as compose,
        ):
            for url in (self.url(), self.url("objects", self.obj), self.url("places", self.place)):
                assert self.client.get(url).status_code == 200
            response = self.client.get(self.url("exits", self.exit))
            assert response.status_code == 429
            assert int(response["Retry-After"]) > 0
            self.headers(response)
            assert compose.call_count == 3
            assert self.client.get(self.url(), {"inputs_for": "give"}).status_code == 429
            assert compose.call_count == 3
        MenuAccountThrottle.cache.clear()
        with patch(
            "actions.target_menu_views.build_target_menu", wraps=build_target_menu
        ) as compose:
            first = self.read()
            self.item.game_object.location = self.room
            self.item.holder_character_sheet = None
            self.item.save(update_fields=["holder_character_sheet"])
            second = self.read()
            assert "drop" in self.entries(first)
            assert "get" in self.entries(second)
            assert compose.call_count == 2
        MenuAccountThrottle.cache.clear()
        with override_settings(TARGET_MENU_ACCOUNT_RATE="1/min"):
            assert self.client.get(self.url()).status_code == 200
            assert self.client.get(self.url("objects", self.obj)).status_code == 429
            other_account = AccountFactory(is_staff=False)
            RosterTenureFactory(
                roster_entry=self.other_entry,
                player_data=PlayerDataFactory(account=other_account),
                start_date=timezone.now(),
                end_date=None,
            )
            other_client = APIClient()
            other_client.force_authenticate(user=other_account)
            assert (
                other_client.get(self.url("objects", self.obj, actor=self.other)).status_code == 200
            )

    def test_two_input_use_real_blend_and_stale_target(self):
        from actions.constants import TargetKind
        from world.consent.constants import ConsentMode
        from world.consent.factories import SocialConsentCategoryFactory
        from world.consent.models import SocialConsentCategory
        from world.forms.factories import CharacterFormFactory, CharacterFormValueFactory

        SocialConsentCategory.objects.filter(key="makeover").delete()
        SocialConsentCategoryFactory(key="makeover", default_mode=ConsentMode.EVERYONE)
        trait = FormTraitFactory(is_cosmetic=True)
        composite = FormTraitOptionFactory(trait=trait, requires_teaching=False)
        trait.composite_option = composite
        trait.save(update_fields=["composite_option"])
        option = FormTraitOptionFactory(trait=trait, requires_teaching=False)
        old = FormTraitOptionFactory(trait=trait, requires_teaching=False)
        form = CharacterFormFactory(character=self.other_sheet)
        CharacterFormValueFactory(form=form, trait=trait, option=old)
        source = self.make_item("Targeted cosmetic")
        source.template.is_consumable = True
        source.template.max_charges = 3
        source.template.on_use_pool = None
        source.template.on_use_target_kind = TargetKind.CHARACTER
        source.template.save()
        source.charges = 3
        source.save(update_fields=["charges"])
        ItemTemplateAppearanceEffect.objects.create(
            item_template=source.template, trait=trait, target_option=None
        )
        entry = self.entries(self.read(target=source))["use_item"]
        assert {row["name"] for row in entry["inputs"] if row["required"]} == {
            "use_target",
            "option_id",
        }
        candidate = next(
            row
            for row in entry["candidates"]
            if row["kwargs"]
            == {
                "use_target": {"kind": "objects", "target_id": self.other.pk},
                "option_id": option.pk,
            }
        )
        assert candidate["available"]
        assert self.other.key not in candidate["label"]
        assert not self.dispatch(entry).data["success"]
        assert source.charges == 3
        candidate = {
            **candidate,
            "kwargs": {**candidate["kwargs"], "blend": True, "descriptor": "silver filigree"},
        }
        response = self.dispatch(entry, candidate)
        assert response.status_code == 200, response.data
        assert response.data["success"], response.data
        assert source.charges == 2
        assert form.values.get(trait=trait).option == composite
        self.other.location = self.remote
        assert not self.dispatch(entry, candidate).data["success"]
        assert source.charges == 2

    def test_authored_real_dispatch_effect(self):
        from world.checks.constants import EffectTarget, EffectType
        from world.checks.factories import ConsequenceEffectFactory
        from world.checks.types import CheckResult

        _, template, approach, _, _ = self.authored_fixture()
        success = CheckOutcomeFactory(success_level=1)
        consequence = ConsequenceFactory(outcome_tier=success, character_loss=False)
        ChallengeTemplateConsequence.objects.create(
            challenge_template=template, consequence=consequence
        )
        lit = PropertyFactory()
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.ADD_PROPERTY,
            target=EffectTarget.TARGET,
            property=lit,
            property_value=1,
        )
        with patch(
            "world.mechanics.services._get_difficulty_indicator_for_check",
            return_value=DifficultyIndicator.MODERATE,
        ):
            entry = next(
                row
                for row in self.read("objects", self.obj)["entries"]
                if row["group"] == "authored"
            )
            check = CheckResult(
                check_type=approach.check_type,
                outcome=success,
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            )
            with patch("world.mechanics.challenge_resolution.perform_check", return_value=check):
                response = self.dispatch(entry)
        assert response.status_code == 200, response.data
        assert ObjectProperty.objects.filter(object=self.obj, property=lit).exists()
        assert ChallengeInstance.objects.filter(target_object=self.obj).exists()

    def test_visible_exit_blocker(self):
        from world.mechanics.constants import ChallengeType

        template = ChallengeTemplateFactory(challenge_type=ChallengeType.INHIBITOR)
        ChallengeInstance.objects.create(
            template=template,
            location=self.exit,
            target_object=self.exit,
            is_active=True,
            is_revealed=True,
        )
        entry = self.entries(self.read("exits", self.exit))["traverse_exit"]
        assert not entry["available"]
        assert entry["reasons"] == ["The way is blocked."]
        assert not self.dispatch(entry).data["success"]
        assert self.actor.location == self.room

    def test_explicit_serializer_query_free_private_projection(self):
        from rest_framework.exceptions import ValidationError

        from actions.target_menu import build_target_menu
        from actions.target_menu_serializers import MenuEntrySerializer, TargetMenuSerializer
        from actions.target_menu_types import MenuTargetKind, MenuTargetRequest

        payload = build_target_menu(
            self.actor, MenuTargetRequest(MenuTargetKind.ITEMS, self.item.pk)
        )
        payload["private_source"] = "PRIVATE"
        for row in payload["entries"]:
            row["private_source"] = "PRIVATE"
            for candidate in row["candidates"]:
                candidate["private_source"] = "PRIVATE"
        assert isinstance(TargetMenuSerializer().fields["entries"].child, MenuEntrySerializer)

        def no_query(execute, sql, params, many, context):
            raise AssertionError(sql)

        with connection.execute_wrapper(no_query):
            output = TargetMenuSerializer(payload).data
        assert "PRIVATE" not in json.dumps(output)
        payload["entries"][0]["kwargs"]["private_source"] = True
        with self.assertRaises(ValidationError):
            _ = TargetMenuSerializer(payload).data

    def test_raw_kwargs_exact_action_candidate_allowlists(self):
        from actions.target_menu import AUTHOR_ENTRY_CONTEXT
        from actions.target_menu_serializers import ENTRY_KWARG_KEYS, MenuKwargsSerializer

        target = {"kind": "items", "target_id": self.item.pk}
        for action in ENTRY_KWARG_KEYS:
            values = {} if action == AUTHOR_ENTRY_CONTEXT else {"menu_target": target}
            serializer = MenuKwargsSerializer(data=values, context={"action_key": action})
            assert serializer.is_valid(), serializer.errors
            assert dict(serializer.validated_data) == values
            invalid_keys = {
                "item",
                "item_id",
                "target",
                "owner_persona_id",
                "container_item_id",
                "recipient_persona_id",
                "unknown",
            }
            if action != "use_item":
                invalid_keys |= {"descriptor", "blend"}
            if action == AUTHOR_ENTRY_CONTEXT:
                invalid_keys.add("menu_target")
            for key in invalid_keys:
                serializer = MenuKwargsSerializer(
                    data={**values, key: object()}, context={"action_key": action}
                )
                assert not serializer.is_valid(), (action, key)
                assert key in serializer.errors, (action, key)
        for action, kind, values in (
            ("give", "recipient", {"recipient_persona_id": self.mask.pk}),
            ("put_in", "container", {"container_item_id": self.bag.pk}),
            ("use_item", "combination", {"option_id": 1}),
        ):
            context = {"action_key": action, "candidate_kind": kind}
            valid = MenuKwargsSerializer(data=values, context=context)
            assert valid.is_valid(), valid.errors
            invalid_keys = {
                "item",
                "item_id",
                "target",
                "owner_persona_id",
                "unknown",
                "menu_target",
            }
            if action != "use_item":
                invalid_keys |= {"descriptor", "blend", "use_target", "option_id"}
            invalid_keys |= {"recipient_persona_id", "container_item_id"} - set(values)
            for key in invalid_keys:
                serializer = MenuKwargsSerializer(data={**values, key: object()}, context=context)
                assert not serializer.is_valid(), (action, key)
                assert key in serializer.errors, (action, key)
        for key, value in (("descriptor", 1), ("blend", "false"), ("blend", 0)):
            serializer = MenuKwargsSerializer(data={key: value}, context={"action_key": "use_item"})
            assert not serializer.is_valid()
            assert key in serializer.errors
