"""The combat payload lists conditions applied between two requests in one process.

A bare ``Prefetch(to_attr=...)`` on the idmapper-shared ObjectDB left the first
request's conditions on the instance, and every later request served them (ADR-0263).
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.services import apply_condition
from world.magic.factories import AudereThresholdFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory


class PayloadConditionsStayFreshTests(TestCase):
    def test_condition_applied_between_requests_reaches_the_second_payload(self) -> None:
        account = AccountFactory(username="fresh_player")
        character = CharacterFactory(db_key="FreshChar")
        sheet = CharacterSheetFactory(character=character)
        RosterTenureFactory(
            roster_entry__character_sheet__character=character,
            player_data__account=account,
        )
        audere = ConditionTemplateFactory(name="Breakthrough", is_visible_to_others=True)
        AudereThresholdFactory(audere_condition=audere)
        encounter = CombatEncounterFactory(scene=SceneFactory())
        CombatParticipantFactory(
            encounter=encounter, character_sheet=sheet, status=ParticipantStatus.ACTIVE
        )
        client = APIClient()
        client.force_authenticate(user=account)
        url = f"/api/combat/{encounter.pk}/"

        before = client.get(url).json()["participants"][0]
        self.assertEqual(before["active_conditions"], [])
        self.assertIsNone(before["audere_state"])

        apply_condition(character, audere)

        after = client.get(url).json()["participants"][0]
        self.assertEqual([c["name"] for c in after["active_conditions"]], ["Breakthrough"])
        self.assertEqual(after["audere_state"], "audere")
