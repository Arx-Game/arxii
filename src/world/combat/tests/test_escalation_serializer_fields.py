"""Tests for escalation state exposure on the combat API (#872, Task 9).

ParticipantSerializer surfaces the COMBAT CharacterEngagement's
escalation_level / intensity_modifier / control_modifier (public dramatic
state — not visibility-gated). EncounterDetailSerializer surfaces the
encounter's escalation_curve FK (writable) plus read-only curve metadata
(name, start_round, tick_narration).
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.serializers import ParticipantSerializer
from world.mechanics.constants import EngagementType
from world.mechanics.services import begin_engagement
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class ParticipantEscalationFieldTests(TestCase):
    """ParticipantSerializer carries COMBAT-engagement escalation state."""

    def setUp(self) -> None:
        super().setUp()
        self.sheet = CharacterSheetFactory()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
        )

    def test_escalation_fields_read_combat_engagement(self) -> None:
        engagement = begin_engagement(
            self.sheet.character,
            EngagementType.COMBAT,
            source=self.encounter,
        )
        engagement.escalation_level = 3
        engagement.intensity_modifier = 2
        engagement.control_modifier = 1
        engagement.save()

        data = ParticipantSerializer(self.participant).data

        self.assertEqual(data["escalation_level"], 3)
        self.assertEqual(data["intensity_modifier"], 2)
        self.assertEqual(data["control_modifier"], 1)

    def test_escalation_fields_null_without_engagement(self) -> None:
        data = ParticipantSerializer(self.participant).data

        self.assertIsNone(data["escalation_level"])
        self.assertIsNone(data["intensity_modifier"])
        self.assertIsNone(data["control_modifier"])

    def test_escalation_fields_ignore_non_combat_engagement(self) -> None:
        engagement = begin_engagement(
            self.sheet.character,
            EngagementType.CHALLENGE,
            source=self.encounter,
        )
        engagement.escalation_level = 5
        engagement.save()

        data = ParticipantSerializer(self.participant).data

        self.assertIsNone(data["escalation_level"])
        self.assertIsNone(data["intensity_modifier"])
        self.assertIsNone(data["control_modifier"])


class EncounterEscalationCurveFieldTests(TestCase):
    """EncounterDetailSerializer exposes the escalation curve + metadata."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="escalation_field_player")
        cls.character = CharacterFactory(db_key="escalationfieldchar")
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

    def setUp(self) -> None:
        # Fresh encounter per test — the SharedMemoryModel identity map would
        # otherwise leak cached prefetch attrs across tests.
        self.encounter = CombatEncounterFactory(
            scene=self.scene,
            status=EncounterStatus.DECLARING,
        )
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _get_detail(self) -> dict:
        response = self.client.get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200)
        return response.data  # type: ignore[return-value]

    def test_curve_fields_present_when_curve_set(self) -> None:
        curve = EscalationCurveFactory(
            start_round=3,
            tick_narration="The air thickens with violence.",
        )
        self.encounter.escalation_curve = curve
        self.encounter.save()

        data = self._get_detail()

        self.assertEqual(data["escalation_curve"], curve.pk)
        self.assertEqual(data["escalation_curve_name"], curve.name)
        self.assertEqual(data["escalation_start_round"], 3)
        self.assertEqual(
            data["escalation_tick_narration"],
            "The air thickens with violence.",
        )

    def test_curve_fields_null_when_no_curve(self) -> None:
        data = self._get_detail()

        self.assertIsNone(data["escalation_curve"])
        self.assertIsNone(data["escalation_curve_name"])
        self.assertIsNone(data["escalation_start_round"])
        self.assertIsNone(data["escalation_tick_narration"])

    def test_patch_sets_escalation_curve(self) -> None:
        curve = EscalationCurveFactory()
        staff = AccountFactory(username="escalation_field_staff")
        staff.is_staff = True
        staff.save()
        staff_client = APIClient()
        staff_client.force_authenticate(user=staff)

        response = staff_client.patch(
            f"/api/combat/{self.encounter.pk}/",
            {"escalation_curve": curve.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.escalation_curve_id, curve.pk)

    def test_patch_clears_escalation_curve(self) -> None:
        curve = EscalationCurveFactory()
        self.encounter.escalation_curve = curve
        self.encounter.save()
        staff = AccountFactory(username="escalation_clear_staff")
        staff.is_staff = True
        staff.save()
        staff_client = APIClient()
        staff_client.force_authenticate(user=staff)

        response = staff_client.patch(
            f"/api/combat/{self.encounter.pk}/",
            {"escalation_curve": None},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.encounter.refresh_from_db()
        self.assertIsNone(self.encounter.escalation_curve_id)
