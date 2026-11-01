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

from integration_tests.harness import JourneyCase
from world.battles.factories import BattleFactory, BattleSideFactory
from world.battles.services import enlist_participant
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
        for fighter in (self.hobb, self.ada):
            enlist_participant(battle=self.battle, character_sheet=fighter.sheet_data, side=side)
        self.face = MediaFactory()
        primary = self.hobb.sheet_data.primary_persona
        primary.thumbnail = self.face
        primary.save(update_fields=["thumbnail"])

    def hobb_as_ada_reads_him(self) -> dict[str, object]:
        response = self.api(self.account_of(self.ada)).get(f"/api/battles/{self.battle.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        (row,) = (
            row
            for row in response.json()["participants"]
            if row["character_sheet_id"] == self.hobb.sheet_data.pk
        )
        return row["persona"]

    def test_ada_reads_the_mask_never_hobbs_name_or_face(self) -> None:
        persona = self.hobb_as_ada_reads_him()
        self.assertEqual(
            (persona["name"], persona["thumbnail_media_url"]), ("Hobb", self.face.cloudinary_url)
        )

        told = self.telnet(self.hobb, "persona mask a hooded man")

        persona = self.hobb_as_ada_reads_him()
        self.assertEqual((persona["name"], persona["thumbnail_media_url"]), ("a hooded man", None))
        self.assertNotIn(self.face.cloudinary_url, str(persona), told)

        hood = MediaFactory()
        mask = Persona.objects.get(
            character_sheet=self.hobb.sheet_data, persona_type=PersonaType.TEMPORARY
        )
        mask.thumbnail = hood
        mask.save(update_fields=["thumbnail"])

        persona = self.hobb_as_ada_reads_him()
        self.assertEqual(persona["thumbnail_media_url"], hood.cloudinary_url)
