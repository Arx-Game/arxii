"""POST /api/combat/<id>/taunt/ names an opponent or a participant, exactly one (#4737)."""

from django.test import TestCase
from rest_framework import status as http_status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.vitals.models import CharacterVitals


class TauntEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="taunt_endpoint_player")
        character = CharacterFactory(db_key="taunt_endpoint_char")
        cls.sheet = CharacterSheetFactory(character=character)
        RosterTenureFactory(
            roster_entry__character_sheet__character=character,
            player_data__account=cls.account,
        )
        CharacterVitals.objects.get_or_create(
            character_sheet=cls.sheet, defaults={"health": 50, "max_health": 100}
        )
        cls.encounter = CombatEncounterFactory(
            scene=SceneFactory(), status=RoundStatus.DECLARING, round_number=1
        )
        cls.taunter = CombatParticipantFactory(
            encounter=cls.encounter, character_sheet=cls.sheet, status=ParticipantStatus.ACTIVE
        )
        cls.ally = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=CharacterSheetFactory(),
            status=ParticipantStatus.ACTIVE,
        )
        cls.opponent = CombatOpponentFactory(encounter=cls.encounter)

    def _post(self, body: dict) -> object:
        client = APIClient()
        client.force_authenticate(user=self.account)
        return client.post(f"/api/combat/{self.encounter.pk}/taunt/", body, format="json")

    def _declared(self) -> CombatRoundAction | None:
        return CombatRoundAction.objects.filter(
            participant=self.taunter, round_number=1, maneuver=CombatManeuver.TAUNT
        ).first()

    def test_taunt_endpoint_accepts_participant_id(self) -> None:
        response = self._post({"participant_id": self.ally.pk})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.content)
        action = self._declared()
        self.assertEqual(action.focused_ally_target, self.ally)
        self.assertIsNone(action.focused_opponent_target)

    def test_taunt_endpoint_still_accepts_opponent_id(self) -> None:
        response = self._post({"opponent_id": self.opponent.pk})
        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.content)
        action = self._declared()
        self.assertEqual(action.focused_opponent_target, self.opponent)
        self.assertIsNone(action.focused_ally_target)

    def test_taunt_endpoint_rejects_both_ids(self) -> None:
        response = self._post({"participant_id": self.ally.pk, "opponent_id": self.opponent.pk})
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(),
            {
                "non_field_errors": [
                    "Name exactly one target to taunt: an opponent or a participant."
                ]
            },
        )
        self.assertIsNone(self._declared())

    def test_taunt_endpoint_rejects_neither_id(self) -> None:
        response = self._post({})
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(),
            {
                "non_field_errors": [
                    "Name exactly one target to taunt: an opponent or a participant."
                ]
            },
        )
        self.assertIsNone(self._declared())

    def test_taunting_yourself_is_a_plain_400(self) -> None:
        response = self._post({"participant_id": self.taunter.pk})
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("yourself", response.content.decode())
        self.assertIsNone(self._declared())

    def test_a_participant_of_another_encounter_is_404(self) -> None:
        stranger = CombatParticipantFactory(
            encounter=CombatEncounterFactory(), status=ParticipantStatus.ACTIVE
        )
        response = self._post({"participant_id": stranger.pk})
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
