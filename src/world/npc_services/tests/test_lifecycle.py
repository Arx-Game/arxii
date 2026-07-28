"""Ladder lifecycle tests (#2827 phase 5)."""

from django.test import TestCase

from world.assets.factories import NPCAssetFactory
from world.npc_services.factories import FunctionaryFactory
from world.npc_services.instantiation import materialize_functionary
from world.npc_services.lifecycle import (
    demote_to_instantiated,
    graduate_to_roster,
    promote_to_standing,
    standing_candidates,
)
from world.npc_services.models import Functionary
from world.roster.models import RosterEntry
from world.roster.models.choices import RosterType


class StandingLadderTests(TestCase):
    def _materialized(self):
        functionary = FunctionaryFactory()
        persona = materialize_functionary(functionary)
        return functionary, persona

    def test_promote_places_the_body_and_retires_the_slot(self):
        functionary, persona = self._materialized()
        room = functionary.room
        character = promote_to_standing(persona, room)
        self.assertEqual(character.location, room.objectdb)
        self.assertFalse(Functionary.objects.filter(pk=functionary.pk, is_active=True).exists())

    def test_demote_melts_back_into_the_crowd(self):
        functionary, persona = self._materialized()
        room = functionary.room
        promote_to_standing(persona, room)
        placement = demote_to_instantiated(persona, role=functionary.role, room=room)
        character = persona.character_sheet.character
        character.refresh_from_db()
        self.assertIsNone(character.location)
        self.assertTrue(placement.is_active)
        self.assertEqual(placement.persona, persona)
        self.assertEqual(placement.name_override, persona.name)

    def test_candidates_require_attachments(self):
        _, persona = self._materialized()
        self.assertNotIn(persona, standing_candidates())
        NPCAssetFactory(asset_persona=persona)
        NPCAssetFactory(asset_persona=persona)
        self.assertIn(persona, standing_candidates())


class GraduationTests(TestCase):
    def test_graduation_moves_the_shelf_entry_to_available(self):
        functionary = FunctionaryFactory()
        persona = materialize_functionary(functionary)
        sheet = persona.character_sheet
        shelf = RosterEntry.objects.get(character_sheet=sheet)
        self.assertEqual(shelf.roster.roster_type, RosterType.NPC)

        entry = graduate_to_roster(sheet)
        self.assertEqual(entry.pk, shelf.pk)
        self.assertEqual(entry.roster.roster_type, RosterType.AVAILABLE)
        self.assertEqual(entry.previous_roster.roster_type, RosterType.NPC)
        # The door actually opens: the entry is claimable.
        self.assertIn(entry, RosterEntry.objects.available_characters())

    def test_graduation_without_shelf_entry_creates_one(self):
        from world.character_sheets.factories import CharacterSheetFactory

        sheet = CharacterSheetFactory()
        RosterEntry.objects.filter(character_sheet=sheet).delete()
        entry = graduate_to_roster(sheet)
        self.assertEqual(entry.roster.roster_type, RosterType.AVAILABLE)
