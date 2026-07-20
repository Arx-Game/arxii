"""Full pipeline proof for ambient reactions v2: model -> DSL compile -> grid-import-derived
Trigger -> real at_post_move -> delivery (#2471 v2).

Unlike the closed PR's version of this test (which hand-installed a Trigger before the
import automation existed), this drives the REAL grid-import path end to end — the Trigger
this test exercises is the one grid-import actually derives and installs, not a manually
constructed stand-in.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

from django.test import TestCase

from core_management.content_export import export_to_content_repo
from core_management.content_fixtures import load_world_content
from core_management.grid_export import export_grid_bundles
from core_management.tests._grid_fixtures import build_sample_grid
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.constants import LocationParentType
from world.narrative.constants import ConditionType
from world.narrative.factories import AmbientEmoteConditionFactory, AmbientEmoteLineFactory
from world.narrative.models import NarrativeMessageDelivery
from world.species.factories import SpeciesFactory


class AmbientReactionMovedIntegrationTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.grid = build_sample_grid()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        self.species = SpeciesFactory(name="Infernal")
        line = AmbientEmoteLineFactory(
            parent_type=LocationParentType.ROOM,
            room_profile=self.grid.taproom,
            area=None,
            bystander_body="A murmur runs through the taproom.",
            arriver_body="Eyes turn to you.",
        )
        AmbientEmoteConditionFactory(
            line=line, condition_type=ConditionType.SPECIES, species=self.species
        )

        export_to_content_repo(self.root)
        export_grid_bundles(self.root)
        load_world_content(self.root)

        from evennia_extensions.factories import CharacterFactory

        self.character = CharacterFactory()
        CharacterSheetFactory(character=self.character, species=self.species)

    def _place_in(self, room) -> None:
        self.character.db_location = room
        self.character.save(update_fields=["db_location"])

    def test_matching_species_delivers_via_real_derived_trigger(self) -> None:
        self._place_in(self.grid.taproom_obj)
        self.character.at_post_move(source_location=None)

        msgs = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=self.character.character_sheet
            ).values_list("message__body", flat=True)
        )
        self.assertEqual(msgs, ["Eyes turn to you."])

    def test_non_matching_species_is_silent(self) -> None:
        other_species = SpeciesFactory(name="Human")
        self.character.character_sheet.species = other_species
        self.character.character_sheet.save(update_fields=["species"])

        self._place_in(self.grid.taproom_obj)
        self.character.at_post_move(source_location=None)

        msgs = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=self.character.character_sheet
            )
        )
        self.assertEqual(msgs, [])
