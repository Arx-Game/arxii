"""Tests for duel state serializer fields (Task 13).

Covers:
- EncounterDetailSerializer exposes encounter_type, is_lethal, duel_winner.
- A duel-mirror CombatOpponent serializes mirrors_participant_id so the UI
  can render the other duelist's identity.
- DuelChallengeSerializer serializes the pending-challenge inbox.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    DuelChallengeStatus,
    EncounterType,
    RiskLevel,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    DuelChallengeFactory,
    PvpDuelFactory,
)
from world.combat.serializers import (
    DuelChallengeSerializer,
    EncounterDetailSerializer,
    OpponentSerializer,
)


class EncounterDetailDuelFieldsTests(TestCase):
    """EncounterDetailSerializer exposes encounter_type, is_lethal, duel_winner."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def _serialize(self, encounter: object) -> dict:
        # Set up participants_cached / opponents_cached so the serializer
        # does not fall back to DB queries (mirrors how the viewset works).
        if not hasattr(encounter, "participants_cached"):
            encounter.participants_cached = list(encounter.participants.all())
        if not hasattr(encounter, "opponents_cached"):
            encounter.opponents_cached = list(encounter.opponents.all())
        return EncounterDetailSerializer(encounter, context={}).data

    def test_encounter_type_exposed(self) -> None:
        enc = CombatEncounterFactory(encounter_type=EncounterType.DUEL)
        data = self._serialize(enc)
        self.assertEqual(data["encounter_type"], EncounterType.DUEL)

    def test_is_lethal_false_for_moderate(self) -> None:
        enc = CombatEncounterFactory(risk_level=RiskLevel.MODERATE)
        data = self._serialize(enc)
        self.assertFalse(data["is_lethal"])

    def test_is_lethal_true_for_lethal(self) -> None:
        enc = CombatEncounterFactory(risk_level=RiskLevel.LETHAL)
        data = self._serialize(enc)
        self.assertTrue(data["is_lethal"])

    def test_duel_winner_null_when_ongoing(self) -> None:
        enc = CombatEncounterFactory(encounter_type=EncounterType.DUEL)
        data = self._serialize(enc)
        self.assertIsNone(data["duel_winner"])

    def test_duel_winner_exposes_id_and_name(self) -> None:
        winner_sheet = CharacterSheetFactory()
        enc = CombatEncounterFactory(
            encounter_type=EncounterType.DUEL,
            duel_winner=winner_sheet,
        )
        data = self._serialize(enc)
        dw = data["duel_winner"]
        self.assertIsNotNone(dw)
        self.assertEqual(dw["id"], winner_sheet.pk)
        # character.db_key is the character's display name.
        self.assertEqual(dw["name"], winner_sheet.character.db_key)


class PvpDuelEncounterSerializerTests(TestCase):
    """Serialize a real PvP duel encounter from PvpDuelFactory.

    Asserts is_lethal=False, mirror opponents carry the duelists' identities,
    and duel_winner starts null.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        self.encounter = PvpDuelFactory.create()

    def _serialize(self) -> dict:
        enc = self.encounter
        if not hasattr(enc, "participants_cached"):
            enc.participants_cached = list(
                enc.participants.select_related(
                    "character_sheet__character",
                    "covenant_role",
                ).all()
            )
        if not hasattr(enc, "opponents_cached"):
            enc.opponents_cached = list(
                enc.opponents.select_related(
                    "mirrors_participant__character_sheet__character",
                ).all()
            )
        return EncounterDetailSerializer(enc, context={}).data

    def test_is_lethal_false(self) -> None:
        data = self._serialize()
        self.assertFalse(data["is_lethal"])

    def test_duel_winner_null(self) -> None:
        data = self._serialize()
        self.assertIsNone(data["duel_winner"])

    def test_mirror_opponents_carry_duelist_identity(self) -> None:
        """Each mirror opponent exposes mirrors_participant_id to the UI."""
        data = self._serialize()
        opponents = data["opponents"]
        mirror_opponents = [o for o in opponents if o["mirrors_participant_id"] is not None]
        # PvP duel creates two mirror opponents, one per duelist.
        self.assertEqual(len(mirror_opponents), 2)
        # Each mirror must link back to a valid participant id.
        participant_ids = {p.pk for p in self.encounter.participants_cached}
        for opp in mirror_opponents:
            self.assertIn(opp["mirrors_participant_id"], participant_ids)


class OpponentSerializerMirrorFieldTests(TestCase):
    """OpponentSerializer exposes mirrors_participant_id for duel-mirror opponents."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def test_non_mirror_opponent_has_null_mirrors_participant_id(self) -> None:
        opponent = CombatOpponentFactory()
        data = OpponentSerializer(opponent).data
        self.assertIsNone(data["mirrors_participant_id"])

    def test_mirror_opponent_exposes_participant_id(self) -> None:
        participant = CombatParticipantFactory()
        mirror = CombatOpponentFactory(
            encounter=participant.encounter,
            mirrors_participant=participant,
        )
        data = OpponentSerializer(mirror).data
        self.assertEqual(data["mirrors_participant_id"], participant.pk)


class DuelChallengeSerializerTests(TestCase):
    """DuelChallengeSerializer serializes the challenge inbox."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

    def test_pending_challenge_serializes(self) -> None:
        challenge = DuelChallengeFactory()
        data = DuelChallengeSerializer(challenge).data
        self.assertEqual(data["id"], challenge.pk)
        self.assertEqual(data["status"], DuelChallengeStatus.PENDING)
        self.assertIsNotNone(data["created_at"])

    def test_challenger_identity_exposed(self) -> None:
        challenge = DuelChallengeFactory()
        data = DuelChallengeSerializer(challenge).data
        challenger = data["challenger"]
        self.assertEqual(challenger["id"], challenge.challenger_sheet_id)
        self.assertEqual(challenger["name"], challenge.challenger_sheet.character.db_key)

    def test_challenged_identity_exposed(self) -> None:
        challenge = DuelChallengeFactory()
        data = DuelChallengeSerializer(challenge).data
        challenged = data["challenged"]
        self.assertEqual(challenged["id"], challenge.challenged_sheet_id)
        self.assertEqual(challenged["name"], challenge.challenged_sheet.character.db_key)

    def test_resolved_at_null_when_pending(self) -> None:
        challenge = DuelChallengeFactory()
        data = DuelChallengeSerializer(challenge).data
        self.assertIsNone(data["resolved_at"])

    def test_resulting_encounter_null_when_pending(self) -> None:
        challenge = DuelChallengeFactory()
        data = DuelChallengeSerializer(challenge).data
        self.assertIsNone(data["resulting_encounter"])

    def test_declined_challenge_serializes(self) -> None:
        challenge = DuelChallengeFactory(status=DuelChallengeStatus.DECLINED)
        data = DuelChallengeSerializer(challenge).data
        self.assertEqual(data["status"], DuelChallengeStatus.DECLINED)
