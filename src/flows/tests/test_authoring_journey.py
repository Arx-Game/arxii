"""End-to-end journey (#3417 task 8): the ADR-0242 redirect idiom, authored via the API.

``test_authored_movement_redirection.py`` hand-builds a working authored movement
redirect (#3416) using factories directly against ``FlowDefinition``,
``FlowStepDefinition``, ``TriggerDefinition``, and ``Trigger``. This test proves the
same mechanic is reachable by a staff author who only ever calls the flows
authoring API (#3417 tasks 2/4/6) - no factory, no direct model access for the
authored rows themselves.

The move goes through a real ``Exit`` (rather than a bare ``move_to(room)`` call
like the hand-built test) so the assertion is unambiguous: the exit's own
``destination`` is a decoy room the trigger never sends anyone to, and arrival at
the *redirect* room instead is proof the authored flow - not the exit - won.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices

FLOWS_URL = "/api/flows/flows/"
TRIGGER_DEFINITIONS_URL = "/api/flows/trigger-definitions/"
TRIGGERS_URL = "/api/flows/triggers/"


def _room(key: str) -> ObjectDB:
    return ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")


class ApiAuthoredRedirectJourneyTests(TestCase):
    """Author the whole redirect idiom through the flows authoring API, then run it."""

    def setUp(self) -> None:
        self.client = APIClient()
        staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=staff)

        self.origin = _room("JourneyOrigin")
        self.decoy = _room("JourneyDecoy")
        self.redirect_target = _room("JourneyRedirectTarget")

        self.exit_obj = ObjectDBFactory(
            db_key="journey-gate", db_typeclass_path="typeclasses.exits.Exit"
        )
        self.exit_obj.location = self.origin
        self.exit_obj.destination = self.decoy
        self.exit_obj.save()

    def _create_flow(self) -> int:
        payload = {
            "name": "ApiAuthoredRedirectFlow",
            "description": "root call_service_function redirect_move",
            "steps": [
                {
                    "client_id": "root",
                    "parent_client_id": None,
                    "action": FlowActionChoices.CALL_SERVICE_FUNCTION,
                    "variable_name": "redirect_move",
                    "parameters": {
                        "payload": "@payload",
                        "room_id": self.redirect_target.pk,
                    },
                },
            ],
        }

        response = self.client.post(FLOWS_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data["id"]

    def _create_trigger_definition(self, flow_id: int) -> int:
        payload = {
            "name": "ApiAuthoredRedirectTriggerDefinition",
            "event_name": EventName.MOVE_PRE_DEPART,
            "flow_definition": flow_id,
            "priority": 0,
        }

        response = self.client.post(TRIGGER_DEFINITIONS_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data["id"]

    def _install_trigger(self, trigger_definition_id: int) -> int:
        payload = {
            "trigger_definition": trigger_definition_id,
            "obj": self.origin.pk,
        }

        response = self.client.post(TRIGGERS_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return response.data["id"]

    def test_api_authored_redirect_executes_end_to_end(self) -> None:
        """Every row (flow, step, trigger definition, trigger) is API-created.

        The character aims at the exit whose real destination is the decoy room,
        but the authored redirect wins: arrival is at the redirect room instead.
        """
        flow_id = self._create_flow()
        trigger_definition_id = self._create_trigger_definition(flow_id)
        self._install_trigger(trigger_definition_id)

        char = CharacterFactory()
        char.location = self.origin

        char.move_to(self.exit_obj, quiet=True)

        self.assertEqual(
            char.location.pk,
            self.redirect_target.pk,
            "Expected the API-authored flow to redirect the move to the target room",
        )
        self.assertNotEqual(
            char.location.pk,
            self.decoy.pk,
            "The exit's own destination must never win once the redirect fires",
        )
