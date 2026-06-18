from django.db import IntegrityError
from django.test import TestCase, tag

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
    DuelChallengeFactory,
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


class DuelChallengeModelTests(TestCase):
    def test_default_status_is_pending(self):
        challenge = DuelChallengeFactory()
        self.assertEqual(challenge.status, DuelChallengeStatus.PENDING)

    def test_resolved_at_and_resulting_encounter_default_to_null(self):
        challenge = DuelChallengeFactory()
        self.assertIsNone(challenge.resolved_at)
        self.assertIsNone(challenge.resulting_encounter)

    def test_created_at_is_set(self):
        challenge = DuelChallengeFactory()
        self.assertIsNotNone(challenge.created_at)

    def test_challenger_and_challenged_related_names(self):
        challenger = CharacterSheetFactory()
        challenged = CharacterSheetFactory()
        challenge = DuelChallengeFactory(
            challenger_sheet=challenger,
            challenged_sheet=challenged,
        )
        self.assertIn(challenge, list(challenger.duel_challenges_issued.all()))
        self.assertIn(challenge, list(challenged.duel_challenges_received.all()))

    def test_resulting_encounter_related_name(self):
        encounter = CombatEncounterFactory()
        challenge = DuelChallengeFactory(resulting_encounter=encounter)
        self.assertEqual(encounter.duel_challenge.get(), challenge)

    @tag("postgres")
    def test_one_pending_challenge_per_pair(self):
        c = DuelChallengeFactory()
        with self.assertRaises(IntegrityError):
            DuelChallengeFactory(
                challenger_sheet=c.challenger_sheet,
                challenged_sheet=c.challenged_sheet,
            )

    def test_non_pending_allows_second_row(self):
        """A resolved challenge should not block a new PENDING one."""
        from world.combat.models import DuelChallenge

        c = DuelChallengeFactory(status=DuelChallengeStatus.DECLINED)
        # A second challenge between the same pair in PENDING status must succeed.
        new = DuelChallengeFactory(
            challenger_sheet=c.challenger_sheet,
            challenged_sheet=c.challenged_sheet,
        )
        self.assertEqual(new.status, DuelChallengeStatus.PENDING)
        self.assertEqual(
            DuelChallenge.objects.filter(
                challenger_sheet=c.challenger_sheet,
                challenged_sheet=c.challenged_sheet,
            ).count(),
            2,
        )
