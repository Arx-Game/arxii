"""Journeys for a masked fighter on the battle roster (#4802).

Hobb and Ada are enlisted on one side of a battle. Hobb's own face carries a portrait.
Ada reads the battle over REST:

- Before the mask, she reads "Hobb" and his portrait.
- Once Hobb masks himself ("persona mask a hooded man"), she reads the mask's name and
  no portrait, because a bare mask has none and never shows the face behind it.
- Once the mask has a portrait of its own, she reads that portrait.

Expected values come from the ruling: the roster shows the face a fighter presents,
never the PRIMARY face behind a mask.
"""

from __future__ import annotations

import json

from django.test import tag
from evennia.objects.models import ObjectDB

from integration_tests.harness import JourneyCase
from world.battles.factories import BattleFactory, BattleSideFactory
from world.battles.services import enlist_participant
from world.conditions.thumbnail_services import BUILTIN_FACE_PLACEHOLDER_URL
from world.roster.factories import MediaFactory
from world.scenes.constants import PersonaType
from world.scenes.models import Persona


class AMaskedFighterOnTheBattleRoster(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        field = self.make_room("The Field")
        self.hobb = self.make_player("Hobb", room=field)
        self.ada = self.make_player("Ada", room=field)
        self.battle = BattleFactory()
        side = BattleSideFactory(battle=self.battle)
        rows = {
            fighter.key: enlist_participant(
                battle=self.battle, character_sheet=fighter.sheet_data, side=side
            )
            for fighter in (self.hobb, self.ada)
        }
        self.hobbs_row = rows["Hobb"]
        self.face = MediaFactory()
        primary = self.hobb.sheet_data.primary_persona
        primary.thumbnail = self.face
        primary.save(update_fields=["thumbnail"])

    def hobb_as_ada_reads_him(self) -> dict[str, object]:
        response = self.api(self.account_of(self.ada)).get(f"/api/battles/{self.battle.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        (row,) = (row for row in response.json()["participants"] if row["id"] == self.hobbs_row.pk)
        return row["persona"]

    def test_ada_reads_the_mask_never_hobbs_name_or_face(self) -> None:
        persona = self.hobb_as_ada_reads_him()
        self.assertEqual(
            (persona["name"], persona["thumbnail_media_url"]), ("Hobb", self.face.cloudinary_url)
        )

        told = self.telnet(self.hobb, "persona mask a hooded man")

        persona = self.hobb_as_ada_reads_him()
        # A bare mask shows the placeholder portrait (#4889), never the true face.
        self.assertEqual(
            (persona["name"], persona["thumbnail_media_url"]),
            ("a hooded man", BUILTIN_FACE_PLACEHOLDER_URL),
        )
        self.assertNotIn(self.face.cloudinary_url, str(persona), told)

        hood = MediaFactory()
        mask = Persona.objects.get(
            character_sheet=self.hobb.sheet_data, persona_type=PersonaType.TEMPORARY
        )
        mask.thumbnail = hood
        mask.save(update_fields=["thumbnail"])

        persona = self.hobb_as_ada_reads_him()
        self.assertEqual(persona["thumbnail_media_url"], hood.cloudinary_url)


class AMaskedFighterIsNotNamedByASheetId(JourneyCase):
    """Hobb fights in a mask; Ada, a stranger, reads the battle the way her browser does.

    The roster already shows Hobb as the mask. It must not also hand Ada his character
    sheet id, which names the character behind the mask. Each player's own browser still
    finds the player's own row, which is how the action panel knows where to act.
    """

    def setUp(self) -> None:
        super().setUp()
        field = self.make_room("The Field")
        self.hobb = self.make_player("Hobb", room=field)
        self.ada = self.make_player("Ada", room=field)
        self.battle = BattleFactory()
        side = BattleSideFactory(battle=self.battle)
        self.rows = {
            fighter.key: enlist_participant(
                battle=self.battle, character_sheet=fighter.sheet_data, side=side
            )
            for fighter in (self.hobb, self.ada)
        }
        self.telnet(self.hobb, "persona mask a hooded man")

    def roster_as(self, player: ObjectDB) -> list[dict[str, object]]:
        response = self.api(self.account_of(player)).get(f"/api/battles/{self.battle.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["participants"]

    @tag("regression")
    def test_regression_a_stranger_gets_no_sheet_id_for_the_masked_fighter(self) -> None:
        """Regression for #5290. Ada's roster carries no character sheet id for Hobb."""
        roster = self.roster_as(self.ada)

        (hobbs_row,) = (row for row in roster if row["id"] == self.rows["Hobb"].pk)
        self.assertEqual(hobbs_row["persona"]["name"], "a hooded man", roster)
        self.assertNotIn("character_sheet_id", hobbs_row)
        self.assertNotIn("character_sheet_id", json.dumps(roster))

    @tag("regression")
    def test_regression_each_player_still_finds_their_own_row(self) -> None:
        """Regression for #5290. Each browser marks exactly the viewer's own row."""
        for viewer in (self.hobb, self.ada):
            with self.subTest(viewer=viewer.key):
                roster = self.roster_as(viewer)
                mine = [row["id"] for row in roster if row["is_mine"]]
                self.assertEqual(mine, [self.rows[viewer.key].pk], roster)
