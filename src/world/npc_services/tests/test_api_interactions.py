"""Tests for the player-facing InteractionViewSet.

Drives the start/resolve/end flow through HTTP. Session state lives in
``request.session``; the viewset rehydrates an ``InteractionSession`` on
each call. Tests monkey-patch ``InteractionViewSet._puppet_character`` to
return a sheet-bearing Character (Evennia's ``Account.puppet`` is a
property tied to live Sessions which we don't spin up in unit tests).
"""

from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    PermitOfferDetailsFactory,
)
from world.npc_services.views import InteractionViewSet

START = "/api/npc-services/interactions/start/"
RESOLVE = "/api/npc-services/interactions/resolve/"
END = "/api/npc-services/interactions/end/"


def _pc():
    """Account + Character with sheet (auto-PRIMARY persona) ready for interactions."""
    account = AccountFactory(username="player-1")
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    return account, character


def _patch_puppet(character):
    """Replace InteractionViewSet._puppet_character with a stub returning ``character``."""
    return patch.object(
        InteractionViewSet,
        "_puppet_character",
        lambda _self, _request: character,
    )


class StartInteractionTests(TestCase):
    def setUp(self) -> None:
        self.account, self.character = _pc()
        self.role = NPCRoleFactory(name="builders-guild-clerk")
        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def test_start_creates_session_state(self) -> None:
        offer = NPCServiceOfferFactory(role=self.role, label="apply-permit")
        PermitOfferDetailsFactory(offer=offer)
        with _patch_puppet(self.character):
            response = self.client.post(START, {"role_id": self.role.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["role_id"], self.role.pk)
        self.assertEqual(response.data["current_rapport"], 0)
        self.assertFalse(response.data["closed"])
        labels = {o["label"] for o in response.data["available_offers"]}
        self.assertIn("apply-permit", labels)

    def test_start_with_in_flight_session_returns_409(self) -> None:
        with _patch_puppet(self.character):
            self.client.post(START, {"role_id": self.role.pk}, format="json")
            response = self.client.post(START, {"role_id": self.role.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.data)

    def test_start_unknown_role_404s(self) -> None:
        with _patch_puppet(self.character):
            response = self.client.post(START, {"role_id": 999999}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)


class ResolveOfferTests(TestCase):
    def setUp(self) -> None:
        from world.buildings.factories import BuildingKindFactory
        from world.buildings.seeds import ensure_building_permit_template

        ensure_building_permit_template()
        kind = BuildingKindFactory(name="api-test-kind")
        self.account, self.character = _pc()
        self.role = NPCRoleFactory(name="role-resolve")
        self.offer = NPCServiceOfferFactory(role=self.role, label="permit", is_final=True)
        PermitOfferDetailsFactory(offer=self.offer, building_kind=kind)
        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def test_resolve_final_action_closes_session(self) -> None:
        with _patch_puppet(self.character):
            self.client.post(START, {"role_id": self.role.pk}, format="json")
            response = self.client.post(RESOLVE, {"offer_id": self.offer.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["closed"])
        self.assertEqual(response.data["available_offers"], [])
        self.assertIn("permit", response.data["last_result_message"].lower())

    def test_resolve_without_in_flight_returns_404(self) -> None:
        with _patch_puppet(self.character):
            response = self.client.post(RESOLVE, {"offer_id": self.offer.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_resolve_ineligible_offer_returns_400(self) -> None:
        # Offer gated on a distinction the PC doesn't have.
        gated = NPCServiceOfferFactory(
            role=self.role,
            label="gated",
            eligibility_rule={"leaf": "has_distinction", "params": {"slug": "unobtainable"}},
        )
        PermitOfferDetailsFactory(offer=gated)
        with _patch_puppet(self.character):
            self.client.post(START, {"role_id": self.role.pk}, format="json")
            response = self.client.post(RESOLVE, {"offer_id": gated.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)


class EndInteractionTests(TestCase):
    def setUp(self) -> None:
        self.account, self.character = _pc()
        self.role = NPCRoleFactory(name="role-end")
        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def test_end_marks_closed_and_clears_session(self) -> None:
        with _patch_puppet(self.character):
            self.client.post(START, {"role_id": self.role.pk}, format="json")
            response = self.client.post(END, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["closed"])
        # A subsequent start should now succeed (the in-flight session was cleared).
        with _patch_puppet(self.character):
            again = self.client.post(START, {"role_id": self.role.pk}, format="json")
        self.assertEqual(again.status_code, status.HTTP_201_CREATED)

    def test_end_without_in_flight_returns_404(self) -> None:
        with _patch_puppet(self.character):
            response = self.client.post(END, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)


class AuthRequiredTests(TestCase):
    def test_anonymous_blocked(self) -> None:
        client = APIClient()
        response = client.post(START, {"role_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class PuppetInvariantTests(TestCase):
    # The "no-puppet" case raises a ValidationError in `_puppet_character`
    # and would surface as 400 in real production traffic, but the test
    # scaffolding can't exercise it — accessing `Account.puppet` on an
    # AccountFactory-created account triggers Evennia's cmdset loader
    # which depends on a live SESSION_HANDLER. We document the path here
    # and rely on _patch_puppet to test the rest of the lifecycle.

    def test_puppet_without_sheet_returns_500(self) -> None:
        # Per character_sheets/CLAUDE.md every played character has a
        # CharacterSheet + PRIMARY persona. A puppeted character without
        # one is a programmer error — persona_for_character raises
        # MissingPrimaryPersonaError, which DRF's custom exception handler
        # surfaces as a 500. The test asserts that the request does NOT
        # silently succeed; 500 is the correct shape for an invariant
        # breach (4xx would hide a real bug).
        account = AccountFactory(username="player-no-sheet")
        bare_character = CharacterFactory()  # no CharacterSheetFactory call
        role = NPCRoleFactory(name="role-no-sheet")
        offer = NPCServiceOfferFactory(role=role, label="permit")
        PermitOfferDetailsFactory(offer=offer)
        client = APIClient()
        client.force_authenticate(account)
        with _patch_puppet(bare_character):
            response = client.post(START, {"role_id": role.pk}, format="json")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
