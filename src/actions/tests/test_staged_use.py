"""Typed staged ordinary Use, real REST charges and authored redirects."""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from actions.base import Action
from actions.constants import TargetKind
from actions.definitions.items import UseItemAction
from evennia_extensions.factories import AccountFactory, ObjectDBFactory
from flows.scene_data_manager import SceneDataManager
from world.consent.constants import ConsentMode
from world.consent.factories import SocialConsentCategoryFactory
from world.consent.models import SocialConsentCategory
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.forms.models import CharacterKnownStyle, PersonaTraitDescriptor
from world.forms.services import learn_style
from world.items.exceptions import (
    BlendNotSupported,
    ItemNotAttuned,
    NoChargesRemaining,
    StyleNotKnown,
)
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemTemplateAppearanceEffect, OwnershipEvent
from world.items.services import usage
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.services import create_mask, set_active_persona


class StagedUseTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.remote = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        entry = RosterEntryFactory()
        self.sheet = entry.character_sheet
        self.actor = self.sheet.character
        self.actor.location = self.room
        self.account = AccountFactory(is_staff=False)
        RosterTenureFactory(
            roster_entry=entry, player_data=PlayerDataFactory(account=self.account), end_date=None
        )
        other = RosterEntryFactory()
        self.other_sheet = other.character_sheet
        self.other = self.other_sheet.character
        self.other.location = self.room
        RosterTenureFactory(roster_entry=other, end_date=None)
        SocialConsentCategory.objects.filter(key="makeover").delete()
        self.category = SocialConsentCategoryFactory(
            key="makeover", default_mode=ConsentMode.EVERYONE
        )
        self.trait = FormTraitFactory(is_cosmetic=True, composite_option=None)
        self.old = FormTraitOptionFactory(trait=self.trait, requires_teaching=False)
        self.option = FormTraitOptionFactory(trait=self.trait, requires_teaching=False)
        self.exotic = FormTraitOptionFactory(trait=self.trait, requires_teaching=True)
        self.composite = FormTraitOptionFactory(trait=self.trait, requires_teaching=False)
        self.template = ItemTemplateFactory(
            on_use_pool=None,
            is_consumable=True,
            max_charges=8,
            requires_attunement=False,
            on_use_target_kind=TargetKind.CHARACTER,
        )
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template, trait=self.trait, target_option=None
        )
        self.item = self.make_item(self.template)
        self.form = CharacterFormFactory(character=self.other_sheet)
        CharacterFormValueFactory(form=self.form, trait=self.trait, option=self.old)
        self.action = UseItemAction()
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def make_item(self, template, *, row_only=False, location=None):
        return ItemInstanceFactory(
            template=template,
            charges=8,
            quality_tier=None,
            holder_character_sheet=self.sheet,
            contained_in=None,
            game_object=None
            if row_only
            else ObjectDBFactory(
                db_typeclass_path="typeclasses.objects.Object",
                location=self.actor if location is None else location,
            ),
        )

    def values(self, *, source=None, target=True, option=True):
        result = {"menu_target": {"kind": "items", "target_id": (source or self.item).pk}}
        if target:
            result["use_target"] = {"kind": "objects", "target_id": self.other.pk}
        if option:
            result["option_id"] = self.option.pk
        return result

    def read(self, values, pending=frozenset()):
        return self.action.check_availability(
            self.actor, context={"kwargs": values}, pending_inputs=pending
        )

    def post(self, values):
        response = self.client.post(
            f"/api/actions/characters/{self.actor.pk}/dispatch/",
            {"ref": {"backend": "registry", "registry_key": "use_item"}, "kwargs": values},
            format="json",
        )
        assert response.status_code == 200, response.data
        return response.data

    def snapshot(self):
        return (
            self.item.charges,
            self.item.destroyed_at,
            tuple(OwnershipEvent.objects.order_by("pk")),
            (
                tuple(self.form.values.values_list("option_id", flat=True)),
                tuple(
                    PersonaTraitDescriptor.objects.order_by("pk").values_list(
                        "persona_id", "trait_id", "text"
                    )
                ),
            ),
        )

    def pure(self, callback):
        before = self.snapshot()
        with (
            CaptureQueriesContext(connection) as queries,
            patch("flows.emit.emit_event") as emit,
            patch.object(SceneDataManager, "initialize_state_for_object") as initialize,
            patch.object(usage, "_apply_on_use_pool") as effects,
        ):
            result = callback()
        emit.assert_not_called()
        initialize.assert_not_called()
        effects.assert_not_called()
        assert self.snapshot() == before
        for query in queries.captured_queries:
            sql = query["sql"].strip().upper()
            assert not sql.startswith(("INSERT", "UPDATE", "DELETE")), sql
            assert "FOR UPDATE" not in sql, sql
        return result

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

    def test_ac1_ac2_strict_wire_and_pending(self):
        bound = self.values(target=False, option=False)
        pending = frozenset({"use_target", "option_id"})
        assert self.pure(lambda: self.read(bound, pending)).available
        assert not self.read(bound).available
        for names, values in (
            (frozenset({"unknown"}), bound),
            (frozenset({"use_target"}), {**bound, "use_target": None}),
            (frozenset({"option_id"}), {**bound, "option_id": False}),
        ):
            with self.assertRaises(ValueError):
                self.read(values, names)
        invalid = []
        for key, bad_values in {
            "option_id": [None, True, "1", 0, [], {}],
            "descriptor": [True, 1, [], {}],
            "blend": [None, 1, "false", [], {}],
            "use_target": [
                None,
                True,
                self.other.pk,
                {},
                {"kind": "persona", "target_id": self.other.pk},
                {"kind": "objects", "target_id": True},
                {"kind": "objects", "target_id": str(self.other.pk)},
                {"kind": "objects", "target_id": self.other.pk, "owner_persona_id": 1},
            ],
        }.items():
            invalid.extend({**self.values(), key: value} for value in bad_values)
        invalid.extend(
            {**self.values(), key: value}
            for key, value in (
                ("target", self.other.pk),
                ("item", self.item.pk),
                ("item_instance_id", self.item.pk),
                ("target_persona_id", self.other_sheet.primary_persona.pk),
                ("pending_inputs", ["option_id"]),
            )
        )
        invalid.extend(
            {**self.values(), "menu_target": value}
            for value in (
                None,
                {"kind": "objects", "target_id": self.item.pk},
                {"kind": "items", "target_id": True},
            )
        )
        before = self.snapshot()
        for values in invalid:
            with self.subTest(values=values):
                assert not self.pure(lambda values=values: self.read(values)).available
                assert not self.post(values)["success"]
                assert self.snapshot() == before
        assert not self.post(bound)["success"]
        assert self.snapshot() == before

    def test_ac2_independent_bound_target_option_blend(self):
        missing_target = self.values(target=False)
        missing_target["option_id"] = self.exotic.pk
        assert (
            StyleNotKnown.user_message
            in self.read(missing_target, frozenset({"use_target"})).reasons
        )
        malformed_descriptor = {**missing_target, "descriptor": 1}
        reasons = self.read(malformed_descriptor, frozenset({"use_target"})).reasons
        assert "descriptor must be text." in reasons
        assert StyleNotKnown.user_message in reasons
        self.category.default_mode = ConsentMode.ALLOWLIST
        self.category.save(update_fields=["default_mode"])
        assert not self.read(self.values(option=False), frozenset({"option_id"})).available
        self.item.charges = 0
        self.item.save(update_fields=["charges"])
        bound = self.values(target=False, option=False)
        reasons = self.read(
            {**bound, "blend": True}, frozenset({"use_target", "option_id"})
        ).reasons
        assert NoChargesRemaining.user_message in reasons
        assert BlendNotSupported.user_message in reasons
        self.item.charges = 8
        self.item.save(update_fields=["charges"])
        self.template.requires_attunement = True
        self.template.save(update_fields=["requires_attunement"])
        assert (
            ItemNotAttuned.user_message
            in self.read(bound, frozenset({"use_target", "option_id"})).reasons
        )
        with patch.object(Action, "_dead_gate_reason", return_value="dead"):
            assert "dead" in self.read(bound, frozenset({"use_target", "option_id"})).reasons
        with (
            patch.object(Action, "_dead_gate_reason", return_value=""),
            patch.object(Action, "_offscreen_gate_reason", return_value="offscreen"),
        ):
            assert "offscreen" in self.read(bound, frozenset({"use_target", "option_id"})).reasons
        self.item.game_object.location = self.room
        assert not self.read(bound, frozenset({"use_target", "option_id"})).available

    def test_ac3_ac4_complete_combinations_masks_hidden_and_purity(self):
        mask = create_mask(self.other_sheet, name="Anonymous visitor")
        set_active_persona(self.other_sheet, mask)
        self.other.key = "Private underlying character key"
        hidden = RosterEntryFactory().character_sheet.character
        hidden.location = self.room
        self.conceal(hidden)
        rows = self.pure(
            lambda: self.action.use_candidates(
                self.actor, kwargs=self.values(target=False, option=False)
            )
        )
        target_ids = {row["use_target"]["target_id"] for row in rows}
        assert self.other.pk in target_ids
        assert hidden.pk not in target_ids
        assert "Private underlying character key" not in str(rows)
        from world.scenes.persona_display import (
            resolve_display_for_viewer,
            viewer_context_for_account,
        )

        personas, sheets = viewer_context_for_account(self.account)
        label, _ = resolve_display_for_viewer(
            mask, viewer_persona_ids=personas, viewer_sheet_ids=sheets, is_staff=False
        )
        assert {
            row["target_name"] for row in rows if row["use_target"]["target_id"] == self.other.pk
        } == {label}
        options = {self.old.pk, self.option.pk, self.exotic.pk, self.composite.pk}
        assert {(row["use_target"]["target_id"], row["option_id"]) for row in rows} == {
            (target_id, option) for target_id in target_ids for option in options
        }
        for row in rows:
            values = {
                **self.values(target=False, option=False),
                "use_target": row["use_target"],
                "option_id": row["option_id"],
            }
            checked = self.read(values)
            assert row["available"] == checked.available
            assert row["reasons"] == checked.reasons
        assert any(
            not row["available"] and StyleNotKnown.user_message in row["reasons"] for row in rows
        )
        for _index in range(33):
            FormTraitOptionFactory(trait=self.trait, requires_teaching=False)
        rows = self.action.use_candidates(
            self.actor, kwargs=self.values(target=False, option=False)
        )
        assert len(rows) == len(target_ids) * 37
        self.category.default_mode = ConsentMode.ALLOWLIST
        self.category.save(update_fields=["default_mode"])
        denied = self.action.use_candidates(
            self.actor, kwargs=self.values(target=True, option=False)
        )
        assert denied
        assert not any(row["available"] for row in denied)
        condition = self.conceal(self.other)
        assert self.action.use_candidates(self.actor, kwargs=self.values(option=False)) == ()
        assert not self.post(self.values())["success"]
        condition.delete()
        self.other.location = self.remote
        assert self.action.use_candidates(self.actor, kwargs=self.values(option=False)) == ()

    def test_ac1_ac3_item_room_unsupported_and_empty_dimensions(self):
        from actions.factories import ConsequencePoolFactory

        ordinary = ItemTemplateFactory(
            on_use_pool=ConsequencePoolFactory(),
            on_use_check_type=None,
            is_consumable=True,
            on_use_target_kind=TargetKind.ITEM,
        )
        source = self.make_item(ordinary)
        target = self.make_item(ordinary, location=self.room)
        row_only = self.make_item(ordinary, row_only=True)
        values = {"menu_target": {"kind": "items", "target_id": source.pk}}
        rows = self.action.use_candidates(self.actor, kwargs=values)
        assert any(row["use_target"] == {"kind": "items", "target_id": target.pk} for row in rows)
        assert all(row["use_target"]["target_id"] != row_only.pk for row in rows)
        assert all(row["option_id"] is None and row["option_name"] == "" for row in rows)
        assert (
            self.action.use_candidates(self.actor, kwargs={**values, "option_id": self.exotic.pk})
            == rows
        )
        assert self.post({**values, "use_target": {"kind": "items", "target_id": target.pk}})[
            "success"
        ]
        ordinary.on_use_target_kind = TargetKind.ROOM
        ordinary.save(update_fields=["on_use_target_kind"])
        rows = self.action.use_candidates(self.actor, kwargs=values)
        assert [row["use_target"] for row in rows] == [
            {"kind": "objects", "target_id": self.room.pk}
        ], rows
        assert self.post({**values, "use_target": rows[0]["use_target"]})["success"]
        ordinary.on_use_target_kind = TargetKind.PERSONA
        ordinary.save(update_fields=["on_use_target_kind"])
        assert not self.read(values, frozenset({"use_target"})).available
        assert self.action.use_candidates(self.actor, kwargs=values) == ()
        ordinary.on_use_target_kind = None
        ordinary.save(update_fields=["on_use_target_kind"])
        rows = self.action.use_candidates(self.actor, kwargs=values)
        assert len(rows) == 1
        assert rows[0]["use_target"] is None
        assert rows[0]["option_id"] is None
        assert self.post(values)["success"]
        assert not self.post(
            {**values, "use_target": {"kind": "objects", "target_id": self.actor.pk}}
        )["success"]
        self.trait.options.all().delete()
        assert (
            self.action.use_candidates(self.actor, kwargs=self.values(target=False, option=False))
            == ()
        )

    def test_ac4_ac5_real_cosmetic_rest_descriptor_blend_row_only(self):
        before = self.item.charges
        assert self.post({**self.values(), "descriptor": "  silver streaks  "})["success"]
        value = self.form.values.get(trait=self.trait)
        assert value.option == self.option
        assert (
            PersonaTraitDescriptor.objects.get(
                persona=self.other_sheet.primary_persona, trait=self.trait
            ).text
            == "silver streaks"
        )
        assert self.item.charges == before - 1
        assert self.post({**self.values(), "descriptor": "  "})["success"]
        assert not PersonaTraitDescriptor.objects.filter(
            persona=self.other_sheet.primary_persona, trait=self.trait
        ).exists()
        self.trait.composite_option = self.composite
        self.trait.save(update_fields=["composite_option"])
        assert self.post({**self.values(), "option_id": self.old.pk, "blend": True})["success"]
        blended = self.form.values.get(trait=self.trait)
        assert blended.option == self.composite
        assert [
            component.option for component in blended.components.order_by("sort_order", "pk")
        ] == [self.option, self.old]
        row = self.make_item(self.template, row_only=True)
        assert self.post(self.values(source=row))["success"]
        assert row.charges == 7
        foreign = self.make_item(self.template, row_only=True)
        foreign.holder_character_sheet = self.other_sheet
        foreign.save(update_fields=["holder_character_sheet"])
        assert not self.post(self.values(source=foreign))["success"]
        assert foreign.charges == 8
        self.template.on_use_target_kind = None
        self.template.save(update_fields=["on_use_target_kind"])
        CharacterFormFactory(character=self.sheet)
        effect = self.template.appearance_effects.first()
        effect.target_option = self.option
        effect.save(update_fields=["target_option"])
        assert self.post(self.values(target=False, option=False))["success"]
        assert not self.action.use_input_spec(
            self.actor, kwargs=self.values(target=False, option=False)
        )["required_inputs"]

    def test_room_use_current_concealed_detected_remote_and_actor_moved(self):
        from actions.factories import ConsequencePoolFactory
        from actions.prerequisites import CANNOT_SEE_MESSAGE, OnUseTargetPrerequisite
        from world.conditions.services import register_detection

        template = ItemTemplateFactory(
            on_use_pool=ConsequencePoolFactory(),
            on_use_check_type=None,
            is_consumable=True,
            on_use_target_kind=TargetKind.ROOM,
        )
        source = self.make_item(template)
        values = {
            "menu_target": {"kind": "items", "target_id": source.pk},
            "use_target": {"kind": "objects", "target_id": self.room.pk},
        }
        prerequisite = OnUseTargetPrerequisite()
        legacy = {"kwargs": {"item": source}}
        assert prerequisite.is_met(self.actor, None, legacy) == (False, "Use it on what?")
        assert prerequisite.is_met(self.actor, self.other, legacy) == (
            False,
            "That can only be used on a place.",
        )
        assert prerequisite.is_met(self.actor, self.remote, legacy) == (False, "They aren't here.")
        assert prerequisite.is_met(self.actor, self.room, legacy) == (True, "")
        assert self.pure(lambda: self.read(values)).available
        assert self.post(values)["success"]
        assert source.charges == 7
        condition = self.conceal(self.room)
        assert prerequisite.is_met(self.actor, self.room, legacy) == (False, CANNOT_SEE_MESSAGE)
        assert not self.pure(lambda: self.read(values)).available
        assert self.action.use_candidates(self.actor, kwargs=values) == ()
        assert not self.post(values)["success"]
        assert source.charges == 7
        register_detection(self.sheet, self.room)
        assert prerequisite.is_met(self.actor, self.room, legacy) == (True, "")
        assert self.pure(lambda: self.read(values)).available
        assert self.post(values)["success"]
        assert source.charges == 6
        remote_values = {**values, "use_target": {"kind": "objects", "target_id": self.remote.pk}}
        assert not self.read(remote_values).available
        assert not self.post(remote_values)["success"]
        self.actor.location = self.remote
        assert prerequisite.is_met(self.actor, self.room, legacy) == (False, "They aren't here.")
        assert not self.read(values).available
        assert not self.post(values)["success"]
        assert source.charges == 6
        self.actor.location = None
        assert prerequisite.is_met(self.actor, self.room, legacy) == (False, "They aren't here.")
        assert not self.read(values).available
        condition.delete()

    def test_real_rest_use_delivers_current_custom_item_label(self):
        self.item.game_object.key = "Raw item object key"
        for label in ("Silver styling kit", "Freshly renamed styling kit"):
            self.item.custom_name = label
            self.item.save(update_fields=["custom_name"])
            with patch.object(self.other, "msg") as delivered:
                result = self.post(self.values())
            assert result["success"]
            texts = str(delivered.call_args_list)
            assert label in texts
            assert "Raw item object key" not in texts
        assert self.item.charges == 6

    def test_ac5_inventory_rest_real_service_refusal_and_success(self):
        self.template.on_use_target_kind = None
        self.template.save(update_fields=["on_use_target_kind"])
        form = CharacterFormFactory(character=self.sheet)
        CharacterFormValueFactory(form=form, trait=self.trait, option=self.old)
        url = f"/api/items/inventory/{self.item.pk}/use/"
        assert self.client.post(url, {}, format="json").status_code == 400
        assert self.item.charges == 8
        response = self.client.post(url, {"option_id": self.option.pk}, format="json")
        assert response.status_code == 200
        assert response.data["charges_remaining"] == 7
        assert form.values.get(trait=self.trait).option == self.option

    def test_ac6_real_authored_effect_redirect_cancel_and_once(self):
        from flows.consts import FlowActionChoices

        replacement = RosterEntryFactory().character_sheet.character
        replacement.location = self.room
        form = CharacterFormFactory(character=replacement.character_sheet)
        CharacterFormValueFactory(form=form, trait=self.trait, option=self.old)
        for service in (False, True):
            trigger = self.trigger(
                FlowActionChoices.CALL_SERVICE_FUNCTION
                if service
                else FlowActionChoices.MODIFY_PAYLOAD,
                {"payload": "@payload", "object_id": replacement.pk}
                if service
                else {"field": "target", "op": "set", "value": replacement.pk},
                "flows.service_functions.actions.redirect_action_target" if service else "",
            )
            try:
                with patch(
                    "actions.definitions.items.emit_event",
                    wraps=__import__("flows.emit", fromlist=["emit_event"]).emit_event,
                ) as emit:
                    assert self.post(self.values())["success"]
                intents = [
                    call for call in emit.call_args_list if str(call.args[0]) == "action_intent"
                ]
                assert len(intents) == 1, emit.call_args_list
                assert form.values.get(trait=self.trait).option == self.option
                assert self.form.values.get(trait=self.trait).option == self.old
            finally:
                self.remove_trigger(trigger)
        for field, value in (
            ("target", True),
            ("target", self.remote.pk),
            ("use_target", {"kind": "objects", "target_id": True}),
            ("item_target", self.room.pk),
            ("item_target", True),
        ):
            trigger = self.trigger(
                FlowActionChoices.MODIFY_PAYLOAD, {"field": field, "op": "set", "value": value}
            )
            before = self.snapshot()
            try:
                assert not self.post(self.values())["success"]
                assert self.snapshot() == before
            finally:
                self.remove_trigger(trigger)
        replacement_item = self.make_item(self.template)
        trigger = self.trigger(
            FlowActionChoices.MODIFY_PAYLOAD,
            {"field": "item_target", "op": "set", "value": replacement_item.game_object.pk},
        )
        before = self.item.charges
        try:
            assert self.post(self.values())["success"]
            assert self.item.charges == before
            assert replacement_item.charges == 7
        finally:
            self.remove_trigger(trigger)
        trigger = self.trigger(FlowActionChoices.CANCEL_EVENT)
        before = self.snapshot()
        try:
            assert self.post(self.values())["message"] == "Something prevents you."
            assert self.snapshot() == before
        finally:
            self.remove_trigger(trigger)

    def test_ac6_enhancement_changes_are_revalidated(self):
        action = self.action
        original = action._apply_enhancements

        def alter(context, actor, enhancements):
            original(context, actor, enhancements)
            context.kwargs["use_target"] = {"kind": "objects", "target_id": self.remote.pk}

        before = self.snapshot()
        with patch.object(UseItemAction, "_apply_enhancements", side_effect=alter):
            assert not action.run(self.actor, **self.values()).success
        assert self.snapshot() == before

    def test_ac3_fixed_no_choice_candidates_ignore_supplied_option_dimension(self):
        effect = self.template.appearance_effects.first()
        effect.target_option = self.option
        effect.save(update_fields=["target_option"])
        values = self.values(target=False, option=False)
        baseline = self.pure(lambda: self.action.use_candidates(self.actor, kwargs=values))
        assert baseline
        target_ids = {row["use_target"]["target_id"] for row in baseline}
        assert len(baseline) == len(target_ids)
        assert all(row["option_id"] is None and row["option_name"] == "" for row in baseline)
        unrelated = FormTraitOptionFactory(trait=FormTraitFactory(is_cosmetic=True))
        nonexistent = max(self.exotic.pk, unrelated.pk) + 1000000
        for ignored in (self.exotic.pk, unrelated.pk, nonexistent):
            rows = self.pure(
                lambda ignored=ignored: self.action.use_candidates(
                    self.actor, kwargs={**values, "option_id": ignored}
                )
            )
            assert rows == baseline
        bound_target = self.values(option=False)
        rows = self.pure(lambda: self.action.use_candidates(self.actor, kwargs=bound_target))
        assert len(rows) == 1
        assert rows[0]["option_id"] is None
        assert rows[0]["use_target"] == bound_target["use_target"]

    def test_ac3_first_null_effect_controls_complete_option_product(self):
        fixed_trait = FormTraitFactory(is_cosmetic=True)
        fixed_option = FormTraitOptionFactory(trait=fixed_trait, requires_teaching=False)
        original = self.template.appearance_effects.first()
        original.target_option = self.option
        original.save(update_fields=["target_option"])
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template, trait=fixed_trait, target_option=fixed_option
        )
        first_trait = FormTraitFactory(is_cosmetic=True)
        second_trait = FormTraitFactory(is_cosmetic=True)
        first_options = [
            FormTraitOptionFactory(trait=first_trait, requires_teaching=False),
            FormTraitOptionFactory(trait=first_trait, requires_teaching=True),
        ]
        second_option = FormTraitOptionFactory(trait=second_trait, requires_teaching=False)
        first_open = ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template, trait=first_trait, target_option=None
        )
        ItemTemplateAppearanceEffect.objects.create(
            item_template=self.template, trait=second_trait, target_option=None
        )
        assert (
            self.template.appearance_effects.filter(target_option__isnull=True).first()
            == first_open
        )
        values = self.values(target=False, option=False)
        rows = self.pure(lambda: self.action.use_candidates(self.actor, kwargs=values))
        assert rows
        target_ids = {row["use_target"]["target_id"] for row in rows}
        assert len(rows) == len(target_ids) * len(first_options)
        assert {(row["use_target"]["target_id"], row["option_id"]) for row in rows} == {
            (target_id, option.pk) for target_id in target_ids for option in first_options
        }
        for row in rows:
            complete = {**values, "use_target": row["use_target"], "option_id": row["option_id"]}
            checked = self.read(complete)
            assert row["available"] == checked.available
            assert row["reasons"] == checked.reasons
        assert any(StyleNotKnown.user_message in row["reasons"] for row in rows)
        for excluded in (self.option.pk, fixed_option.pk, second_option.pk):
            assert (
                self.action.use_candidates(self.actor, kwargs={**values, "option_id": excluded})
                == ()
            )
        chosen = first_options[0]
        selected = self.pure(
            lambda: self.action.use_candidates(
                self.actor, kwargs={**values, "option_id": chosen.pk}
            )
        )
        assert len(selected) == len(target_ids)
        assert {(row["use_target"]["target_id"], row["option_id"]) for row in selected} == {
            (target_id, chosen.pk) for target_id in target_ids
        }
        assert (
            usage.validate_item_use_option(
                item_instance=self.item, user=self.actor, option_id=chosen.pk
            )
            == chosen
        )

    def test_ac5_fixed_execution_ignores_well_formed_option_and_empty_visible_candidates(self):
        effect = self.template.appearance_effects.first()
        effect.target_option = self.option
        effect.save(update_fields=["target_option"])
        values = self.values(option=False)
        assert self.read(values).available
        assert self.post({**values, "option_id": self.exotic.pk})["success"]
        assert self.form.values.get(trait=self.trait).option == self.option
        before = self.snapshot()
        assert not self.post({**values, "option_id": True})["success"]
        assert self.snapshot() == before
        from actions.factories import ConsequencePoolFactory

        ordinary = ItemTemplateFactory(
            on_use_pool=ConsequencePoolFactory(),
            on_use_check_type=None,
            on_use_target_kind=TargetKind.ITEM,
        )
        row = self.make_item(ordinary, row_only=True)
        self.item.game_object.location = self.remote
        assert (
            self.action.use_candidates(
                self.actor, kwargs=self.values(source=row, target=False, option=False)
            )
            == ()
        )

    def test_ac6_source_assertions_survive_redirect_and_invalid_enhancement(self):
        from flows.consts import FlowActionChoices

        replacement = self.make_item(self.template)
        values = self.values()
        values["menu_target"]["owner_persona_id"] = self.other_sheet.primary_persona.pk
        trigger = self.trigger(
            FlowActionChoices.MODIFY_PAYLOAD,
            {"field": "item_target", "op": "set", "value": replacement.game_object.pk},
        )
        before = self.snapshot()
        try:
            assert not self.post(values)["success"]
            assert self.snapshot() == before
            assert replacement.charges == 8
        finally:
            self.remove_trigger(trigger)
        original = self.action._apply_enhancements

        def alter(context, actor, enhancements):
            original(context, actor, enhancements)
            context.kwargs["menu_target"] = {"kind": "items", "target_id": replacement.pk}
            context.kwargs["option_id"] = True

        with patch.object(UseItemAction, "_apply_enhancements", side_effect=alter):
            assert not self.action.run(self.actor, **self.values()).success
        assert self.snapshot() == before
        assert replacement.charges == 8

    def test_ac7_locked_gate_repeats_option_and_consent(self):
        learn_style(self.sheet, self.exotic, taught_by_label="Teacher")
        values = {**self.values(), "option_id": self.exotic.pk}
        original = usage._run_pre_charge_gates
        for change in ("knowledge", "consent", "membership"):
            before = self.snapshot()

            def change_then_gate(change=change, **kwargs):
                if change == "knowledge":
                    CharacterKnownStyle.objects.filter(
                        character_sheet=self.sheet, option=self.exotic
                    ).delete()
                elif change == "consent":
                    self.category.default_mode = ConsentMode.ALLOWLIST
                    self.category.save(update_fields=["default_mode"])
                else:
                    self.exotic.trait = FormTraitFactory(is_cosmetic=True)
                    self.exotic.save(update_fields=["trait"])
                return original(**kwargs)

            with patch.object(usage, "_run_pre_charge_gates", side_effect=change_then_gate):
                assert not self.post(values)["success"]
            assert self.snapshot() == before
            self.category.default_mode = ConsentMode.EVERYONE
            self.category.save(update_fields=["default_mode"])
            self.exotic.trait = self.trait
            self.exotic.save(update_fields=["trait"])
            learn_style(self.sheet, self.exotic, taught_by_label="Teacher")

    def _change_use_state(self, change, hidden):
        if change == "consent":
            self.category.default_mode = ConsentMode.ALLOWLIST
            self.category.save(update_fields=["default_mode"])
        elif change == "knowledge":
            CharacterKnownStyle.objects.filter(
                character_sheet=self.sheet, option=self.exotic
            ).delete()
        elif change == "holding":
            self.item.game_object.location = self.room
        elif change == "concealment":
            hidden.append(self.conceal(self.other))
        elif change == "depletion":
            self.item.charges = 0
            self.item.save(update_fields=["charges"])
        elif change == "attunement":
            self.template.requires_attunement = True
            self.template.save(update_fields=["requires_attunement"])
        else:
            self.other.location = self.remote

    def test_ac7_stale_after_gate_and_after_initialization(self):
        learn_style(self.sheet, self.exotic, taught_by_label="Teacher")
        values = {**self.values(), "option_id": self.exotic.pk}
        assert self.read(values).available
        for stage in ("gate", "initialize"):
            for change in (
                "consent",
                "knowledge",
                "holding",
                "concealment",
                "presence",
                "depletion",
                "attunement",
            ):
                with self.subTest(stage=stage, change=change):
                    hidden = []

                    def mutate(change=change, hidden=hidden):
                        self._change_use_state(change, hidden)

                    before = self.snapshot()
                    if stage == "gate":
                        with patch.object(
                            UseItemAction,
                            "_charge_costs",
                            side_effect=lambda _actor, mutate=mutate: mutate(),
                        ):
                            assert not self.post(values)["success"]
                    else:
                        initialize = SceneDataManager.initialize_state_for_object
                        calls = []

                        def initialize_and_change(
                            manager, obj, initialize=initialize, calls=calls, mutate=mutate
                        ):
                            state = initialize(manager, obj)
                            if obj == self.actor:
                                calls.append(obj)
                                if len(calls) == 2:
                                    mutate()
                            return state

                        with patch.object(
                            SceneDataManager,
                            "initialize_state_for_object",
                            new=initialize_and_change,
                        ):
                            assert not self.post(values)["success"]
                    after = self.snapshot()
                    assert after[1:] == before[1:]
                    assert self.item.charges == (0 if change == "depletion" else before[0])
                    self.item.charges = 8
                    self.item.save(update_fields=["charges"])
                    self.template.requires_attunement = False
                    self.template.save(update_fields=["requires_attunement"])
                    self.category.default_mode = ConsentMode.EVERYONE
                    self.category.save(update_fields=["default_mode"])
                    self.item.game_object.location = self.actor
                    self.other.location = self.room
                    for condition in hidden:
                        condition.delete()
                    learn_style(self.sheet, self.exotic, taught_by_label="Teacher")
