"""Tests for ``CharmAssetAction``'s NPC-only guard (#4091 task 12 fix round 2).

``CharmedByActorPrerequisite`` refuses a player character carrying the actor's
own charm -- including an OFFLINE one, where ``db_account`` alone reads
identically to an NPC (Evennia's ``unpuppet_object`` clears it the instant
nobody is actively connected). The canonical test is an active
``RosterTenure`` instead (``world.roster.services.activity.is_player_character``);
a bare ``RosterEntry`` doesn't count, since major NPCs are rostered too.
"""

from __future__ import annotations

from django.test import TestCase

from actions.registry import get_action
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class CharmAssetOfflinePCGuardTests(TestCase):
    """``retain`` (``charm_asset``) refuses an offline PC carrying the actor's charm."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        self.wren = ObjectDBFactory(
            db_key="Wren",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        CharacterSheetFactory(character=self.wren)

    def test_offline_pc_with_active_tenure_is_refused_as_not_an_npc(self) -> None:
        entry = RosterEntryFactory()
        pc_char = entry.character_sheet.character
        pc_char.location = self.room
        pc_char.save()
        RosterTenureFactory(roster_entry=entry)
        self.assertIsNone(pc_char.db_account)
        pc_persona = entry.character_sheet.primary_persona
        charm = ConditionTemplateFactory(
            name="Retain Offline PC Charm",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=CheckTypeFactory(name="Retain Offline PC Break"),
        )
        ConditionInstanceFactory(
            target=pc_char, condition=charm, source_character=self.wren, severity=4
        )

        result = get_action("charm_asset").run(
            actor=self.wren, target_persona_id=pc_persona.pk, role_context="informant"
        )

        self.assertFalse(result.success)
        self.assertIn("will of their own", result.message)
