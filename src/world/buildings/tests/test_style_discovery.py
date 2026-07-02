"""Research-discoverable architectural styles (#1469).

The throwback tier: non-default styles gate on codex knowledge, the
clue→RESEARCH pipeline grants that knowledge, and an owned home building's
style adds base prestige. Fixtures live in setUp (never setUpTestData —
Evennia objects can't survive Django's per-test deepcopy).
"""

from django.test import TestCase, tag
from evennia.objects.models import ObjectDB

from actions.registry import get_action
from evennia_extensions.factories import CharacterFactory
from evennia_extensions.models import RoomProfile
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.buildings.factories import BuildingFactory
from world.buildings.models import ArchitecturalStyle
from world.buildings.polish_services import recompute_persona_prestige_from_dwellings
from world.buildings.seeds import ensure_architectural_styles
from world.buildings.services import can_build_style
from world.character_sheets.factories import CharacterSheetFactory
from world.clues.models import Clue
from world.clues.research import resolve_research, start_research_project
from world.codex.constants import CodexKnowledgeStatus
from world.codex.models import CharacterCodexKnowledge
from world.locations.constants import HolderType, LocationParentType
from world.locations.models import LocationOwnership
from world.locations.services import assign_room_tenant, set_primary_home
from world.roster.factories import RosterEntryFactory
from world.traits.factories import CheckOutcomeFactory

THROWBACK = "Antique Imperial PLACEHOLDER"
DEFAULT_STYLE = "Vernacular Timberframe PLACEHOLDER"


def _room_in(area, *, name="A Room"):
    room = ObjectDB.objects.create(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    RoomProfile.objects.update_or_create(objectdb=room, defaults={"area": area})
    return room


@tag("postgres")  # ownership cascade walks the areas_areaclosure materialized view
class StyleDiscoveryBase(TestCase):
    def setUp(self) -> None:
        ensure_architectural_styles()
        self.default_style = ArchitecturalStyle.objects.get(name=DEFAULT_STYLE)
        self.throwback = ArchitecturalStyle.objects.get(name=THROWBACK)

        self.actor = CharacterFactory()
        sheet = CharacterSheetFactory(character=self.actor)
        RosterEntryFactory(character_sheet=sheet)
        self.persona = sheet.primary_persona

        area = AreaFactory(level=AreaLevel.BUILDING)
        self.building = BuildingFactory(area=area, space_budget=100)
        LocationOwnership.objects.create(
            parent_type=LocationParentType.AREA,
            area=area,
            holder_type=HolderType.PERSONA,
            holder_persona=self.persona,
        )
        self.entry = _room_in(area, name="Entry Hall")
        self.building.entry_room = self.entry.room_profile
        self.building.save(update_fields=["entry_room"])
        self.actor.db_location = self.entry
        self.actor.save(update_fields=["db_location"])

    def _learn_throwback(self) -> None:
        """Run the real discovery pipeline: research the clue to completion."""
        clue = Clue.objects.get(name=f"Fragments of the {THROWBACK}")
        project = start_research_project(clue, self.persona, threshold_target=5)
        from world.clues.research import contribute_research

        contribute_research(project, self.persona, CheckOutcomeFactory(success_level=5))
        resolve_research(project, CheckOutcomeFactory(success_level=1))


class SeedTests(StyleDiscoveryBase):
    def test_seed_is_idempotent_and_wires_the_pipeline(self) -> None:
        ensure_architectural_styles()  # second call — no dupes
        self.assertEqual(ArchitecturalStyle.objects.filter(name__endswith="PLACEHOLDER").count(), 4)
        self.assertFalse(self.throwback.is_default)
        self.assertIsNotNone(self.throwback.codex_subject)
        self.assertGreater(self.throwback.prestige_bonus, 0)
        clue = Clue.objects.get(name=f"Fragments of the {THROWBACK}")
        self.assertEqual(clue.target_codex_entry.subject, self.throwback.codex_subject)


class CanBuildStyleTests(StyleDiscoveryBase):
    def test_default_style_is_open(self) -> None:
        self.assertTrue(can_build_style(self.persona, self.default_style))

    def test_throwback_needs_knowledge(self) -> None:
        self.assertFalse(can_build_style(self.persona, self.throwback))

    def test_research_unlocks_the_throwback(self) -> None:
        self._learn_throwback()
        self.assertTrue(
            CharacterCodexKnowledge.objects.filter(
                roster_entry=self.persona.character_sheet.roster_entry,
                entry__subject=self.throwback.codex_subject,
                status=CodexKnowledgeStatus.KNOWN,
            ).exists()
        )
        self.assertTrue(can_build_style(self.persona, self.throwback))

    def test_inactive_style_is_never_buildable(self) -> None:
        self.throwback.is_active = False
        self.throwback.save(update_fields=["is_active"])
        self._learn_throwback()
        self.assertFalse(can_build_style(self.persona, self.throwback))


class SetBuildingStyleActionTests(StyleDiscoveryBase):
    def test_owner_sets_a_default_style(self) -> None:
        result = get_action("set_building_style").run(actor=self.actor, style=DEFAULT_STYLE)
        self.assertTrue(result.success, result.message)
        self.building.refresh_from_db()
        self.assertEqual(self.building.architectural_style, self.default_style)

    def test_throwback_refused_until_learned(self) -> None:
        result = get_action("set_building_style").run(actor=self.actor, style=THROWBACK)
        self.assertFalse(result.success)
        self.assertIn("haven't learned", result.message)

        self._learn_throwback()
        result = get_action("set_building_style").run(actor=self.actor, style=THROWBACK)
        self.assertTrue(result.success, result.message)
        self.building.refresh_from_db()
        self.assertEqual(self.building.architectural_style, self.throwback)

    def test_room_id_anchor_works(self) -> None:
        elsewhere = AreaFactory(level=AreaLevel.WARD)
        street = _room_in(elsewhere, name="Open Street")
        self.actor.db_location = street
        self.actor.save(update_fields=["db_location"])
        result = get_action("set_building_style").run(
            actor=self.actor, room_id=self.entry.pk, style=DEFAULT_STYLE
        )
        self.assertTrue(result.success, result.message)

    def test_non_owner_refused(self) -> None:
        stranger = CharacterFactory()
        CharacterSheetFactory(character=stranger)
        stranger.db_location = self.entry
        stranger.save(update_fields=["db_location"])
        result = get_action("set_building_style").run(actor=stranger, style=DEFAULT_STYLE)
        self.assertFalse(result.success)


class StylePrestigeTests(StyleDiscoveryBase):
    def test_owned_home_building_style_adds_prestige(self) -> None:
        self.building.owner_persona = self.persona
        self.building.architectural_style = self.throwback
        self.building.save(update_fields=["owner_persona", "architectural_style"])
        assign_room_tenant(persona=self.persona, room=self.entry, tenant_persona=self.persona)
        set_primary_home(persona=self.persona, room=self.entry)

        total = recompute_persona_prestige_from_dwellings(self.persona)
        self.assertEqual(total, self.throwback.prestige_bonus)

    def test_unowned_home_building_style_adds_nothing(self) -> None:
        other_sheet = CharacterSheetFactory()
        self.building.owner_persona = other_sheet.primary_persona
        self.building.architectural_style = self.throwback
        self.building.save(update_fields=["owner_persona", "architectural_style"])
        assign_room_tenant(persona=self.persona, room=self.entry, tenant_persona=self.persona)
        set_primary_home(persona=self.persona, room=self.entry)

        total = recompute_persona_prestige_from_dwellings(self.persona)
        self.assertEqual(total, 0)
