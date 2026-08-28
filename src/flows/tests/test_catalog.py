"""Catalog completeness: the authoring catalog must describe every action."""

from django.test import SimpleTestCase

from flows.catalog import (
    FILTER_OPS,
    STEP_ACTION_SPECS,
    VariableNameRole,
    event_catalog,
    service_function_catalog,
)
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.models.flows import CONDITIONAL_ACTIONS


class StepActionCatalogTests(SimpleTestCase):
    def test_every_action_has_a_spec(self):
        self.assertEqual(set(STEP_ACTION_SPECS), set(FlowActionChoices.values))

    def test_conditional_flags_match_runtime(self):
        conditional_values = {str(a.value) for a in CONDITIONAL_ACTIONS}
        flagged = {a for a, spec in STEP_ACTION_SPECS.items() if spec.is_conditional}
        self.assertEqual(flagged, conditional_values)

    def test_spec_action_keys_match_their_action_field(self):
        for action, spec in STEP_ACTION_SPECS.items():
            self.assertEqual(action, spec.action)

    def test_roles_are_valid(self):
        roles = {r.value for r in VariableNameRole}
        for spec in STEP_ACTION_SPECS.values():
            self.assertIn(spec.variable_name_role, roles)

    def test_call_service_function_allows_extra_params(self):
        spec = STEP_ACTION_SPECS[FlowActionChoices.CALL_SERVICE_FUNCTION.value]
        self.assertTrue(spec.allows_extra_params)
        self.assertEqual(spec.variable_name_role, VariableNameRole.SERVICE_FUNCTION_NAME.value)

    def test_modify_payload_op_choices(self):
        spec = STEP_ACTION_SPECS[FlowActionChoices.MODIFY_PAYLOAD.value]
        op = next(p for p in spec.params if p.name == "op")
        self.assertEqual(set(op.choices), {"set", "multiply", "add", "min", "max"})


class EventCatalogTests(SimpleTestCase):
    def test_every_event_name_listed_and_no_vestigial_enums(self):
        names = {e["name"] for e in event_catalog()}
        self.assertEqual(names, set(EventName.values))
        self.assertNotIn("EXAMINE", names)  # vestigial EventType member

    def test_move_pre_depart_has_payload_fields(self):
        entry = next(e for e in event_catalog() if e["name"] == "move_pre_depart")
        field_names = {f["name"] for f in entry["payload_fields"]}
        self.assertIn("destination", field_names)

    def test_filter_ops_exported(self):
        self.assertIn("==", FILTER_OPS)
        self.assertIn("has_capability", FILTER_OPS)


class ServiceFunctionCatalogTests(SimpleTestCase):
    def test_catalog_includes_registered_world_verbs(self):
        # world/apps.py ready() registration ran at test bootstrap
        names = {e["name"] for e in service_function_catalog()}
        self.assertIn("advance_condition_stage", names)
        self.assertIn("redirect_move", names)

    def test_params_have_type_tags(self):
        entry = next(e for e in service_function_catalog() if e["name"] == "redirect_move")
        params = {p["name"]: p["type"] for p in entry["params"]}
        # redirect_move(*, payload: object, room_id: object, **kwargs: object) — both
        # keyword-only params are annotated `object`, not a concrete int/bool/str/float,
        # so both fall back to the catalog's "json" tag. Verified against the actual
        # signature in src/flows/service_functions/movement.py before asserting here.
        self.assertEqual(params.get("room_id"), "json")
        self.assertEqual(params.get("payload"), "json")

    def test_entries_sorted_by_name(self):
        names = [e["name"] for e in service_function_catalog()]
        self.assertEqual(names, sorted(names))

    def test_builtin_param_tags_survive_a_sibling_unresolvable_annotation(self):
        # flow_apply_condition(*, target: ObjectDB, condition_name: str) — the
        # module uses `from __future__ import annotations` and only imports
        # ObjectDB under TYPE_CHECKING, so `typing.get_type_hints` raises for
        # the whole function. condition_name's plain-string "str" annotation
        # must still tag "str" rather than being dragged down to "json" by
        # the unresolvable `target` param on the same function.
        entry = next(e for e in service_function_catalog() if e["name"] == "flow_apply_condition")
        params = {p["name"]: p["type"] for p in entry["params"]}
        self.assertEqual(params.get("condition_name"), "str")
