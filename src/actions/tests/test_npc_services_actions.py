"""Tests for the NPC-service registry Actions (#1493)."""

from django.test import TestCase

from actions.definitions.npc_services import (
    end_npc_interaction,
    resolve_npc_offer,
    start_npc_interaction,
)
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    PermitOfferDetailsFactory,
)
from world.npc_services.services import start_interaction


def _pc():
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    return character


class StartNPCInteractionActionTests(TestCase):
    def test_start_returns_session(self):
        character = _pc()
        role = NPCRoleFactory()
        NPCServiceOfferFactory(role=role, label="menu", eligibility_rule={})

        result = start_npc_interaction.run(actor=character, role_id=role.pk)

        self.assertTrue(result.success)
        self.assertIn("session", result.data)
        self.assertEqual(result.data["session"].role.pk, role.pk)

    def test_start_missing_role_fails(self):
        character = _pc()
        result = start_npc_interaction.run(actor=character, role_id=999999)
        self.assertFalse(result.success)


class ResolveNPCOfferActionTests(TestCase):
    def test_resolve_final_offer_closes_session(self):
        from world.buildings.factories import BuildingKindFactory
        from world.buildings.seeds import ensure_building_permit_template

        ensure_building_permit_template()
        kind = BuildingKindFactory(name="test-kind")
        character = _pc()
        role = NPCRoleFactory()
        offer = NPCServiceOfferFactory(role=role, label="permit", is_final=True)
        PermitOfferDetailsFactory(offer=offer, building_kind=kind)
        session = start_interaction(
            role=role,
            persona=character.sheet_data.primary_persona,
            character=character,
        )

        result = resolve_npc_offer.run(actor=character, session=session, offer_id=offer.pk)

        self.assertTrue(result.success)
        self.assertTrue(result.data["session"].closed)

    def test_resolve_without_session_fails(self):
        character = _pc()
        result = resolve_npc_offer.run(actor=character, session=None, offer_id=1)
        self.assertFalse(result.success)


class EndNPCInteractionActionTests(TestCase):
    def test_end_closes_session(self):
        character = _pc()
        role = NPCRoleFactory()
        session = start_interaction(
            role=role,
            persona=character.sheet_data.primary_persona,
            character=character,
        )

        result = end_npc_interaction.run(actor=character, session=session)

        self.assertTrue(result.success)
        self.assertTrue(session.closed)

    def test_end_without_session_fails(self):
        character = _pc()
        result = end_npc_interaction.run(actor=character, session=None)
        self.assertFalse(result.success)
