"""Journey for the "Your resonances" panel (#5124): what is kindled, how strongly and why.

The scene sidebar and the combat rail read it through the API; telnet ``resonances`` prints
the same list. A condition the character bears that matches a resonance's feeling kindles it.
Kindling only strengthens her magic and suggests a resonance beside an act she took (#5327):
the panel lists no amount and nothing here pays.
"""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.covenants.perks.constants import Situation
from world.magic.factories import (
    AffinityFactory,
    CharacterResonanceFactory,
    KindledStrengthTierFactory,
    KindlingSituationFactory,
    ResonanceFactory,
    ThreadFactory,
    TrickleAccrualFactory,
)
from world.magic.models import KindledStrengthTier
from world.mechanics.factories import PropertyFactory
from world.missions.factories import (
    MissionInstanceFactory,
    MissionParticipantFactory,
    MissionThemeFactory,
)

URL = "/api/magic/kindled-resonances/"


class SeeingWhatIsKindled(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        KindledStrengthTier.objects.all().delete()
        for rank, severity, name in ((1, 1, "Faint"), (2, 3, "Strong"), (3, 5, "Blazing")):
            KindledStrengthTierFactory(rank=rank, name=name, min_severity=severity)
        self.room = self.make_room("The Hollow")
        self.mira = self.make_player("Mira", room=self.room)
        self.sheet = self.mira.sheet_data
        feeling = PropertyFactory()
        self.fury = ResonanceFactory(
            name="Fury", affinity=AffinityFactory(name="Primal"), feeling=feeling
        )
        self.wonder = ResonanceFactory(name="Wonder", affinity=self.fury.affinity)
        for resonance in (self.fury, self.wonder):
            CharacterResonanceFactory(character_sheet=self.sheet, resonance=resonance)
        KindlingSituationFactory(
            resonance=self.fury, situation=Situation.OWN_FEELING, strength=None
        )
        rage = ConditionTemplateFactory(name="Rage")
        rage.properties.add(feeling)
        ConditionInstanceFactory(target=self.mira, condition=rage, severity=5)

    def test_the_api_lists_each_resonance_with_its_strength_word_and_reasons(self) -> None:
        response = self.api(self.account_of(self.mira)).get(URL, {"character_sheet": self.sheet.pk})
        self.assertEqual(response.status_code, 200)
        rows = {row["name"]: row for row in response.json()["results"]}
        self.assertEqual(set(rows), {"Fury", "Wonder"})
        self.assertEqual(
            rows["Fury"],
            {
                "id": self.fury.pk,
                "name": "Fury",
                "affinity_name": "Primal",
                "kindled": True,
                "strength_name": "Blazing",
                "reasons": ["You carry Rage"],
                "waiting_trickle": 0,
            },
        )
        self.assertFalse(rows["Wonder"]["kindled"])
        self.assertIsNone(rows["Wonder"]["strength_name"])
        self.assertEqual(rows["Wonder"]["reasons"], [])

    def test_telnet_resonances_prints_the_same_list(self) -> None:
        # #5308: what her days piled up waits for her anima ritual, on both surfaces.
        TrickleAccrualFactory(character_sheet=self.sheet, resonance=self.wonder, amount=3)
        TrickleAccrualFactory(character_sheet=self.sheet, resonance=self.wonder, amount=4)
        told = self.telnet(self.mira, "resonances")
        self.assertEqual(
            told.splitlines(),
            [
                "|wFury|n (Primal) - Kindled, blazing",
                "  You carry Rage",
                "|wWonder|n (Primal) - Not kindled",
                "  7 waiting for your anima ritual",
            ],
        )
        response = self.api(self.account_of(self.mira)).get(URL, {"character_sheet": self.sheet.pk})
        rows = {row["name"]: row for row in response.json()["results"]}
        self.assertEqual(rows["Wonder"]["waiting_trickle"], 7)
        self.assertEqual(rows["Fury"]["waiting_trickle"], 0)

    def test_the_api_shows_her_resonances_to_her_and_no_one_else(self) -> None:
        other = self.make_player("Hobb", room=self.room)
        response = self.api(self.account_of(other)).get(URL, {"character_sheet": self.sheet.pk})
        self.assertEqual(response.json()["results"], [])
        self.assertEqual(self.api(self.account_of(self.mira)).get(URL).status_code, 400)


class SeeingWhatTheSituationKindles(JourneyCase):
    """What only a live fight or mission kindles reads the same on the web and on telnet."""

    def setUp(self) -> None:
        super().setUp()
        KindledStrengthTier.objects.all().delete()
        for rank, name in ((1, "Faint"), (2, "Strong"), (3, "Blazing")):
            KindledStrengthTierFactory(rank=rank, name=name, min_bond_tier=rank)
        self.room = self.make_room("The Hollow")
        self.mira = self.make_player("Mira", room=self.room)
        self.sheet = self.mira.sheet_data
        self.fury = ResonanceFactory(name="Fury", affinity=AffinityFactory(name="Primal"))
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.fury)

    def _both(self) -> tuple[dict, list[str]]:
        response = self.api(self.account_of(self.mira)).get(URL, {"character_sheet": self.sheet.pk})
        rows = {row["name"]: row for row in response.json()["results"]}
        return rows, self.telnet(self.mira, "resonances").splitlines()

    def test_an_opponent_her_thread_is_tied_to_kindles_it_only_in_the_fight(self) -> None:
        overseer = CharacterSheetFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=self.fury, as_track_thread=True)
        side = thread.target_relationship
        side.target = overseer
        side.tier = 2
        side.save()
        KindlingSituationFactory(
            resonance=self.fury,
            situation=Situation.THREAD_ANCHOR_PRESENT,
            enemies_only=True,
            strength=None,
        )
        rows, lines = self._both()
        self.assertFalse(rows["Fury"]["kindled"])
        self.assertEqual(lines, ["|wFury|n (Primal) - Not kindled"])

        encounter = CombatEncounterFactory()
        CombatParticipantFactory(encounter=encounter, character_sheet=self.sheet)
        CombatOpponentFactory(encounter=encounter, persona=overseer.primary_persona)
        reason = f"{overseer.character.db_key} stands against you here"
        rows, lines = self._both()
        self.assertEqual(rows["Fury"]["strength_name"], "Strong")
        self.assertEqual(rows["Fury"]["reasons"], [reason])
        self.assertEqual(lines, ["|wFury|n (Primal) - Kindled, strong", f"  {reason}"])

    def test_her_active_mission_kindles_by_its_theme(self) -> None:
        theme = MissionThemeFactory(player_text="This mission is about people held captive.")
        KindlingSituationFactory(
            resonance=self.fury, situation=Situation.MISSION_THEME, mission_theme=theme, strength=1
        )
        mission = MissionInstanceFactory()
        mission.template.themes.add(theme)
        MissionParticipantFactory(instance=mission, character=self.sheet)
        rows, lines = self._both()
        self.assertEqual(rows["Fury"]["strength_name"], "Faint")
        self.assertEqual(
            lines,
            [
                "|wFury|n (Primal) - Kindled, faint",
                "  This mission is about people held captive.",
            ],
        )
