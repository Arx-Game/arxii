from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CombatManeuver,
    DuelChallengeStatus,
    EncounterStatus,
    EncounterType,
    RiskLevel,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import select_npc_actions


class DuelEnumTests(TestCase):
    def test_duel_enum_members_exist(self):
        self.assertEqual(EncounterType.DUEL, "duel")
        self.assertEqual(CombatManeuver.YIELD, "yield")
        self.assertEqual(DuelChallengeStatus.PENDING, "pending")

    def test_is_lethal_derives_from_risk_level(self):
        lethal = CombatEncounterFactory(risk_level=RiskLevel.LETHAL)
        spar = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)
        self.assertTrue(lethal.is_lethal)
        self.assertFalse(spar.is_lethal)


class DuelWinnerFieldTests(TestCase):
    def test_fresh_encounter_has_no_duel_winner(self):
        enc = CombatEncounterFactory()
        self.assertIsNone(enc.duel_winner)

    def test_duel_winner_accepts_character_sheet(self):
        sheet = CharacterSheetFactory()
        enc = CombatEncounterFactory()
        enc.duel_winner = sheet
        enc.save(update_fields=["duel_winner"])
        enc.refresh_from_db()
        self.assertEqual(enc.duel_winner_id, sheet.pk)


class DuelMirrorOpponentTests(TestCase):
    def test_mirror_opponent_is_passive_and_links_participant(self):
        participant = CombatParticipantFactory()
        enc = participant.encounter
        enc.status = EncounterStatus.DECLARING
        enc.round_number = 1
        enc.save(update_fields=["status", "round_number"])
        mirror = CombatOpponentFactory(encounter=enc, mirrors_participant=participant)
        self.assertTrue(mirror.is_duel_mirror)
        actions = select_npc_actions(enc)
        self.assertNotIn(mirror.id, [a.opponent_id for a in actions])
