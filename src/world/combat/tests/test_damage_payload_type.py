"""Tests that DAMAGE_PRE_APPLY / DAMAGE_APPLIED payloads carry DamageType FK, not str."""

from unittest.mock import patch

from django.test import TestCase

from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.conditions.factories import DamageTypeFactory
from world.vitals.constants import CharacterStatus
from world.vitals.models import CharacterVitals


class DamagePayloadTypeTests(TestCase):
    """Verify that apply_damage_to_participant passes DamageType FK through payloads."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory()
        cls.participant = CombatParticipantFactory(encounter=cls.encounter)
        cls.fire = DamageTypeFactory(name="Fire")

    def setUp(self) -> None:
        self.vitals, _ = CharacterVitals.objects.get_or_create(
            character_sheet=self.participant.character_sheet,
            defaults={"health": 100, "max_health": 100, "status": CharacterStatus.ALIVE},
        )
        self.vitals.health = 100
        self.vitals.max_health = 100
        self.vitals.status = CharacterStatus.ALIVE
        self.vitals.save()

        # Move character into encounter room so DAMAGE_PRE_APPLY fires
        character = self.participant.character_sheet.character
        character.location = self.encounter.room
        character.save()

    def test_pre_apply_payload_carries_damage_type_fk(self) -> None:
        """DAMAGE_PRE_APPLY payload.damage_type must be a DamageType FK, not a string."""
        from flows.constants import EventName
        from world.combat.services import apply_damage_to_participant

        captured: list = []

        class _FakeStack:
            def was_cancelled(self) -> bool:
                return False

        def _capture(event_name: str, payload: object, **kwargs: object) -> _FakeStack:
            captured.append((event_name, payload))
            return _FakeStack()

        with patch("world.combat.services.emit_event", side_effect=_capture):
            apply_damage_to_participant(self.participant, 5, damage_type=self.fire)

        pre_apply_payloads = [p for n, p in captured if n == EventName.DAMAGE_PRE_APPLY]
        self.assertEqual(len(pre_apply_payloads), 1)
        # Critical assertion — must be the DamageType instance, not a string
        self.assertEqual(pre_apply_payloads[0].damage_type, self.fire)
        self.assertNotIsInstance(pre_apply_payloads[0].damage_type, str)

    def test_applied_payload_carries_damage_type_fk(self) -> None:
        """DAMAGE_APPLIED payload.damage_type must be a DamageType FK, not a string."""
        from flows.constants import EventName
        from world.combat.services import apply_damage_to_participant

        captured: list = []

        class _FakeStack:
            def was_cancelled(self) -> bool:
                return False

        def _capture(event_name: str, payload: object, **kwargs: object) -> _FakeStack:
            captured.append((event_name, payload))
            return _FakeStack()

        with patch("world.combat.services.emit_event", side_effect=_capture):
            apply_damage_to_participant(self.participant, 5, damage_type=self.fire)

        applied_payloads = [p for n, p in captured if n == EventName.DAMAGE_APPLIED]
        self.assertEqual(len(applied_payloads), 1)
        # Critical assertion — must be the DamageType instance, not a string
        self.assertEqual(applied_payloads[0].damage_type, self.fire)
        self.assertNotIsInstance(applied_payloads[0].damage_type, str)

    def test_none_damage_type_passes_through(self) -> None:
        """damage_type=None (untyped) is valid and passes through as None."""
        from flows.constants import EventName
        from world.combat.services import apply_damage_to_participant

        captured: list = []

        class _FakeStack:
            def was_cancelled(self) -> bool:
                return False

        def _capture(event_name: str, payload: object, **kwargs: object) -> _FakeStack:
            captured.append((event_name, payload))
            return _FakeStack()

        with patch("world.combat.services.emit_event", side_effect=_capture):
            apply_damage_to_participant(self.participant, 5, damage_type=None)

        pre_apply_payloads = [p for n, p in captured if n == EventName.DAMAGE_PRE_APPLY]
        self.assertEqual(len(pre_apply_payloads), 1)
        self.assertIsNone(pre_apply_payloads[0].damage_type)
