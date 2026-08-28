"""Tests for the flows authoring API (#3417 task 4): catalog + FlowDefinition CRUD."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from flows.consts import FlowActionChoices
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from flows.models import FlowDefinition, FlowStepDefinition
from world.gm.factories import GMProfileFactory

CATALOG_URL = "/api/flows/catalog/"
FLOWS_URL = "/api/flows/flows/"


def _flow_detail_url(pk):
    return f"{FLOWS_URL}{pk}/"


class CatalogEndpointTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def test_staff_gets_catalog(self):
        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)

        response = self.client.get(CATALOG_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_actions = {value for value, _label in FlowActionChoices.choices}
        actual_actions = {entry["action"] for entry in response.data["actions"]}
        self.assertEqual(actual_actions, expected_actions)
        self.assertIn("events", response.data)
        self.assertIn("service_functions", response.data)
        self.assertIn("filter_ops", response.data)
        self.assertIn("variable_name_roles", response.data)

    def test_player_denied(self):
        player = AccountFactory()
        self.client.force_authenticate(user=player)

        response = self.client.get(CATALOG_URL)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_denied(self):
        response = self.client.get(CATALOG_URL)

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class FlowDefinitionApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=self.staff)

    def test_create_flow_with_step_tree(self):
        payload = {
            "name": "TestFlowWithTree",
            "description": "root -> child -> grandchild",
            "steps": [
                {
                    "client_id": "root",
                    "parent_client_id": None,
                    "action": FlowActionChoices.CALL_SERVICE_FUNCTION,
                    "variable_name": "some_service_fn",
                    "parameters": {},
                },
                {
                    "client_id": "child",
                    "parent_client_id": "root",
                    "action": FlowActionChoices.EVALUATE_EQUALS,
                    "variable_name": "some_flow_var",
                    "parameters": {"value": "10"},
                },
                {
                    "client_id": "grandchild",
                    "parent_client_id": "child",
                    "action": FlowActionChoices.CANCEL_EVENT,
                    "parameters": {},
                },
            ],
        }

        response = self.client.post(FLOWS_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        flow = FlowDefinition.objects.get(name="TestFlowWithTree")
        steps = list(flow.steps.order_by("pk"))
        self.assertEqual(len(steps), 3)
        root, child, grandchild = steps
        self.assertIsNone(root.parent)
        self.assertEqual(child.parent_id, root.pk)
        self.assertEqual(grandchild.parent_id, child.pk)
        self.assertEqual(root.action, FlowActionChoices.CALL_SERVICE_FUNCTION)
        self.assertEqual(child.action, FlowActionChoices.EVALUATE_EQUALS)
        self.assertEqual(grandchild.action, FlowActionChoices.CANCEL_EVENT)

        # Retrieve should also report the same depth-first authored order.
        retrieve_response = self.client.get(_flow_detail_url(flow.pk))
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        returned_ids = [entry["id"] for entry in retrieve_response.data["steps"]]
        self.assertEqual(returned_ids, [root.pk, child.pk, grandchild.pk])

    def test_create_flow_with_zero_steps(self):
        payload = {"name": "EmptyFlow", "description": "", "steps": []}

        response = self.client.post(FLOWS_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        flow = FlowDefinition.objects.get(name="EmptyFlow")
        self.assertEqual(flow.steps.count(), 0)

    def test_two_roots_rejected(self):
        payload = {
            "name": "TwoRootFlow",
            "steps": [
                {
                    "client_id": "a",
                    "parent_client_id": None,
                    "action": FlowActionChoices.CANCEL_EVENT,
                    "parameters": {},
                },
                {
                    "client_id": "b",
                    "parent_client_id": None,
                    "action": FlowActionChoices.CANCEL_EVENT,
                    "parameters": {},
                },
            ],
        }

        response = self.client.post(FLOWS_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("root", str(response.data).lower())

    def test_missing_required_param_rejected(self):
        payload = {
            "name": "MissingParamFlow",
            "steps": [
                {
                    "client_id": "a",
                    "parent_client_id": None,
                    "action": FlowActionChoices.EVALUATE_EQUALS,
                    "variable_name": "some_flow_var",
                    "parameters": {},
                },
            ],
        }

        response = self.client.post(FLOWS_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_replaces_tree(self):
        flow = FlowDefinitionFactory(name="ReplaceMeFlow")
        old_step = FlowStepDefinitionFactory(
            flow=flow, action=FlowActionChoices.CANCEL_EVENT, parameters={}
        )
        old_step_pk = old_step.pk

        payload = {
            "name": "ReplaceMeFlow",
            "description": "replaced",
            "steps": [
                {
                    "client_id": "new-root",
                    "parent_client_id": None,
                    "action": FlowActionChoices.CANCEL_EVENT,
                    "parameters": {},
                },
            ],
        }

        response = self.client.put(_flow_detail_url(flow.pk), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(FlowStepDefinition.objects.filter(pk=old_step_pk).exists())
        remaining_steps = list(FlowStepDefinition.objects.filter(flow=flow))
        self.assertEqual(len(remaining_steps), 1)
        self.assertIsNone(remaining_steps[0].parent)

    def test_gm_can_read_but_not_write(self):
        gm_profile = GMProfileFactory()
        gm_account = gm_profile.account
        self.client.force_authenticate(user=gm_account)
        flow = FlowDefinitionFactory()

        list_response = self.client.get(FLOWS_URL)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)

        retrieve_response = self.client.get(_flow_detail_url(flow.pk))
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)

        write_response = self.client.post(
            FLOWS_URL,
            {"name": "GmCannotWrite", "steps": []},
            format="json",
        )
        self.assertEqual(write_response.status_code, status.HTTP_403_FORBIDDEN)
