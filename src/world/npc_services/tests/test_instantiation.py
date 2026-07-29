"""Tier-1 instantiation tests (#2827 phase 2)."""

from django.test import TestCase

from actions.registry import get_action
from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.npc_services.factories import FunctionaryFactory, NPCRoleFactory
from world.npc_services.instantiation import (
    generate_person_name,
    materialize_functionary,
    name_culture_for_room,
)
from world.npc_services.models import NameCulture, NameCultureEntry, NamePart
from world.roster.factories import FamilyFactory
from world.roster.models import RosterEntry
from world.roster.models.choices import RosterType


class NameCultureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.culture = NameCulture.objects.create(name="Umbran")
        NameCultureEntry.objects.create(culture=cls.culture, part=NamePart.GIVEN, value="Sella")
        NameCultureEntry.objects.create(culture=cls.culture, part=NamePart.SURNAME, value="Vane")

    def test_generate_uses_culture_pools(self):
        self.assertEqual(generate_person_name(self.culture), "Sella Vane")

    def test_family_overrides_surname(self):
        family = FamilyFactory(name="Velenosa")
        self.assertEqual(generate_person_name(self.culture, family=family), "Sella Velenosa")

    def test_no_culture_falls_back_to_placeholder(self):
        self.assertEqual(generate_person_name(None), "Sojourner")

    def test_global_default_culture_resolves_for_arealess_room(self):
        room = RoomProfileFactory()
        self.assertEqual(name_culture_for_room(room), self.culture)


class MaterializationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        culture = NameCulture.objects.create(name="Default Pool")
        NameCultureEntry.objects.create(culture=culture, part=NamePart.GIVEN, value="Marta")

    def test_materialize_mints_identity_and_shelves_it(self):
        functionary = FunctionaryFactory()
        persona = materialize_functionary(functionary)

        functionary.refresh_from_db()
        self.assertEqual(functionary.persona, persona)
        self.assertEqual(functionary.name_override, persona.name)
        self.assertIn("Marta", persona.name)
        entry = RosterEntry.objects.get(character_sheet=persona.character_sheet)
        self.assertEqual(entry.roster.roster_type, RosterType.NPC)

    def test_materialize_is_idempotent(self):
        functionary = FunctionaryFactory()
        first = materialize_functionary(functionary)
        self.assertEqual(materialize_functionary(functionary), first)

    def test_named_placement_keeps_its_authored_name(self):
        functionary = FunctionaryFactory(name_override="Old Marta")
        persona = materialize_functionary(functionary)
        self.assertEqual(persona.name, "Old Marta")


class EngagementHookTests(TestCase):
    """npc_start against a co-located faceless placement makes it real."""

    def test_npc_start_materializes_the_placement(self):
        NameCulture.objects.create(name="Hookville")
        role = NPCRoleFactory(name="Barmaid")
        room = RoomProfileFactory()
        functionary = FunctionaryFactory(role=role, room=room)
        actor = CharacterSheetFactory().character
        actor.db_location = room.objectdb
        actor.save()

        result = get_action("npc_start").run(actor, role_id=role.pk)
        self.assertTrue(result.success)
        functionary.refresh_from_db()
        self.assertIsNotNone(functionary.persona)
        self.assertIn(functionary.persona.name, result.message)
        # Rapport now flows durable: the session carries the NPC persona.
        self.assertEqual(result.data["session"].npc_persona, functionary.persona)
