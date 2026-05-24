"""Tests for EncounterDetailSerializer.clashes field.

Phase 8, Task 8.4 — verifies that GET /api/combat/<id>/ exposes active
Clash records via the new `clashes` SerializerMethodField.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ClashStatus, EncounterStatus
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class EncounterDetailClashesFieldTests(TestCase):
    """EncounterDetailSerializer exposes active Clash records in `clashes` field."""

    @classmethod
    def setUpTestData(cls) -> None:
        ClashConfigFactory()

        cls.account = AccountFactory(username="clashtest_player")
        cls.character = CharacterFactory(db_key="clashtestchar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.character,
            player_data__account=cls.account,
        )
        cls.scene = SceneFactory()
        SceneParticipationFactory(
            scene=cls.scene,
            account=cls.account,
            is_gm=False,
        )
        cls.encounter = CombatEncounterFactory(
            scene=cls.scene,
            status=EncounterStatus.DECLARING,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
        )

    def _get_detail(self) -> dict:
        client = APIClient()
        client.force_authenticate(user=self.account)
        response = client.get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200)
        return response.data  # type: ignore[return-value]

    def test_clashes_field_present_when_no_active_clashes(self) -> None:
        data = self._get_detail()
        self.assertIn("clashes", data)
        self.assertEqual(data["clashes"], [])

    def test_clashes_field_returns_active_clash(self) -> None:
        clash = ClashFactory(
            encounter=self.encounter,
            status=ClashStatus.ACTIVE,
            progress=2,
            pc_win_threshold=5,
        )

        data = self._get_detail()

        self.assertEqual(len(data["clashes"]), 1)
        clash_data = data["clashes"][0]
        self.assertEqual(clash_data["id"], clash.pk)
        self.assertEqual(clash_data["flavor"], "CLASH")
        self.assertEqual(clash_data["status"], ClashStatus.ACTIVE)
        self.assertEqual(clash_data["progress"], 2)
        self.assertEqual(clash_data["pc_win_threshold"], 5)

    def test_clashes_excludes_resolved_clashes(self) -> None:
        # Create a resolved clash — should not appear.
        ClashFactory(
            encounter=self.encounter,
            status=ClashStatus.RESOLVED,
        )
        # Create an active one — should appear.
        active = ClashFactory(
            encounter=self.encounter,
            status=ClashStatus.ACTIVE,
        )

        data = self._get_detail()

        ids = [c["id"] for c in data["clashes"]]
        self.assertIn(active.pk, ids)
        self.assertEqual(len(ids), 1)
