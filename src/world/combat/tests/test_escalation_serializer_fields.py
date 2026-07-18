"""Tests for escalation state exposure on the combat API (#872, Task 9).

ParticipantSerializer surfaces the COMBAT CharacterEngagement's
escalation_level / intensity_modifier / control_modifier (public dramatic
state — not visibility-gated). EncounterDetailSerializer surfaces the
encounter's escalation_curve FK (writable) plus read-only curve metadata
(name, start_round, tick_narration).
"""

from unittest.mock import PropertyMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.escalation import apply_dramatic_surge
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
)
from world.combat.models import CombatParticipant, DramaticSurgeRecord
from world.combat.serializers import ParticipantSerializer
from world.mechanics.constants import EngagementType
from world.mechanics.services import begin_engagement, end_engagement
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import RoundStatus
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

    def test_escalation_fields_null_after_end_engagement(self) -> None:
        """Stale reverse-cache guard: queryset delete nulls pk without clearing the
        accessor; _combat_engagement must return None rather than a dead instance."""
        engagement = begin_engagement(
            self.sheet.character,
            EngagementType.COMBAT,
            source=self.encounter,
        )
        engagement.escalation_level = 2
        engagement.intensity_modifier = 1
        engagement.control_modifier = 1
        engagement.save()

        # Confirm fields are present while engaged.
        data_before = ParticipantSerializer(self.participant).data
        self.assertEqual(data_before["escalation_level"], 2)

        # end_engagement deletes via queryset; the reverse cache on the identity-
        # mapped ObjectDB instance is not cleared, but pk is nulled on the cached obj.
        end_engagement(
            self.sheet.character,
            EngagementType.COMBAT,
            source=self.encounter,
        )

        data_after = ParticipantSerializer(self.participant).data
        self.assertIsNone(data_after["escalation_level"])
        self.assertIsNone(data_after["intensity_modifier"])
        self.assertIsNone(data_after["control_modifier"])

    def test_combat_engagement_returns_none_when_character_sheet_attribute_error(self) -> None:
        """AttributeError branch in _combat_engagement: if the character_sheet
        descriptor raises (e.g. a bare or partially-constructed participant), the
        helper returns None rather than propagating.

        character_sheet is non-nullable at the DB level so we simulate the guard
        by patching the property on the class for the duration of the call.
        We test _combat_engagement directly (not the full serializer) to avoid
        triggering unrelated field handlers that don't share this guard shape.
        """
        serializer = ParticipantSerializer()
        with patch.object(
            CombatParticipant,
            "character_sheet",
            new_callable=PropertyMock,
            side_effect=AttributeError("no sheet"),
        ):
            result = serializer._combat_engagement(self.participant)

        self.assertIsNone(result)


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
            status=RoundStatus.DECLARING,
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


class SurgeBeatsSerializerFieldTests(TestCase):
    """EncounterDetailSerializer.surge_beats: generic line for everyone, owner/GM-scoped
    provenance for the surging participant + staff/GM (#2013).

    Exercised through the real API client (not a bare serializer context dict):
    ``EncounterDetailSerializer.to_representation`` unconditionally recomputes
    ``is_gm`` from ``request`` (see its docstring), so a hand-built context
    dict's ``is_gm``/``viewer_character_ids`` would just get clobbered. Owner
    and GM scoping are set up the same way ``EncounterEscalationCurveFieldTests``
    above does it: a RosterTenure for the owner, a GM SceneParticipation for
    the GM.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="surge_beats_player")
        cls.character = CharacterFactory(db_key="surgebeatschar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.character,
            player_data__account=cls.account,
        )
        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.account, is_gm=False)

        cls.gm_account = AccountFactory(username="surge_beats_gm")
        SceneParticipationFactory(scene=cls.scene, account=cls.gm_account, is_gm=True)

        cls.other_account = AccountFactory(username="surge_beats_other")

    def setUp(self) -> None:
        self.curve = EscalationCurveFactory(surge_narration="{character}'s power surges.")
        self.encounter = CombatEncounterFactory(
            scene=self.scene,
            escalation_curve=self.curve,
            round_number=3,
            status=RoundStatus.DECLARING,
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
            status=ParticipantStatus.ACTIVE,
        )
        begin_engagement(self.character, EngagementType.COMBAT, source=self.encounter)
        apply_dramatic_surge(
            encounter=self.encounter,
            participant=self.participant,
            amount=4,
            trigger_kind=SurgeTriggerKind.HIGH_STAKES,
        )
        self.surge_record = DramaticSurgeRecord.objects.get(
            encounter=self.encounter,
            participant=self.participant,
        )

    def _get_detail(self, account: object) -> dict:
        client = APIClient()
        client.force_authenticate(user=account)
        response = client.get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200)
        return response.data  # type: ignore[return-value]

    def test_owner_sees_full_provenance(self) -> None:
        data = self._get_detail(self.account)
        beat = data["surge_beats"][0]
        self.assertEqual(beat["id"], self.surge_record.pk)
        self.assertEqual(beat["narration"], f"{self.character.db_key}'s power surges.")
        self.assertEqual(beat["trigger_kind"], SurgeTriggerKind.HIGH_STAKES)
        self.assertEqual(beat["amount"], 4)

    def test_other_viewer_sees_only_generic_line(self) -> None:
        data = self._get_detail(self.other_account)
        beat = data["surge_beats"][0]
        self.assertEqual(beat["id"], self.surge_record.pk)
        self.assertIn("narration", beat)
        self.assertNotIn("trigger_kind", beat)
        self.assertNotIn("amount", beat)

    def test_gm_sees_full_provenance(self) -> None:
        data = self._get_detail(self.gm_account)
        beat = data["surge_beats"][0]
        self.assertIn("trigger_kind", beat)

    def test_only_current_round_beats_are_surfaced(self) -> None:
        self.encounter.round_number = 4
        self.encounter.save(update_fields=["round_number"])
        data = self._get_detail(self.account)
        self.assertEqual(data["surge_beats"], [])
