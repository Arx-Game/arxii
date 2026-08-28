"""Catalog completeness: the authoring catalog must describe every action."""

from django.test import SimpleTestCase

from flows.catalog import FILTER_OPS, STEP_ACTION_SPECS, VariableNameRole, event_catalog
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
